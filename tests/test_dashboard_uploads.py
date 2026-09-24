"""上传实际字节限制、批次归属与配额回收验证。"""

import asyncio

import pytest

from dashboard.host import ManagementError
from dashboard.uploads import UploadStore
from tests.test_sticker_maintenance import _PNG


class Upload:
    def __init__(self, data, name="input.png"):
        self.data = data
        self.filename = name
        self.closed = False

    async def read(self, size):
        chunk, self.data = self.data[:size], self.data[size:]
        return chunk

    async def close(self):
        self.closed = True


def test_upload_ignores_name_and_never_uses_inbox(tmp_path):
    upload = Upload(_PNG, "../../untrusted.png")
    store = UploadStore(tmp_path)
    result = asyncio.run(store.receive([upload]))
    root, candidates = store.candidates(result["batch_id"], result["file_ids"])
    assert candidates[0][1].parent == root
    assert candidates[0][1].read_bytes() == _PNG
    assert not (tmp_path / "stickers" / "inbox").exists()
    assert upload.closed


def test_actual_bytes_quota_and_incomplete_cleanup(tmp_path, monkeypatch):
    import dashboard.uploads as module

    monkeypatch.setattr(module, "QUOTA", 10)
    store = UploadStore(tmp_path)
    with pytest.raises(ManagementError) as caught:
        asyncio.run(store.receive([Upload(_PNG)]))
    assert caught.value.status == "quota_exceeded"
    assert list(store.root.iterdir()) == []


def test_batch_file_limit_and_archive_rejection(tmp_path):
    store = UploadStore(tmp_path)
    with pytest.raises(ManagementError):
        asyncio.run(store.receive([Upload(_PNG)] * 51))
    with pytest.raises(ManagementError):
        asyncio.run(store.receive([Upload(_PNG, "images.zip")]))
    assert list(store.root.iterdir()) == []


def test_active_reference_prevents_discard_and_expiry(tmp_path):
    now = [10.0]
    store = UploadStore(tmp_path, clock=lambda: now[0])
    result = asyncio.run(store.receive([Upload(_PNG)]))
    store.reference(result["batch_id"], True)
    now[0] += 8 * 86400
    assert store.reclaim()["removed"] == 0
    with pytest.raises(ManagementError):
        store.discard(result["batch_id"])
    store.reference(result["batch_id"], False)
    assert store.reclaim()["removed"] == 1


def test_persisted_queued_import_protects_batch(tmp_path):
    from dashboard.jobs import JobManager

    now = [10.0]
    uploads = UploadStore(tmp_path, clock=lambda: now[0])
    batch = asyncio.run(uploads.receive([Upload(_PNG)]))
    manager = JobManager(tmp_path)
    task = manager.submit(
        manager.issue("import")["request_id"],
        "import",
        {"batch_id": batch["batch_id"], "file_ids": batch["file_ids"]},
    )
    now[0] += 8 * 86400
    assert uploads.reclaim()["removed"] == 0
    with pytest.raises(ManagementError):
        uploads.discard(batch["batch_id"])
    manager.cancel(task["task_id"])
    assert uploads.reclaim()["removed"] == 1


def test_refresh_recovers_only_remaining_explicit_candidates(tmp_path):
    store = UploadStore(tmp_path)
    batch = asyncio.run(store.receive([Upload(_PNG), Upload(_PNG)]))
    _, candidates = store.candidates(batch["batch_id"], batch["file_ids"])
    candidates[0][1].unlink()
    restored = UploadStore(tmp_path).list_batches()["items"]
    assert len(restored) == 1
    assert restored[0]["file_ids"] == [batch["file_ids"][1]]
    assert "name" not in repr(restored)
    assert not restored[0]["active"]


def test_cancelled_visual_protects_inputs_until_thread_exits(tmp_path):
    import threading

    from stickers.visual_worker import run_visual

    async def run():
        now = [10.0]
        uploads = UploadStore(tmp_path, clock=lambda: now[0])
        batch = await uploads.receive([Upload(_PNG)])
        entered, finish = threading.Event(), threading.Event()

        def read_later():
            entered.set()
            finish.wait(5)
            _, candidates = uploads.candidates(batch["batch_id"], batch["file_ids"])
            return candidates[0][1].read_bytes()

        task = asyncio.create_task(run_visual(tmp_path, read_later))
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        now[0] += 8 * 86400
        try:
            assert uploads.reclaim()["removed"] == 0
            with pytest.raises(ManagementError) as caught:
                uploads.discard(batch["batch_id"])
            assert caught.value.status == "busy"
        finally:
            finish.set()
        for _ in range(100):
            if not uploads._active(batch["batch_id"]):
                break
            await asyncio.sleep(0.01)
        assert uploads.reclaim()["removed"] == 1

    asyncio.run(run())
