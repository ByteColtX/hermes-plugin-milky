"""任务持久去重、排队限制和取消边界。"""

import asyncio

import pytest

from dashboard.host import ManagementError
from dashboard.jobs import JobManager


def test_same_request_returns_original_and_changed_content_conflicts(tmp_path):
    manager = JobManager(tmp_path)
    request = manager.issue("cleanup")["request_id"]
    first = manager.submit(request, "cleanup", {"plan_id": "a" * 48})
    assert manager.submit(request, "cleanup", {"plan_id": "a" * 48}) == first
    with pytest.raises(ManagementError) as caught:
        manager.submit(request, "cleanup", {"plan_id": "b" * 48})
    assert caught.value.status == "conflict"
    assert len(manager.list()["items"]) == 1


def test_queue_and_expired_ids_are_bounded(tmp_path):
    now = [1.0]
    manager = JobManager(tmp_path, clock=lambda: now[0])
    ids = [manager.issue("reindex")["request_id"] for _ in range(11)]
    for request in ids[:10]:
        manager.submit(request, "reindex", {})
    with pytest.raises(ManagementError) as caught:
        manager.submit(ids[10], "reindex", {})
    assert caught.value.status == "busy"
    now[0] += 8 * 86400
    with pytest.raises(ManagementError) as caught:
        manager.submit(ids[0], "reindex", {})
    assert caught.value.status == "expired"


def test_cancel_running_prevents_commit(tmp_path):
    async def run():
        manager = JobManager(tmp_path)
        entered = asyncio.Event()
        finish = asyncio.Event()
        committed = []

        async def execute(_operation, _payload, guard):
            entered.set()
            await finish.wait()
            guard()
            committed.append(True)
            return {"items": []}

        task = manager.submit(manager.issue("reindex")["request_id"], "reindex", {})["task_id"]
        manager.start(execute, lambda: True)
        await entered.wait()
        manager.cancel(task)
        finish.set()
        await manager.worker
        assert not committed
        assert manager.list()["items"][0]["status"] == "cancelled"
        await manager.close()

    asyncio.run(run())


def test_close_and_restart_do_not_replay(tmp_path):
    async def run():
        manager = JobManager(tmp_path)
        entered = asyncio.Event()

        async def execute(*_):
            entered.set()
            await asyncio.Event().wait()

        manager.submit(manager.issue("reindex")["request_id"], "reindex", {})
        manager.start(execute, lambda: True)
        await entered.wait()
        await manager.close()
        restored = JobManager(tmp_path)
        restored.recover()
        assert restored.list()["items"][0]["status"] == "interrupted"
        assert restored.worker is None

    asyncio.run(run())


def test_browse_never_creates_storage(tmp_path):
    root = tmp_path / "missing"
    assert JobManager(root).list() == {"items": []}
    assert not root.exists()


@pytest.mark.parametrize(
    "operation,payload",
    [
        ("reindex", {"token": "sensitive"}),
        ("import", {"batch_id": "a" * 48, "file_ids": ["https://example.invalid"]}),
        ("delete", {"targets": []}),
        ("edit", {"targets": [{"sticker_id": "bad", "version": "b" * 64}]}),
    ],
)
def test_invalid_payload_never_persists(tmp_path, operation, payload):
    manager = JobManager(tmp_path)
    request = manager.issue(operation)["request_id"]
    with pytest.raises(ManagementError):
        manager.submit(request, operation, payload)
    assert manager.list()["items"] == []
    assert b"sensitive" not in (tmp_path / "dashboard-jobs.db").read_bytes()


def test_progress_survives_cancellation_and_queued_close(tmp_path):
    async def run():
        manager = JobManager(tmp_path)
        task = manager.submit(manager.issue("reindex")["request_id"], "reindex", {})["task_id"]
        manager.submit(manager.issue("reindex")["request_id"], "reindex", {})
        started = asyncio.Event()

        async def execute(_operation, _payload, guard):
            guard.progress([{"status": "updated", "sticker_id": "confirmed"}])
            started.set()
            await asyncio.Event().wait()

        manager.start(execute, lambda: True)
        await started.wait()
        manager.cancel(task)
        await manager.close()
        result = {x["task_id"]: x for x in manager.list()["items"]}
        assert result[task]["items"] == [{"status": "updated", "sticker_id": "confirmed"}]
        assert {x["status"] for x in result.values()} == {"cancelled", "interrupted"}

    asyncio.run(run())


def test_operation_status_does_not_replace_task_state(tmp_path):
    async def run():
        manager = JobManager(tmp_path)
        manager.submit(manager.issue("reindex")["request_id"], "reindex", {})

        async def execute(*_):
            return {"status": "ok", "indexed": 0}

        manager.start(execute, lambda: True)
        await manager.worker
        row = manager.list()["items"][0]
        assert row["status"] == "succeeded"
        assert row["operation_status"] == "ok"

    asyncio.run(run())


def test_dead_owner_queue_is_interrupted_without_replay(tmp_path, monkeypatch):
    import dashboard.jobs as module

    manager = JobManager(tmp_path)
    manager.submit(manager.issue("reindex")["request_id"], "reindex", {})

    def vanished(*_):
        raise ProcessLookupError()

    monkeypatch.setattr(module.os, "kill", vanished)
    restored = JobManager(tmp_path)
    restored.recover()
    assert restored.list()["items"][0]["status"] == "interrupted"
    assert restored.worker is None


def test_history_eviction_expires_identity_and_preserves_active(tmp_path):
    manager = JobManager(tmp_path)
    original = manager.issue("reindex")["request_id"]
    oldest = manager.submit(original, "reindex", {})["task_id"]
    with manager.connect() as conn:
        conn.execute("UPDATE jobs SET status='succeeded',updated=1 WHERE id=?", (oldest,))
        for index in range(1001):
            conn.execute(
                "INSERT INTO jobs(id,operation,payload,status,created,updated) VALUES (?,'reindex','{}','succeeded',?,?)",
                (f"synthetic-{index}", manager.clock(), manager.clock()),
            )
    active = manager.submit(manager.issue("reindex")["request_id"], "reindex", {})["task_id"]
    with pytest.raises(ManagementError) as caught:
        manager.submit(original, "reindex", {})
    assert caught.value.status == "expired"
    with manager.connect() as conn:
        assert (
            conn.execute("SELECT count(*) FROM jobs WHERE status='succeeded'").fetchone()[0] == 1000
        )
        assert (
            conn.execute("SELECT status FROM jobs WHERE id=?", (active,)).fetchone()[0] == "queued"
        )


def test_two_managers_serialize_profile_batches(tmp_path):
    async def run():
        first, second = JobManager(tmp_path), JobManager(tmp_path)
        entered, release = asyncio.Event(), asyncio.Event()
        order = []

        async def slow(*_):
            entered.set()
            await release.wait()
            order.append("first")
            return {}

        async def fast(*_):
            order.append("second")
            return {}

        for manager in (first, second):
            manager.submit(manager.issue("reindex")["request_id"], "reindex", {})
        first.start(slow, lambda: True)
        await entered.wait()
        second.start(fast, lambda: True)
        await asyncio.sleep(0.01)
        assert order == []
        release.set()
        await asyncio.gather(first.worker, second.worker)
        assert order == ["first", "second"]

    asyncio.run(run())
