"""固定 Milky Tool Action 的窄执行接口。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import Any

from milky.client import ActionError


class FixedActionExecutor:
    """复用已绑定 client 执行固定 Action，不创建连接或重试。"""

    def __init__(self, client: object) -> None:
        self._client = client

    async def call(
        self,
        action: str,
        params: Mapping[str, object],
        fallback: Callable[[], Any],
    ) -> object:
        """优先调用 client 的固定 Tool 入口，测试 fake 时使用 typed fallback。"""

        call_tool = getattr(self._client, "call_tool", None)
        if callable(call_tool):
            return await _maybe_await(call_tool(action, params))
        return await _maybe_await(fallback())

    async def execute(
        self,
        action: str,
        params: Mapping[str, object],
        fallback: Callable[[], Any],
    ) -> object:
        """执行一次固定 Action，并把未确认结果降级为安全分类。"""

        try:
            return await self.call(action, params, fallback)
        except asyncio.CancelledError:
            raise
        except (ActionError, TypeError, ValueError) as error:
            return _failure(_error_classification(error), _safe_reason(error))
        except Exception:  # noqa: BLE001 - Tool 边界不回显底层异常
            return _failure("transport_unknown", "tool action outcome is unknown")


async def _maybe_await(value: Any) -> Any:
    """兼容同步 fake 与异步 client。"""

    if asyncio.iscoroutine(value) or isinstance(value, asyncio.Future):
        return await value
    return value


def _failure(kind: str, reason: str) -> Any:
    """创建 sender 使用的最小失败结果，避免依赖 sender 实现。"""

    # 延迟导入避免 fixed_actions 与 sender 的循环依赖。
    from .sender import OutboundSendResult

    return OutboundSendResult(False, error=reason, error_kind=kind)


def _error_classification(error: BaseException) -> str:
    """读取受控错误分类，未知异常统一归为 transport_unknown。"""

    classification = getattr(error, "classification", None)
    if classification in {"invalid_input", "unsupported", "transport_unknown"}:
        return classification
    return "transport_unknown"


def _safe_reason(error: BaseException) -> str:
    """只返回固定安全原因，不泄漏底层异常正文。"""

    classification = _error_classification(error)
    return {
        "invalid_input": "tool input is invalid",
        "unsupported": "tool is unavailable",
        "transport_unknown": "tool result is unknown",
    }[classification]
