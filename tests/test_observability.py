"""验证 Milky 运行时日志的事件、字段、级别和安全边界。"""

from __future__ import annotations

import ast
import asyncio
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import pytest

from config import load_config
from milky import observability
from milky.client import ActionError, MilkyClient, TransportResponse
from milky.observability import (
    ALLOWED_FIELDS,
    EVENT_NAMES,
    log_event,
    log_local_exception,
    mask_chat_key,
    mask_identifier,
    sanitize_fields,
)
from milky.resources import ResourceResolver
from session.buffer import DetachedTriggerBatch
from tests.fixtures.observability_inputs import (
    CORRELATION_FIXTURE,
    SENSITIVE_INPUTS,
    SYNTHETIC_IDENTIFIERS,
)
from will import RoutingConfig

SYNTHETIC_CREDENTIAL = "synthetic" + "-credential-value"
SYNTHETIC_AUTHORIZATION = "Bearer " + SYNTHETIC_CREDENTIAL

_PROJECT_ROOT = Path(__file__).parents[1]
_RUNTIME_SOURCE_FILES = (
    "__init__.py",
    "adapter.py",
    "config/__init__.py",
    "milky/client.py",
    "milky/event_stream.py",
    "milky/resources.py",
    "inbound/pipeline.py",
    "outbound/sender.py",
    "state/mute_tracker.py",
)
_DIRECT_LOG_METHODS = frozenset(
    {"debug", "info", "warning", "error", "exception", "critical", "log"}
)


def _record_dump(record: logging.LogRecord) -> str:
    """收集消息和结构化字段用于秘密扫描。"""

    return repr((record.getMessage(), record.__dict__))


def test_runtime_log_inventory_uses_registered_helper_and_cli_boundary() -> None:
    """运行时日志必须经过共享 helper，smoke 输出保持独立边界。"""

    for relative_path in _RUNTIME_SOURCE_FILES:
        source_path = _PROJECT_ROOT / relative_path
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"logger", "logging"}
                and node.func.attr in _DIRECT_LOG_METHODS
            ):
                pytest.fail(f"{relative_path} bypasses log_event with {node.func.attr}()")
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "log_event":
                continue
            if not isinstance(node.func, ast.Attribute):
                continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "log_event" or len(node.args) < 2:
                continue
            event_name = node.args[1]
            if isinstance(event_name, ast.Constant) and isinstance(event_name.value, str):
                assert event_name.value in EVENT_NAMES

    smoke_path = _PROJECT_ROOT / "scripts/milky_smoke.py"
    smoke_tree = ast.parse(smoke_path.read_text(encoding="utf-8"), filename=str(smoke_path))
    assert any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"
        for node in ast.walk(smoke_tree)
    )


def test_safe_fields_preserve_business_values_and_reject_unknown_values() -> None:
    """字段只能来自白名单，业务 ID 和 chat key 应保持原样。"""

    fields = sanitize_fields(
        {
            **CORRELATION_FIXTURE,
            "self_id": SYNTHETIC_IDENTIFIERS["self_id"],
            "message_id": SYNTHETIC_IDENTIFIERS["message_id"],
            "classification": "transport_unknown",
        }
    )

    assert fields["chat_key"] == CORRELATION_FIXTURE["chat_key"]
    assert fields["self_id"] == SYNTHETIC_IDENTIFIERS["self_id"]
    assert fields["message_id"] == SYNTHETIC_IDENTIFIERS["message_id"]
    fields = sanitize_fields(
        {
            "uid": SYNTHETIC_IDENTIFIERS["self_id"],
            "nickname": "合成机器人",
            "component": "mute_tracker",
            "member_mute": "muted",
            "whole_mute": "unknown",
        }
    )
    assert fields == {
        "uid": 900000001,
        "nickname": "合成机器人",
        "component": "mute_tracker",
        "member_mute": "muted",
        "whole_mute": "unknown",
    }
    assert set(fields) <= ALLOWED_FIELDS
    assert (
        sanitize_fields({"nickname": SENSITIVE_INPUTS["url"]})["nickname"]
        == SENSITIVE_INPUTS["url"]
    )
    assert sanitize_fields({"nickname": "900000001"})["nickname"] == "900000001"

    with pytest.raises(ValueError):
        sanitize_fields({"body": SENSITIVE_INPUTS["body"]})
    with pytest.raises(ValueError):
        sanitize_fields({"chat_key": "group:700000003/secret"})


def test_log_event_has_fixed_prefix_event_name_and_safe_fields(caplog) -> None:
    """规范日志应使用统一前缀、固定事件名和安全级别。"""

    logger = logging.getLogger("milky.observability")
    with caplog.at_level(logging.INFO, logger=logger.name):
        log_event(
            logger,
            "milky_inbound_trigger",
            logging.INFO,
            stage="will",
            scene="group",
            chat_key=CORRELATION_FIXTURE["chat_key"],
            ingress_sequence=CORRELATION_FIXTURE["ingress_sequence"],
            history_count=CORRELATION_FIXTURE["history_count"],
        )

    record = caplog.records[-1]
    assert record.getMessage().startswith("[Milky] ")
    assert record.event_name == "milky_inbound_trigger"
    assert record.levelno == logging.INFO
    assert record.chat_key == CORRELATION_FIXTURE["chat_key"]
    assert set(record.__dict__) >= ALLOWED_FIELDS.intersection(record.__dict__)

    with pytest.raises(ValueError):
        log_event(logger, "milky_inbound_trigger", message=SENSITIVE_INPUTS["body"])


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("chat_key", "group:700000001"),
        ("uid", 900000001),
        ("self_id", 900000001),
        ("sender_id", 800000002),
        ("peer_id", 700000001),
        ("group_id", 700000001),
        ("user_id", 800000002),
        ("message_id", "46244"),
        ("reference_id", "fixture-reference-001"),
        ("file_id", "fixture-file-id-raw"),
        ("nickname", "合成机器人"),
    ],
)
def test_human_log_preserves_all_business_field_values(
    field_name: str, field_value: object, caplog: pytest.LogCaptureFixture
) -> None:
    """人类日志应保留所有业务关联字段的原始值。"""

    logger = logging.getLogger(f"milky.observability.business.{field_name}")
    with caplog.at_level(logging.INFO, logger=logger.name):
        log_event(
            logger,
            "milky_inbound_wait",
            logging.INFO,
            stage="buffer",
            **{field_name: field_value},
        )

    records = [
        record
        for record in caplog.records
        if record.name == logger.name and record.event_name == "milky_inbound_wait"
    ]
    assert len(records) == 1
    assert getattr(records[0], field_name) == field_value
    assert str(field_value) in records[0].getMessage()


def test_log_event_renders_safe_fields_once(caplog) -> None:
    """helper 应用同一份安全字段生成可见消息和结构化记录。"""

    logger = logging.getLogger("milky.observability.single-render")
    with caplog.at_level(logging.INFO, logger=logger.name):
        log_event(
            logger,
            "milky_mute_initial_sync_succeeded",
            logging.INFO,
            stage="mute",
            scope="allowlist",
            total=3,
            succeeded=3,
            failed=0,
            muted=0,
            unmuted=0,
            unknown=3,
        )

    record = caplog.records[-1]
    message = record.getMessage()
    assert message == (
        "[Milky] Mute scan completed stage=mute scope=allowlist total=3 succeeded=3 "
        "failed=0 muted=0 unmuted=0 unknown=3 event_name=milky_mute_initial_sync_succeeded"
    )
    assert message.count("[Milky]") == 1
    for field in (
        "stage=mute",
        "scope=allowlist",
        "total=3",
        "succeeded=3",
        "failed=0",
        "muted=0",
        "unmuted=0",
        "unknown=3",
        "event_name=milky_mute_initial_sync_succeeded",
    ):
        assert message.split().count(field) == 1
    assert record.scope == "allowlist"
    assert record.total == 3
    assert record.event_name == "milky_mute_initial_sync_succeeded"


def test_log_records_do_not_contain_synthetic_sensitive_inputs(caplog) -> None:
    """合成凭证、URL、正文、路径和文件标识均不得进入日志。"""

    logger = logging.getLogger("milky.observability.safety")
    with caplog.at_level(logging.WARNING, logger=logger.name):
        log_event(
            logger,
            "milky_action_failed",
            logging.WARNING,
            stage="action",
            action="get_message",
            classification="transport_unknown",
            reason="connection_error",
            status_code=503,
            duration_ms=12.5,
            chat_key=CORRELATION_FIXTURE["chat_key"],
            file_id=SYNTHETIC_IDENTIFIERS["file_id"],
        )

    rendered = " ".join(_record_dump(record) for record in caplog.records)
    for value in SENSITIVE_INPUTS.values():
        assert value not in rendered
    assert str(SYNTHETIC_IDENTIFIERS["self_id"]) not in rendered
    assert str(SYNTHETIC_IDENTIFIERS["peer_id"]) in rendered
    assert SYNTHETIC_IDENTIFIERS["file_id"] in rendered


def test_local_traceback_requires_safe_exception_content(caplog) -> None:
    """本地安全异常可带 traceback，远端细节则不会记录。"""

    logger = logging.getLogger("milky.observability.exception")
    with caplog.at_level(logging.ERROR, logger=logger.name):
        safe = log_local_exception(
            logger,
            "milky_inbound_handoff_failed",
            RuntimeError("local invariant failed"),
            stage="handoff",
            classification="malformed",
            reason="handoff_failed",
        )
        unsafe = log_local_exception(
            logger,
            "milky_inbound_handoff_failed",
            RuntimeError(SENSITIVE_INPUTS["exception_detail"]),
            stage="handoff",
            classification="malformed",
            reason="handoff_failed",
        )

    assert safe is True
    assert unsafe is False
    assert len(caplog.records) == 1
    assert caplog.records[0].exc_info is not None
    assert caplog.records[0].exc_info[2] is None


def test_exception_chain_and_real_traceback_are_rejected(caplog) -> None:
    """异常链或真实 traceback 存在时不得输出异常详情。"""

    logger = logging.getLogger("milky.observability.exception-chain")
    chained = RuntimeError("safe outer")
    chained.__cause__ = RuntimeError(SENSITIVE_INPUTS["path"])
    with caplog.at_level(logging.ERROR, logger=logger.name):
        assert (
            log_local_exception(
                logger,
                "milky_inbound_handoff_failed",
                chained,
                stage="handoff",
                classification="malformed",
                reason="handoff_failed",
            )
            is False
        )

        try:
            raise RuntimeError("safe but has a traceback")
        except RuntimeError as error:
            assert (
                log_local_exception(
                    logger,
                    "milky_inbound_handoff_failed",
                    error,
                    stage="handoff",
                    classification="malformed",
                    reason="handoff_failed",
                )
                is False
            )

        assert (
            log_local_exception(
                logger,
                "milky_inbound_handoff_failed",
                RuntimeError("uid=900000001"),
                stage="handoff",
                classification="malformed",
                reason="handoff_failed",
            )
            is False
        )

    assert caplog.records == []


@dataclass
class _ActionTransport:
    """按顺序提供脱敏 HTTP fake 响应。"""

    responses: list[TransportResponse | BaseException]

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> TransportResponse:
        """记录参数形状但不让它们进入日志。"""

        del method, url, headers, body, timeout
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    async def close(self) -> None:
        """提供 client 所需的关闭边界。"""


def test_action_boundary_logs_safe_success_and_failure_classifications(caplog) -> None:
    """Action 统一边界应只记录 Action 名称、分类、状态和耗时。"""

    def response(payload: object, status_code: int = 200) -> TransportResponse:
        """构造 JSON fake 响应。"""

        import json

        return TransportResponse(status_code, json.dumps(payload).encode(), {})

    transport = _ActionTransport(
        [
            response({"status": "ok", "retcode": 0, "data": {"uin": 900000001}}),
            response({"status": "failed", "retcode": 100, "data": {}}),
            TransportResponse(200, b"remote payload " + SYNTHETIC_CREDENTIAL.encode(), {}),
            OSError("https://fixture.invalid Authorization " + SYNTHETIC_AUTHORIZATION),
        ]
    )
    client = MilkyClient(
        load_config(
            {
                "MILKY_BASE_URL": "https://fixture.invalid/milky",
                "MILKY_ACCESS_TOKEN": SYNTHETIC_CREDENTIAL,
            }
        ),
        transport=transport,
    )

    async def scenario() -> None:
        with caplog.at_level(logging.DEBUG, logger="milky.client"):
            await client.call("get_login_info")
            for _ in range(3):
                with pytest.raises(ActionError):
                    await client.call("get_login_info")

    asyncio.run(scenario())

    records = [record for record in caplog.records if record.name == "milky.client"]
    assert [record.event_name for record in records] == [
        "milky_action_succeeded",
        "milky_action_failed",
        "milky_action_failed",
        "milky_action_failed",
    ]
    assert [record.classification for record in records[1:]] == [
        "rejected",
        "malformed",
        "transport_unknown",
    ]
    assert [record.reason for record in records[1:]] == [
        "action_rejected",
        "malformed_response",
        "request_unknown",
    ]
    rendered = repr([(record.getMessage(), record.__dict__) for record in records])
    for value in (*SENSITIVE_INPUTS.values(), SYNTHETIC_CREDENTIAL, SYNTHETIC_AUTHORIZATION):
        assert value not in rendered


def test_inbound_wait_trigger_and_handoff_logs_are_correlatable(caplog) -> None:
    """wait 到 trigger 的日志应保留 chat 原值和 ingress 顺序。"""

    from tests.test_hermes_pipeline import FakeHermes, FakeResolver, load_fixture, make_pipeline

    async def scenario() -> None:
        hermes = FakeHermes()
        pipeline = make_pipeline(
            hermes,
            FakeResolver(),
            routing=RoutingConfig(all_message="wait"),
        )
        first = load_fixture("events/message_receive.group.all_segments.json")
        first["data"]["message_seq"] = 2001
        first["data"]["segments"] = [{"type": "text", "data": {"text": "历史敏感正文"}}]
        second = load_fixture("events/message_receive.group.all_segments.json")
        second["data"]["message_seq"] = 2002
        second["data"]["segments"] = [
            {"type": "mention", "data": {"user_id": 900000001, "name": "合成机器人"}},
            {"type": "text", "data": {"text": "触发敏感正文"}},
        ]
        await pipeline.handle_event(first)
        await pipeline.handle_event(second)
        await pipeline.wait_idle()

    with caplog.at_level(logging.DEBUG, logger="inbound.pipeline"):
        asyncio.run(scenario())

    records = [
        record
        for record in caplog.records
        if record.name == "inbound.pipeline"
        and getattr(record, "event_name", None)
        in {
            "milky_inbound_wait",
            "milky_inbound_trigger",
            "milky_inbound_drain",
            "milky_inbound_handoff_succeeded",
        }
    ]
    assert [record.event_name for record in records] == [
        "milky_inbound_wait",
        "milky_inbound_trigger",
        "milky_inbound_drain",
        "milky_inbound_handoff_succeeded",
    ]
    assert records[0].chat_key == records[1].chat_key == "group:700000001"
    assert records[0].ingress_sequence < records[1].ingress_sequence
    rendered = repr([(record.getMessage(), record.__dict__) for record in records])
    assert "chat_key[group:700000001]" in rendered
    assert "chat_key=group:700000001" not in rendered
    assert "历史敏感正文" not in rendered
    assert "触发敏感正文" not in rendered


def test_outbound_logs_route_chunks_and_safe_final_result(caplog, tmp_path) -> None:
    """出站日志应记录路由和计数，不记录正文、路径或文件名。"""

    from outbound.sender import MilkyOutboundSender
    from tests.test_outbound import FakeOutboundClient

    sender = MilkyOutboundSender(FakeOutboundClient([1, 2, 3, 4]), max_text_length=2)

    async def scenario() -> None:
        with caplog.at_level(logging.DEBUG, logger="outbound.sender"):
            await sender.send("group:700000001", "出站敏感正文")
            await sender.send_document(
                "group:700000001",
                "https://media.example.invalid/fixture-report.txt",
                file_name="fixture-report.txt",
            )

    asyncio.run(scenario())

    records = [record for record in caplog.records if record.name == "outbound.sender"]
    events = [record.event_name for record in records]
    assert "milky_outbound_route" in events
    assert "milky_outbound_chunked" in events
    assert "milky_outbound_succeeded" in events
    assert "milky_outbound_upload_succeeded" in events
    rendered = repr([(record.getMessage(), record.__dict__) for record in records])
    assert "出站敏感正文" not in rendered
    assert "media.example.invalid" not in rendered
    assert "sensitive-fixture-name.txt" not in rendered


def test_resource_resolution_logs_counts_without_references_or_body(caplog) -> None:
    """资源 resolver 只记录触发阶段计数和安全关联字段。"""

    from inbound.canonical import canonicalize_event
    from tests.test_resources import FakeHermesMedia, load_fixture, make_client

    canonical = canonicalize_event(
        load_fixture("events/message_receive.group.all_segments.json")
    ).value
    assert canonical is not None
    batch = DetachedTriggerBatch(
        canonical.chat_key,
        (canonical,),
        canonical,
        trigger_ingress_sequence=17,
    )
    resolver = ResourceResolver(
        make_client(),
        FakeHermesMedia(),
    )

    async def scenario() -> None:
        with caplog.at_level(logging.DEBUG, logger="milky.resources"):
            await resolver.resolve_batch(batch)

    asyncio.run(scenario())

    records = [record for record in caplog.records if record.name == "milky.resources"]
    assert [record.event_name for record in records] == [
        "milky_resource_resolution_started",
        "milky_resource_resolution_completed",
        "milky_resource_resolution_degraded",
    ]
    assert records[0].chat_key == "group:700000001"
    assert records[0].ingress_sequence == 17
    assert records[1].materialized_count >= 1
    rendered = repr([(record.getMessage(), record.__dict__) for record in records])
    assert "cdn.example.invalid" not in rendered
    assert "fixture-file-id" not in rendered
    assert "中性文本" not in rendered


def test_resource_degradation_logs_safe_classification_and_counts(caplog) -> None:
    """资源局部失败应记录降级分类和数量，而不记录远端引用。"""

    from inbound.canonical import canonicalize_event
    from milky.models import MilkyEnvelope
    from tests.test_resources import FakeHermesMedia, load_fixture, make_client

    canonical = canonicalize_event(
        load_fixture("events/message_receive.group.all_segments.json")
    ).value
    assert canonical is not None
    batch = DetachedTriggerBatch(canonical.chat_key, (), canonical, trigger_ingress_sequence=18)
    client = make_client()
    client.resource_response = MilkyEnvelope("ok", 0, {})
    resolver = ResourceResolver(client, FakeHermesMedia())

    async def scenario() -> None:
        with caplog.at_level(logging.DEBUG, logger="milky.resources"):
            await resolver.resolve_batch(batch)

    asyncio.run(scenario())

    degraded = [
        record
        for record in caplog.records
        if record.name == "milky.resources"
        and record.event_name == "milky_resource_resolution_degraded"
    ]
    assert len(degraded) == 1
    assert degraded[0].classification == "malformed"
    assert degraded[0].degraded_count >= 1
    rendered = repr([(record.getMessage(), record.__dict__) for record in degraded])
    assert "cdn.example.invalid" not in rendered
    assert "fixture-image-resource" not in rendered


def test_short_circuit_logs_do_not_claim_resource_or_handoff(caplog) -> None:
    """observe-only、重复、temp 和 Gate deny 应在资源前结束。"""

    from tests.test_hermes_pipeline import FakeHermes, FakeResolver, load_fixture, make_pipeline

    async def scenario() -> None:
        pipeline = make_pipeline(FakeHermes(), FakeResolver())
        event = load_fixture("events/message_receive.friend.json")
        await pipeline.handle_event(event)
        await pipeline.handle_event(event)
        denied = load_fixture("events/message_receive.friend.json")
        denied["data"]["message_seq"] = 1009
        denied["data"]["sender_id"] = 900000001
        denied["data"]["peer_id"] = 900000001
        denied["data"]["friend"]["user_id"] = 900000001
        await pipeline.handle_event(denied)
        await pipeline.handle_event(load_fixture("events/message_receive.temp.json"))
        await pipeline.handle_event(load_fixture("events/system.message_recall.json"))

    with caplog.at_level(logging.DEBUG, logger="inbound.pipeline"):
        asyncio.run(scenario())

    event_names = [
        record.event_name
        for record in caplog.records
        if record.name == "inbound.pipeline" and hasattr(record, "event_name")
    ]
    assert "milky_inbound_duplicate" in event_names
    assert "milky_inbound_gate_denied" in event_names
    assert "milky_inbound_temp_ignored" in event_names
    assert "milky_inbound_observe_only" in event_names
    assert "milky_inbound_handoff_succeeded" not in event_names


def test_observer_failure_has_a_dedicated_event(caplog) -> None:
    """observe-only handler 失败应独立记录且不伪装成普通消息失败。"""

    from tests.test_hermes_pipeline import FakeHermes, FakeResolver, load_fixture, make_pipeline

    def fail_observer(_event) -> None:
        """模拟安全观察器失败。"""

        raise RuntimeError("observer detail must not be logged")

    async def scenario() -> None:
        pipeline = make_pipeline(FakeHermes(), FakeResolver()).with_observer(fail_observer)
        await pipeline.handle_event(load_fixture("events/system.message_recall.json"))

    with caplog.at_level(logging.DEBUG, logger="inbound.pipeline"):
        asyncio.run(scenario())

    records = [
        record
        for record in caplog.records
        if record.name == "inbound.pipeline"
        and getattr(record, "event_name", None) == "milky_inbound_observer_failed"
    ]
    assert len(records) == 1
    assert records[0].classification == "handler_error"
    assert records[0].reason == "observer_failed"
    assert "observer detail must not be logged" not in repr(records[0].__dict__)


def test_mute_refresh_logs_success_and_failure_with_raw_group(caplog) -> None:
    """禁言刷新日志应区分成功/失败并保留群号原值。"""

    from state import MuteTracker
    from tests.test_mute_tracker import FakeMuteClient, member

    client = FakeMuteClient([700000001], member_results={700000001: member(700000001)})
    tracker = MuteTracker(client, clock=lambda: 100, refresh_cooldown=0)

    async def scenario() -> None:
        await tracker.initialize()
        await tracker.refresh_group(700000001)
        client.member_results[700000001] = ActionError(
            "transport_unknown", "member", "remote payload " + SYNTHETIC_CREDENTIAL
        )
        await tracker.refresh_group(700000001)

    with caplog.at_level(logging.INFO, logger="state.mute_tracker"):
        asyncio.run(scenario())

    records = [
        record
        for record in caplog.records
        if record.name == "state.mute_tracker"
        and record.event_name in {"milky_mute_refresh_succeeded", "milky_mute_refresh_failed"}
    ]
    assert [record.event_name for record in records] == [
        "milky_mute_refresh_succeeded",
        "milky_mute_refresh_failed",
    ]
    assert all(record.group_id == 700000001 for record in records)
    rendered = repr([(record.getMessage(), record.__dict__) for record in records])
    assert "remote payload synthetic-credential-value" not in rendered


def test_identifier_helpers_preserve_namespace_and_prefix_suffix() -> None:
    """兼容 helper 应保留可关联的命名空间和数字原值。"""

    assert mask_identifier(SYNTHETIC_IDENTIFIERS["self_id"]) == "900000001"
    assert mask_chat_key(CORRELATION_FIXTURE["chat_key"]) == "group:700000003"


def test_event_name_catalog_contains_required_boundaries() -> None:
    """事件名集合应覆盖 change 规定的所有关键边界。"""

    required = {
        "milky_adapter_ready",
        "milky_adapter_fatal_error_report_failed",
        "milky_action_succeeded",
        "milky_action_failed",
        "milky_event_stream_handler_failed",
        "milky_inbound_observe_only",
        "milky_inbound_duplicate",
        "milky_inbound_gate_denied",
        "milky_inbound_wait",
        "milky_inbound_trigger",
        "milky_inbound_handoff_succeeded",
        "milky_inbound_handoff_failed",
        "milky_inbound_observer_failed",
        "milky_resource_resolution_completed",
        "milky_resource_resolution_degraded",
        "milky_outbound_succeeded",
        "milky_outbound_failed",
        "milky_mute_refresh_succeeded",
        "milky_mute_refresh_failed",
    }
    assert required <= EVENT_NAMES


def test_slow_logging_handler_does_not_block_running_event_loop() -> None:
    """慢宿主 handler 不应阻塞调用方的事件循环。"""

    class SlowHandler(logging.Handler):
        """在后台线程中等待释放的测试 handler。"""

        def __init__(self) -> None:
            super().__init__()
            self.started = threading.Event()
            self.unblock = threading.Event()

        def emit(self, _record: logging.LogRecord) -> None:
            self.started.set()
            self.unblock.wait(1)

    logger = logging.getLogger("milky.observability.slow")
    handler = SlowHandler()
    old_propagate = logger.propagate
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:

        async def scenario() -> None:
            marker = asyncio.Event()
            log_event(
                logger,
                "milky_inbound_trigger",
                stage="will",
                scene="group",
                chat_key=CORRELATION_FIXTURE["chat_key"],
                ingress_sequence=1,
            )
            marker.set()
            await asyncio.sleep(0)
            assert marker.is_set()
            assert await asyncio.to_thread(handler.started.wait, 1)
            handler.unblock.set()
            await asyncio.sleep(0)

        asyncio.run(scenario())
    finally:
        handler.unblock.set()
        logger.removeHandler(handler)
        logger.propagate = old_propagate


def test_log_submission_capacity_drops_without_blocking_business(monkeypatch) -> None:
    """后台日志容量耗尽时不应阻塞业务，并记录受控丢弃计数。"""

    logger = logging.getLogger("milky.observability.capacity")
    logger.setLevel(logging.INFO)
    monkeypatch.setattr(observability, "_LOG_SUBMISSION_SLOTS", threading.BoundedSemaphore(0))
    before = observability._DROPPED_LOG_COUNTS[logging.INFO]

    async def scenario() -> None:
        marker = asyncio.Event()
        log_event(logger, "milky_adapter_ready", logging.INFO, stage="lifecycle")
        marker.set()
        await asyncio.sleep(0)
        assert marker.is_set()

    asyncio.run(scenario())

    assert observability._DROPPED_LOG_COUNTS[logging.INFO] == before + 1
