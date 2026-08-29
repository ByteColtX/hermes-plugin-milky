"""验证 T09 的 per-chat 短暂 admission 和 ingress 顺序。"""

from __future__ import annotations

import asyncio

import pytest

from session.admission import ChatAdmissionCoordinator
from session.identity import ChatKeyError


def test_invalid_chat_key_is_rejected_before_ticket_allocation() -> None:
    """admission 必须复用 T07 身份校验，非法目标不能消耗有效入口。"""

    coordinator = ChatAdmissionCoordinator()

    with pytest.raises(ChatKeyError):
        coordinator.admit("private:300")

    async def scenario() -> int:
        async with coordinator.admit("group:300") as ticket:
            return ticket.ingress_sequence

    assert asyncio.run(scenario()) == 1


def test_same_chat_admission_is_fifo_and_releases_after_short_boundary() -> None:
    """同一 chat 按登记顺序串行，离开上下文后下一个入口立即可用。"""

    async def scenario() -> tuple[list[str], list[int]]:
        coordinator = ChatAdmissionCoordinator()
        first = coordinator.admit("group:300")
        second = coordinator.admit("group:300")
        third = coordinator.admit("group:300")
        entered: list[str] = []
        sequences: list[int] = []
        first_finished = asyncio.Event()

        async def worker(label: str, lease) -> None:
            async with lease as ticket:
                entered.append(label)
                sequences.append(ticket.ingress_sequence)
                if label == "first":
                    await first_finished.wait()

        tasks = [
            asyncio.create_task(worker("first", first)),
            asyncio.create_task(worker("second", second)),
            asyncio.create_task(worker("third", third)),
        ]
        await asyncio.sleep(0)
        assert entered == ["first"]
        first_finished.set()
        await asyncio.gather(*tasks)
        return entered, sequences

    entered, sequences = asyncio.run(scenario())

    assert entered == ["first", "second", "third"]
    assert sequences == [1, 2, 3]


def test_different_chats_can_enter_admission_in_parallel() -> None:
    """一个 chat 的短暂等待不能阻塞另一个 chat。"""

    async def scenario() -> list[str]:
        coordinator = ChatAdmissionCoordinator()
        first_entered = asyncio.Event()
        release_first = asyncio.Event()
        entered: list[str] = []

        async def blocked_group() -> None:
            async with coordinator.admit("group:300"):
                entered.append("group")
                first_entered.set()
                await release_first.wait()

        async def independent_dm() -> None:
            await first_entered.wait()
            async with coordinator.admit("dm:300"):
                entered.append("dm")

        group_task = asyncio.create_task(blocked_group())
        dm_task = asyncio.create_task(independent_dm())
        await dm_task
        assert entered == ["group", "dm"]
        release_first.set()
        await group_task
        return entered

    assert asyncio.run(scenario()) == ["group", "dm"]


def test_admission_does_not_cover_slow_agent_execution() -> None:
    """退出 admission 后可继续接纳消息，即使 detached Agent 仍在执行。"""

    async def scenario() -> tuple[list[str], bool]:
        coordinator = ChatAdmissionCoordinator()
        agent_finished = asyncio.Event()
        entered: list[str] = []

        async def slow_agent() -> None:
            await agent_finished.wait()

        async with coordinator.admit("group:300") as ticket:
            entered.append(f"submitted:{ticket.ingress_sequence}")
            agent_task = asyncio.create_task(slow_agent())

        async with coordinator.admit("group:300") as ticket:
            entered.append(f"submitted:{ticket.ingress_sequence}")

        agent_finished.set()
        await agent_task
        return entered, agent_task.done()

    assert asyncio.run(scenario()) == (["submitted:1", "submitted:2"], True)


def test_admission_releases_lock_when_critical_section_raises() -> None:
    """业务异常不能永久占用 chat admission。"""

    async def scenario() -> int:
        coordinator = ChatAdmissionCoordinator()
        with pytest.raises(RuntimeError, match="detached handoff failed"):
            async with coordinator.admit("group:300"):
                raise RuntimeError("detached handoff failed")

        async with coordinator.admit("group:300") as ticket:
            return ticket.ingress_sequence

    assert asyncio.run(scenario()) == 2


def test_cancelled_waiter_does_not_block_next_admission() -> None:
    """等待中的取消不能破坏同 chat 锁的后续交接。"""

    async def scenario() -> list[int]:
        coordinator = ChatAdmissionCoordinator()
        release_first = asyncio.Event()
        entered: list[int] = []

        async def first_worker() -> None:
            async with coordinator.admit("group:300") as ticket:
                entered.append(ticket.ingress_sequence)
                await release_first.wait()

        async def waiting_worker() -> None:
            async with coordinator.admit("group:300"):
                entered.append(2)

        first_task = asyncio.create_task(first_worker())
        await asyncio.sleep(0)
        waiting_task = asyncio.create_task(waiting_worker())
        await asyncio.sleep(0)
        waiting_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting_task

        release_first.set()
        await first_task
        async with coordinator.admit("group:300") as ticket:
            entered.append(ticket.ingress_sequence)
        return entered

    assert asyncio.run(scenario()) == [1, 3]
