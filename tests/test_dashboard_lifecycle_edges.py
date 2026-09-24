"""停用、关闭和视觉迟到结果的提交边界。"""

import asyncio
import threading

import pytest

from dashboard.jobs import JobManager
from stickers.maintenance import StickerMaintenanceService
from stickers.management import StickerManagementService
from tests.test_sticker_maintenance import _vision
from tests.test_sticker_management import _populate


@pytest.mark.parametrize("before_dispatch", [True, False])
def test_disabled_profile_never_commits(tmp_path, before_dispatch):
    async def run():
        manager = JobManager(tmp_path)
        active = [not before_dispatch]
        committed = []

        async def execute(_operation, _payload, guard):
            active[0] = False
            guard()
            committed.append(True)
            return {}

        manager.submit(manager.issue("reindex")["request_id"], "reindex", {})
        manager.start(execute, lambda: active[0])
        await manager.worker
        assert not committed
        assert manager.list()["items"][0]["status"] == "cancelled"
        await manager.close()

    asyncio.run(run())


def test_closing_one_owner_preserves_another_queue(tmp_path):
    first, second = JobManager(tmp_path), JobManager(tmp_path)
    first.submit(first.issue("reindex")["request_id"], "reindex", {})
    other = second.submit(second.issue("reindex")["request_id"], "reindex", {})
    asyncio.run(first.close())
    rows = {x["task_id"]: x["status"] for x in second.list()["items"]}
    assert rows[other["task_id"]] == "queued"
    assert not second.closed


def test_reanalysis_cancel_discards_late_visual_result(tmp_path, monkeypatch):
    _populate(tmp_path)
    gallery = StickerManagementService(tmp_path)
    before = gallery.browse()
    item = before["items"][0]
    entered, finish, ended = threading.Event(), threading.Event(), threading.Event()

    async def slow(_self, _path):
        entered.set()
        assert finish.wait(5)
        ended.set()
        return _vision()

    monkeypatch.setattr(StickerMaintenanceService, "_call_vision", slow)

    async def run():
        task = asyncio.create_task(
            gallery.reanalyze_targets(
                [{"sticker_id": item["sticker_id"], "version": item["version"]}]
            )
        )
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        finish.set()
        assert await asyncio.to_thread(ended.wait, 2)
        for _ in range(100):
            from dashboard.uploads import UploadStore

            if not UploadStore(tmp_path)._active("unused"):
                break
            await asyncio.sleep(0.01)
        assert gallery.browse() == before

    asyncio.run(run())


def test_adapter_disconnect_and_web_close_keep_independent_ownership(tmp_path):
    from tests.test_adapter_lifecycle import make_adapter

    async def run():
        adapter, _, stream, _, _, client = make_adapter()
        assert await adapter.connect()
        await stream.started.wait()
        manager = JobManager(tmp_path)
        entered, release = asyncio.Event(), asyncio.Event()

        async def execute(_operation, _payload, guard):
            entered.set()
            await release.wait()
            guard()
            return {}

        manager.submit(manager.issue("reindex")["request_id"], "reindex", {})
        manager.start(execute, lambda: True)
        await entered.wait()
        await adapter.disconnect()
        assert not manager.closed and not manager.worker.done()
        release.set()
        await manager.worker
        assert manager.list()["items"][0]["status"] == "succeeded"
        other, _, other_stream, _, _, other_client = make_adapter()
        assert await other.connect()
        await other_stream.started.wait()
        await manager.close()
        assert other_client.close_calls == 0
        assert not other_stream.stopped.is_set()
        await other.disconnect()
        assert client.close_calls == 1

    asyncio.run(run())
