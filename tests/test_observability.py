"""验证 Milky 使用 Hermes 标准 logger 的最小可观察性契约。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from config import load_config
from milky.client import ActionError, MilkyClient, TransportResponse
from milky.logging import render_event

_PROJECT_ROOT = Path(__file__).parents[1]
_RUNTIME_SOURCE_FILES = (
    "adapter.py",
    "milky/client.py",
    "milky/event_stream.py",
    "milky/resources.py",
    "inbound/pipeline.py",
    "outbound/sender.py",
    "outbound/tools.py",
    "state/mute_tracker.py",
)


def test_private_observability_backend_is_removed() -> None:
    """运行时代码不得依赖旧安全日志后端或自定义事件 API。"""

    assert not (_PROJECT_ROOT / "milky/observability.py").exists()
    for relative_path in _RUNTIME_SOURCE_FILES:
        source = (_PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert "milky.observability" not in source
        assert "log_event" not in source
        assert "log_local_exception" not in source


def test_runtime_loggers_use_hermes_namespace() -> None:
    """组件 logger 使用 Hermes 可识别的命名空间且不安装私有 handler。"""

    logger_names = {
        "hermes_plugins.milky.adapter",
        "hermes_plugins.milky.client",
        "hermes_plugins.milky.event_stream",
        "hermes_plugins.milky.resources",
        "hermes_plugins.milky.inbound.pipeline",
        "hermes_plugins.milky.outbound.sender",
        "hermes_plugins.milky.outbound.tools",
        "hermes_plugins.milky.state.mute_tracker",
    }
    for name in logger_names:
        logger = logging.getLogger(name)
        assert logger.handlers == []
        assert logger.propagate is True


def test_standard_message_has_one_event_and_low_sensitivity_fields(caplog) -> None:
    """标准 logger 消息只表达一个事件和调用方确认的关联字段。"""

    logger = logging.getLogger("hermes_plugins.milky.test")
    with caplog.at_level(logging.INFO, logger=logger.name):
        logger.info(
            render_event(
                "milky.action",
                action="get_login_info",
                classification="accepted",
                status_code=200,
                duration_ms=3.5,
                chat_key="group:700000001",
            )
        )

    message = caplog.records[-1].getMessage()
    assert message == (
        "event=milky.action action=get_login_info classification=accepted status_code=200 "
        "duration_ms=3.5 chat_key=group:700000001"
    )
    assert "[Milky]" not in message


class _Transport:
    """提供不把请求细节交给日志的 Action fake。"""

    def __init__(self) -> None:
        self.responses = [
            TransportResponse(
                200,
                b'{"status":"ok","retcode":0,"data":{"uin":900000001}}',
                {},
            ),
            TransportResponse(503, b"body contains synthetic-token", {}),
        ]

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> TransportResponse:
        """返回预置响应但不记录请求参数。"""

        del method, url, headers, body, timeout
        return self.responses.pop(0)

    async def close(self) -> None:
        """提供关闭边界。"""


def test_action_logs_classification_status_duration_without_response_body(caplog) -> None:
    """Action 日志保留结果分类、状态码和耗时，不复制响应正文。"""

    client = MilkyClient(
        load_config(
            {
                "MILKY_BASE_URL": "https://fixture.invalid/milky",
                "MILKY_ACCESS_TOKEN": "synthetic-token",
            }
        ),
        transport=_Transport(),
    )

    async def scenario() -> None:
        with caplog.at_level(logging.DEBUG, logger="hermes_plugins.milky.client"):
            await client.call("get_login_info")
            try:
                await client.call("get_login_info")
            except ActionError:
                return

    asyncio.run(scenario())

    rendered = " ".join(record.getMessage() for record in caplog.records)
    assert "event=milky.action" in rendered
    assert "classification=accepted" in rendered
    assert "classification=http_error" in rendered
    assert "status_code=200" in rendered
    assert "status_code=503" in rendered
    assert "duration_ms=" in rendered
    assert "synthetic-token" not in rendered
    assert "body contains synthetic-token" not in rendered
    assert "https://fixture.invalid/milky" not in rendered


def test_log_level_and_handler_failures_do_not_change_action_result(monkeypatch) -> None:
    """禁用 logger 时 Action 仍返回同样的协议结果。"""

    client = MilkyClient(
        load_config(
            {
                "MILKY_BASE_URL": "https://fixture.invalid",
                "MILKY_ACCESS_TOKEN": "synthetic-token",
            }
        ),
        transport=_Transport(),
    )
    logger = logging.getLogger("hermes_plugins.milky.client")
    monkeypatch.setattr(logger, "disabled", True)

    result = asyncio.run(client.call("get_login_info"))

    assert result.status == "ok"
    assert result.retcode == 0
