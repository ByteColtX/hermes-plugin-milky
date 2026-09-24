"""只读图库与短提交冲突的合成图片验证。"""

import asyncio
from pathlib import Path

import pytest

from stickers.errors import StickerError, StickerStorageError
from stickers.maintenance import StickerMaintenanceService
from stickers.management import StickerManagementService
from tests.test_sticker_maintenance import _PNG, _vision


def _populate(root: Path):
    inbox = root / "stickers" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "sample.png").write_bytes(_PNG)
    service = StickerMaintenanceService(data_dir=root, vision_analyzer=lambda *_: _vision())
    asyncio.run(service.add())
    return service


def test_missing_browse_does_not_create_storage(tmp_path):
    root = tmp_path / "absent"
    assert StickerManagementService(root).browse()["items"] == []
    assert not root.exists()


def test_browse_preview_and_filters_are_read_only(tmp_path):
    _populate(tmp_path)
    manager = StickerManagementService(tmp_path)
    before = (tmp_path / "stickers.db").read_bytes()
    result = manager.browse(tag="开心", emotion="joy", description="表达")
    assert result["total"] == 1
    item = result["items"][0]
    assert item["field_sources"]["emotion"] == "vision"
    assert item["file_status"] == "available"
    assert manager.browse(page=2)["items"] == []
    assert manager.preview(item["sticker_id"]) == (_PNG, "image/png")
    assert (tmp_path / "stickers.db").read_bytes() == before
    assert item["use_count"] == 0


@pytest.mark.parametrize(
    "kwargs", [{"limit": 101}, {"limit": True}, {"page": 0}, {"emotion": "invalid"}, {"tag": ""}]
)
def test_invalid_pagination_and_filters(tmp_path, kwargs):
    with pytest.raises(StickerError) as caught:
        StickerManagementService(tmp_path).browse(**kwargs)
    assert caught.value.classification == "invalid_input"


def test_corrupt_database_is_not_rebuilt(tmp_path):
    database = tmp_path / "stickers.db"
    database.write_bytes(b"broken")
    with pytest.raises(StickerStorageError):
        StickerManagementService(tmp_path).browse()
    assert database.read_bytes() == b"broken"


def test_partial_edit_preserves_other_manual_fields(tmp_path):
    service = _populate(tmp_path)
    manager = StickerManagementService(tmp_path)
    sticker_id = manager.browse()["items"][0]["sticker_id"]
    service.edit(sticker_id, sets={"emotion": "love"})
    service.edit(sticker_id, sets={"description": "表达喜爱"})
    item = manager.browse()["items"][0]
    assert item["emotion"] == "love"
    assert item["description"] == "表达喜爱"


def test_reanalysis_conflicts_with_intervening_edit(tmp_path):
    service = _populate(tmp_path)
    sticker_id = StickerManagementService(tmp_path).browse()["items"][0]["sticker_id"]

    async def vision(*_):
        service.edit(sticker_id, sets={"emotion": "love"})
        return _vision()

    other = StickerMaintenanceService(data_dir=tmp_path, vision_analyzer=vision)
    assert asyncio.run(other.reanalyze(sticker_id))["status"] == "conflict"
    assert StickerManagementService(tmp_path).browse()["items"][0]["emotion"] == "love"


def test_preview_rejects_other_profile_missing_and_changed_bytes(tmp_path):
    root = tmp_path / "a"
    service = _populate(root)
    manager = StickerManagementService(root)
    item = manager.browse()["items"][0]
    with pytest.raises(StickerError) as caught:
        StickerManagementService(tmp_path / "b").preview(item["sticker_id"])
    assert caught.value.classification == "not_found"
    path = next((root / "stickers" / "library").rglob("*.png"))
    path.write_bytes(b"corrupt")
    with pytest.raises(StickerError) as caught:
        manager.preview(item["sticker_id"])
    assert caught.value.classification == "integrity_error"
    path.unlink()
    with pytest.raises(StickerError) as caught:
        manager.preview(item["sticker_id"])
    assert caught.value.classification == "missing_file"
    service.delete(item["sticker_id"])
    with pytest.raises(StickerError) as caught:
        manager.preview(item["sticker_id"])
    assert caught.value.classification == "not_found"


def _contending_guard(root, connection):
    """独立进程检验目录锁，不共用父进程线程状态。"""
    from stickers.coordination import library_guard

    try:
        with library_guard(Path(root), timeout=0.1):
            connection.send("acquired")
    except StickerStorageError:
        connection.send("busy")
    finally:
        connection.close()


def test_library_guard_coordinates_independent_process(tmp_path):
    import multiprocessing

    from stickers.coordination import library_guard

    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    with library_guard(tmp_path):
        process = context.Process(target=_contending_guard, args=(str(tmp_path), writer))
        process.start()
        writer.close()
        assert reader.poll(5)
        assert reader.recv() == "busy"
        process.join(5)
        assert process.exitcode == 0
    reader.close()


def test_batch_edit_versions_and_cleanup_plan_preserve_new_files(tmp_path):
    service = _populate(tmp_path)
    manager = StickerManagementService(tmp_path)
    item = manager.browse()["items"][0]
    target = {"sticker_id": item["sticker_id"], "version": item["version"]}
    result = manager.mutate("edit", [target], sets={"emotion": "love"})
    assert result["items"][0]["status"] == "updated"
    assert manager.mutate("delete", [target])["items"][0]["status"] == "conflict"
    current = manager.browse()["items"][0]
    assert (
        manager.mutate(
            "delete", [{"sticker_id": current["sticker_id"], "version": current["version"]}]
        )["items"][0]["status"]
        == "deleted"
    )
    plan = manager.cleanup_plan()
    new_file = tmp_path / "stickers" / "library" / "later.tmp"
    new_file.write_bytes(b"keep")
    assert manager.cleanup_execute(plan["plan_id"])["removed"] == 1
    assert new_file.exists()
    assert service.list()["items"] == []


def test_explicit_import_never_consumes_command_inbox(tmp_path, monkeypatch):
    _populate(tmp_path)
    inbox = tmp_path / "stickers" / "inbox" / "untouched.png"
    inbox.write_bytes(_PNG)
    staged = tmp_path / "web-uploads" / "batch"
    staged.mkdir(parents=True)
    from tests.test_sticker_maintenance import _unique_png

    image = staged / "opaque.png"
    image.write_bytes(_unique_png(99))

    async def vision(*_):
        return _vision()

    monkeypatch.setattr(StickerMaintenanceService, "_call_vision", vision)
    result = asyncio.run(
        StickerManagementService(tmp_path).import_candidates(staged, [("file-id", image)])
    )
    assert result["items"][0]["status"] == "created"
    assert inbox.exists()
    assert not image.exists()


def test_independent_imports_preserve_content_uniqueness(tmp_path):
    import multiprocessing

    # 命令提交与 Web 提交使用同一个目录锁，直接让两个进程在提交边界竞争。
    from stickers.storage import StickerStore

    with StickerStore(data_dir=tmp_path):
        pass
    context = multiprocessing.get_context("spawn")
    result = context.Queue()
    start = context.Event()
    workers = []
    for index in range(2):
        inbox = tmp_path / f"candidate-{index}"
        inbox.mkdir()
        (inbox / "image.png").write_bytes(_PNG)
        worker = context.Process(
            target=_commit_process, args=(str(tmp_path), str(inbox), start, result)
        )
        workers.append(worker)
        worker.start()
    start.set()
    outcomes = [result.get(timeout=10) for _ in workers]
    for worker in workers:
        worker.join(5)
        assert worker.exitcode == 0
    assert sorted(outcomes) == ["created", "duplicate"]
    assert StickerManagementService(tmp_path).browse()["total"] == 1


def _commit_process(root, inbox, start, result):
    """独立数据库连接和视觉后提交，验证跨进程唯一性。"""
    from stickers.maintenance import parse_visual_response
    from stickers.storage import StickerStore
    from stickers.validation import validate_image_file

    root, inbox = Path(root), Path(inbox)
    candidate = validate_image_file(inbox / "image.png", inbox)
    assert start.wait(5)
    with StickerStore(data_dir=root) as store:
        outcome = StickerMaintenanceService(data_dir=root)._commit_sticker(
            store, candidate, parse_visual_response(_vision()), [], input_root=inbox
        )
    result.put(outcome["status"])


def test_preview_rejects_forged_index_path_and_symlink(tmp_path):
    from stickers.storage import StickerStore

    root = tmp_path / "library"
    _populate(root)
    manager = StickerManagementService(root)
    item = manager.browse()["items"][0]
    with StickerStore(data_dir=root) as store:
        store.connection.execute("UPDATE sticker_files SET relative_path='../outside.png'")
        store.connection.commit()
    (tmp_path / "outside.png").write_bytes(_PNG)
    with pytest.raises(StickerError) as caught:
        manager.preview(item["sticker_id"])
    assert caught.value.classification == "integrity_error"


def test_cleanup_rejects_changed_references_and_expired_plan(tmp_path):
    _populate(tmp_path)
    manager = StickerManagementService(tmp_path)
    plan = manager.cleanup_plan()
    item = manager.browse()["items"][0]
    manager.mutate("delete", [{"sticker_id": item["sticker_id"], "version": item["version"]}])
    with pytest.raises(StickerError) as caught:
        manager.cleanup_execute(plan["plan_id"])
    assert caught.value.classification == "conflict"
    import json

    plan = manager.cleanup_plan()
    path = tmp_path / "cleanup-plans" / (plan["plan_id"] + ".json")
    data = json.loads(path.read_text())
    data["created"] = 0
    path.write_text(json.dumps(data))
    with pytest.raises(StickerError) as caught:
        manager.cleanup_execute(plan["plan_id"])
    assert caught.value.classification == "expired"


def test_cancel_between_items_preserves_confirmation(tmp_path):
    from tests.test_sticker_maintenance import _unique_png

    service = _populate(tmp_path)
    image = tmp_path / "stickers" / "inbox" / "second.png"
    image.write_bytes(_unique_png(1))
    asyncio.run(service.add())
    manager = StickerManagementService(tmp_path)
    targets = [
        {"sticker_id": item["sticker_id"], "version": item["version"]}
        for item in manager.browse()["items"]
    ]
    snapshots = []
    calls = [0]

    def guard():
        calls[0] += 1
        if calls[0] >= 3:
            raise StickerError("cancelled")

    with pytest.raises(StickerError):
        manager.mutate(
            "delete", targets, guard=guard, progress=lambda items: snapshots.append(items)
        )
    assert snapshots[-1][0]["status"] == "deleted"
    assert snapshots[-1][1]["status"] == "not_started"
    assert manager.browse()["total"] == 1


def test_delete_refuses_corrupt_multiple_references(tmp_path):
    """模拟外部破坏唯一约束后的多引用库，删除不得扩大到共享文件。"""
    import sqlite3

    _populate(tmp_path)
    manager = StickerManagementService(tmp_path)
    item = manager.browse()["items"][0]
    with sqlite3.connect(tmp_path / "stickers.db") as connection:
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='sticker_items'"
        ).fetchone()[0]
        connection.execute("CREATE TABLE preserved_items AS SELECT * FROM sticker_items")
        connection.execute("DROP TABLE sticker_items")
        connection.execute(schema.replace("NOT NULL UNIQUE", "NOT NULL"))
        connection.execute("INSERT INTO sticker_items SELECT * FROM preserved_items")
        connection.execute("UPDATE preserved_items SET sticker_id = ?", ("a" * 32,))
        connection.execute("INSERT INTO sticker_items SELECT * FROM preserved_items")
        connection.execute("DROP TABLE preserved_items")
    target = {"sticker_id": item["sticker_id"], "version": item["version"]}
    result = manager.mutate("delete", [target])
    assert result["task_status"] == "partial"
    assert result["items"][0]["status"] == "storage_error"
    assert manager.browse()["total"] == 2
    assert manager.preview(item["sticker_id"]) == (_PNG, "image/png")


def test_reindex_failure_rolls_back_original_index(tmp_path):
    """重建在清空索引后失败时，事务恢复原索引和全部可见条目。"""
    from stickers.storage import StickerStore

    service = _populate(tmp_path)
    manager = StickerManagementService(tmp_path)
    before = manager.browse()
    with StickerStore(data_dir=tmp_path) as store:
        original = store.connection.execute("SELECT * FROM sticker_files").fetchall()
        store.connection.execute(
            "CREATE TRIGGER reject_reindex BEFORE INSERT ON sticker_files "
            "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
        )
        store.connection.commit()
    with pytest.raises(StickerStorageError):
        service.reindex()
    with StickerStore(data_dir=tmp_path) as store:
        assert store.connection.execute("SELECT * FROM sticker_files").fetchall() == original
    assert manager.browse() == before
    assert manager.preview(before["items"][0]["sticker_id"]) == (_PNG, "image/png")


def test_preview_read_finishes_before_concurrent_delete_and_cleanup(tmp_path, monkeypatch):
    """一次读取持有短保护，回收等待复制完成后再删除库文件。"""
    import concurrent.futures
    import threading

    from stickers import management

    service = _populate(tmp_path)
    manager = StickerManagementService(tmp_path)
    item = manager.browse()["items"][0]
    entered, release = threading.Event(), threading.Event()
    maintenance_started, maintenance_done = threading.Event(), threading.Event()
    original = management.read_validated_image_file

    def blocked_read(*args):
        entered.set()
        assert release.wait(3)
        return original(*args)

    def reclaim():
        maintenance_started.set()
        result = service.delete(item["sticker_id"])
        service.cleanup()
        maintenance_done.set()
        return result

    monkeypatch.setattr(management, "read_validated_image_file", blocked_read)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        preview = executor.submit(manager.preview, item["sticker_id"])
        try:
            assert entered.wait(2)
            reclamation = executor.submit(reclaim)
            assert maintenance_started.wait(2)
            assert not maintenance_done.wait(0.05)
        finally:
            release.set()
        assert preview.result(timeout=3) == (_PNG, "image/png")
        assert reclamation.result(timeout=3)["status"] == "deleted"
    assert not list((tmp_path / "stickers" / "library").rglob("*.png"))


def test_batch_rejects_duplicate_targets_before_first_write(tmp_path):
    """目标集合有重复时整次拒绝，不先提交第一个目标。"""
    _populate(tmp_path)
    manager = StickerManagementService(tmp_path)
    before = manager.browse()
    item = before["items"][0]
    target = {"sticker_id": item["sticker_id"], "version": item["version"]}
    with pytest.raises(StickerError) as caught:
        manager.mutate("delete", [target, target])
    assert caught.value.classification == "invalid_input"
    assert manager.browse() == before


def test_delete_unknown_target_keeps_explicit_batch_scope(tmp_path):
    """未知目标逐项失败，其余明确目标正常提交，重复删除不重报成功。"""
    _populate(tmp_path)
    manager = StickerManagementService(tmp_path)
    item = manager.browse()["items"][0]
    targets = [
        {"sticker_id": "a" * 32, "version": "missing"},
        {"sticker_id": item["sticker_id"], "version": item["version"]},
    ]
    result = manager.mutate("delete", targets)
    assert result["task_status"] == "partial"
    assert [entry["status"] for entry in result["items"]] == ["not_found", "deleted"]
    assert manager.browse()["total"] == 0
    repeated = manager.mutate("delete", targets)
    assert [entry["status"] for entry in repeated["items"]] == ["not_found", "not_found"]
    assert list((tmp_path / "stickers" / "library").rglob("*.png"))


def test_send_releases_library_guard_before_network_and_keeps_copied_bytes(tmp_path):
    """网络在途时允许回收，发送继续使用已复制 bytes 且仅调用一次。"""
    import base64

    from outbound.sender import OutboundSendResult
    from stickers.sending import StickerSendService

    service = _populate(tmp_path)
    manager = StickerManagementService(tmp_path)
    sticker_id = manager.browse()["items"][0]["sticker_id"]
    calls = []

    class Sender:
        async def send_sticker(self, chat_key, uri):
            calls.append((chat_key, uri))
            assert manager.browse()["items"][0]["use_count"] == 1

            def reclaim():
                assert service.delete(sticker_id)["status"] == "deleted"
                assert service.cleanup()["orphan"] == 1

            await asyncio.wait_for(asyncio.to_thread(reclaim), timeout=2)
            assert not list((tmp_path / "stickers" / "library").rglob("*.png"))
            assert base64.b64decode(uri.removeprefix("base64://")) == _PNG
            return OutboundSendResult(success=True, message_id="confirmed-send")

    result = asyncio.run(
        StickerSendService(data_dir=tmp_path).send(sticker_id, "group:700000001", Sender())
    )
    assert result == {"status": "sent", "message_id": "confirmed-send"}
    assert len(calls) == 1


def test_batch_50_limit_and_invalid_fields_are_atomic(tmp_path):
    _populate(tmp_path)
    manager = StickerManagementService(tmp_path)
    before = manager.browse()
    item = before["items"][0]
    targets = [{"sticker_id": item["sticker_id"], "version": item["version"]}]
    targets.extend({"sticker_id": f"missing_{n:020d}", "version": "missing"} for n in range(49))
    with pytest.raises(StickerError):
        manager.mutate("edit", targets, sets={"emotion": "love", "unknown": "bad"})
    assert manager.browse() == before
    with pytest.raises(StickerError):
        manager.mutate(
            "edit",
            targets + [{"sticker_id": "extra_target", "version": "missing"}],
            sets={"emotion": "love"},
        )
    assert manager.browse() == before
    result = manager.mutate("edit", targets, sets={"emotion": "love"})
    assert result["task_status"] == "partial"
    assert result["items"][0]["status"] == "updated"
    assert all(x["status"] == "not_found" for x in result["items"][1:])
    updated = manager.browse()["items"][0]
    assert updated["use_count"] == 0
    cleared = manager.mutate(
        "edit",
        [{"sticker_id": updated["sticker_id"], "version": updated["version"]}],
        clears=["emotion"],
    )
    assert cleared["items"][0]["status"] == "updated"
    assert manager.browse()["items"][0]["field_sources"]["emotion"] == "vision"
