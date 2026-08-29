"""验证 T10 的 wait buffer 和 detached trigger batch 契约。"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from session import ChatAdmissionCoordinator
from session.buffer import (
    DetachedTriggerBatch,
    WaitBuffer,
    render_channel_context,
    render_message_record,
)


@dataclass(frozen=True, slots=True)
class FakeMessage:
    """提供 T10 所需的规范化消息字段，不包含 raw payload。"""

    chat_key: str
    sender_name: str
    sender_id: int
    body: str
    message_id: str | None = None
    quote_message_id: str | None = None
    raw: dict[str, str] | None = None


def message(
    number: int,
    *,
    chat_key: str = "group:300",
    sender_name: str | None = None,
    body: str | None = None,
    message_id: str | None = None,
    quote_message_id: str | None = None,
) -> FakeMessage:
    """构造一条最小的规范化历史消息。"""

    return FakeMessage(
        chat_key=chat_key,
        sender_name=sender_name or f"sender-{number}",
        sender_id=100 + number,
        body=body or f"body-{number}",
        message_id=message_id if message_id is not None else str(number),
        quote_message_id=quote_message_id,
    )


def test_wait_buffer_defaults_to_twenty_and_evicts_oldest_fifo() -> None:
    """默认 buffer 有界，溢出时只丢弃最早历史并返回安全诊断。"""

    buffer = WaitBuffer()

    for number in range(1, 22):
        result = buffer.append("group:300", message(number), ingress_sequence=number)

    assert result.accepted is True
    assert result.reason == "wait_buffer_overflow"
    assert result.evicted is not None
    assert result.evicted.message == message(1)
    assert [item.sender_id for item in buffer.snapshot("group:300")] == list(range(102, 122))
    assert buffer.diagnostics[-1].reason == "wait_buffer_overflow"


def test_zero_capacity_does_not_retain_history() -> None:
    """容量为零时 wait 消息明确丢弃，不创建历史上下文。"""

    buffer = WaitBuffer(max_size=0)

    result = buffer.append("group:300", message(1), ingress_sequence=1)
    batch = buffer.drain("group:300", message(2), ingress_sequence=2)

    assert result.accepted is False
    assert result.reason == "wait_buffer_disabled"
    assert buffer.snapshot("group:300") == ()
    assert batch.history == ()
    assert batch.channel_context is None


def test_wait_buffer_isolated_by_chat_key() -> None:
    """不同 chat 的历史不能互相出现在 detached batch 中。"""

    buffer = WaitBuffer(max_size=2)
    buffer.append("group:300", message(1, chat_key="group:300"))
    buffer.append("dm:300", message(2, chat_key="dm:300"))

    group_batch = buffer.drain("group:300", message(3, chat_key="group:300"))
    dm_batch = buffer.drain("dm:300", message(4, chat_key="dm:300"))

    assert group_batch.history == (message(1, chat_key="group:300"),)
    assert dm_batch.history == (message(2, chat_key="dm:300"),)
    assert group_batch.chat_key == "group:300"
    assert dm_batch.chat_key == "dm:300"


def test_drain_atomically_detaches_history_and_separates_current_message() -> None:
    """drain 清空 buffer 后才返回 detached batch，当前消息不进入历史。"""

    buffer = WaitBuffer()
    history = (message(1), message(2, quote_message_id="1"))
    for item in history:
        buffer.append("group:300", item)
    current = message(3, sender_name="Carol", body="trigger")

    batch = buffer.drain("group:300", current, ingress_sequence=3)

    assert isinstance(batch, DetachedTriggerBatch)
    assert batch.history == history
    assert batch.current == current
    assert batch.channel_context == (
        "[sender-1 uid 101 msg_id 1]\nbody-1\n[sender-2 uid 102 msg_id 2 reply_id 1]\nbody-2"
    )
    assert batch.current_text == "[Carol uid 103 msg_id 3]\ntrigger"
    assert current not in batch.history
    assert buffer.snapshot("group:300") == ()


def test_context_omits_empty_ids_and_escapes_untrusted_boundaries() -> None:
    """上下文只使用规范化字段，且不能被名称或正文伪造记录边界。"""

    unsafe = FakeMessage(
        chat_key="group:300",
        sender_name="A\\]name\r\nnext",
        sender_id=101,
        body="line\r\n[forged] raw-token",
    )

    assert render_message_record(unsafe) == (
        "[A\\\\\\]name\\n\\nnext uid 101]\nline\\n\\n[forged] raw-token"
    )
    assert render_channel_context((unsafe,)) == render_message_record(unsafe)

    no_ids = FakeMessage(
        chat_key="group:300",
        sender_name="sender-2",
        sender_id=102,
        body="body-2",
    )
    assert render_message_record(no_ids) == "[sender-2 uid 102]\nbody-2"
    assert render_channel_context(()) is None


def test_context_does_not_read_raw_payload() -> None:
    """历史上下文只读取规范化字段，不把 raw 中的凭证带入输出。"""

    candidate = message(1)
    candidate = FakeMessage(
        chat_key=candidate.chat_key,
        sender_name=candidate.sender_name,
        sender_id=candidate.sender_id,
        body=candidate.body,
        message_id=candidate.message_id,
        raw={"authorization": "Bearer fixture-secret", "token": "fixture-secret"},
    )

    rendered = render_message_record(candidate)

    assert rendered == "[sender-1 uid 101 msg_id 1]\nbody-1"
    assert "fixture-secret" not in rendered


def test_buffer_rejects_invalid_capacity_sequence_and_cross_chat_message() -> None:
    """buffer 的容量、ingress 和 chat 边界必须在内存操作前校验。"""

    for invalid in (-1, True, "20"):
        try:
            WaitBuffer(invalid)  # type: ignore[arg-type]
        except ValueError:
            pass
        else:
            raise AssertionError("invalid capacity was accepted")

    buffer = WaitBuffer()
    foreign = message(1, chat_key="dm:300")

    try:
        buffer.append("group:300", foreign)
    except ValueError as error:
        assert str(error) == "message chat_key disagrees with buffer chat_key"
    else:
        raise AssertionError("cross-chat message was accepted")

    try:
        buffer.append("group:300", message(2), ingress_sequence=-1)
    except ValueError:
        pass
    else:
        raise AssertionError("negative ingress sequence was accepted")


def test_buffer_diagnostics_are_bounded() -> None:
    """持续 wait 或溢出不能通过诊断列表制造无界内存。"""

    buffer = WaitBuffer(max_size=0)

    for number in range(300):
        buffer.append("group:300", message(number))

    assert len(buffer.diagnostics) == 256
    assert all(item.reason == "wait_buffer_disabled" for item in buffer.diagnostics)


def test_detached_failure_retries_same_batch_without_refilling_buffer() -> None:
    """失败策略只能重试原 batch 或记录失败，不能无条件回填历史。"""

    buffer = WaitBuffer()
    history = message(1)
    buffer.append("group:300", history)
    batch = buffer.drain("group:300", message(2))

    retry = buffer.record_handoff_failure(batch, recoverable=True)
    unrecoverable = buffer.record_handoff_failure(batch, recoverable=False)

    assert retry.action == "retry_same_batch"
    assert retry.batch is batch
    assert unrecoverable.action == "recorded_failure"
    assert unrecoverable.batch is None
    assert buffer.snapshot("group:300") == ()
    assert [item.reason for item in buffer.diagnostics[-2:]] == [
        "detached_handoff_retry",
        "detached_handoff_failed",
    ]


def test_wait_path_has_no_hermes_side_effect_and_admission_orders_drain() -> None:
    """wait 只写 buffer；同 chat 的 admission 保证 wait/trigger 顺序。"""

    hermes_turns: list[FakeMessage] = []

    async def scenario() -> DetachedTriggerBatch[FakeMessage]:
        coordinator = ChatAdmissionCoordinator()
        buffer = WaitBuffer()
        leases = [
            coordinator.admit("group:300"),
            coordinator.admit("group:300"),
            coordinator.admit("group:300"),
        ]

        async with leases[0] as ticket:
            buffer.append("group:300", message(1), ingress_sequence=ticket.ingress_sequence)
        async with leases[1] as ticket:
            buffer.append("group:300", message(2), ingress_sequence=ticket.ingress_sequence)
        async with leases[2] as ticket:
            batch = buffer.drain(
                "group:300",
                message(3),
                ingress_sequence=ticket.ingress_sequence,
            )
            hermes_turns.append(batch.current)
            return batch

    batch = asyncio.run(scenario())

    assert batch.history == (message(1), message(2))
    assert hermes_turns == [message(3)]


def test_concurrent_drains_have_one_history_winner() -> None:
    """并发 drain 对同一 chat 只能让一个 batch 取得历史。"""

    buffer = WaitBuffer()
    buffer.append("group:300", message(1))

    with ThreadPoolExecutor(max_workers=2) as executor:
        batches = list(
            executor.map(
                lambda number: buffer.drain("group:300", message(number)),
                (2, 3),
            )
        )

    assert sum(bool(batch.history) for batch in batches) == 1
    assert sum(len(batch.history) for batch in batches) == 1
    assert buffer.snapshot("group:300") == ()
