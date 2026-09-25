"""Hermes 插件斜杠命令和 Milky client 生命周期交接。"""

from __future__ import annotations

import asyncio
import inspect
import json
from threading import RLock

from management.allowlist import USAGE, current_invocation, parse
from milky.client import ActionError
from stickers.maintenance import StickerMaintenanceService

_SAFE_FAILURES = frozenset(
    {
        "rejected",
        "transport_unknown",
        "malformed",
        "unsupported",
        "invalid_input",
        "http_error",
    }
)

_IMPL_INFO_FIELDS = (
    "impl_name",
    "impl_version",
    "milky_version",
    "qq_protocol_type",
    "qq_protocol_version",
)


def format_impl_info(raw_response: str) -> str:
    """将已校验的 ``get_impl_info`` 响应转换为可读的中文摘要。"""

    try:
        payload = json.loads(raw_response)
    except (TypeError, json.JSONDecodeError):
        raise ActionError("malformed", "get_impl_info", "response is not valid JSON") from None

    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise ActionError("malformed", "get_impl_info", "response data is unavailable")

    data = payload["data"]
    if any(not isinstance(data.get(field), str) for field in _IMPL_INFO_FIELDS):
        raise ActionError("malformed", "get_impl_info", "response data is unavailable")

    return "\n".join(
        (
            "Milky 信息",
            f"实现: {data['impl_name']}",
            f"版本: {data['impl_version']}",
            f"Milky 版本: {data['milky_version']}",
            f"QQ 协议: {data['qq_protocol_type']} ({data['qq_protocol_version']})",
        )
    )


class SlashCommandService:
    """提供固定的 ``/milky`` 命令并绑定活动 Milky client。"""

    def __init__(self, sticker_service: StickerMaintenanceService | None = None) -> None:
        self._clients: list[object] = []
        self._managers: list[object] = []
        self._lock = RLock()
        self._sticker_service = sticker_service or StickerMaintenanceService()

    @property
    def active_client_count(self) -> int:
        """返回当前由 adapter 生命周期绑定的不同 client 数量。"""

        with self._lock:
            return len(self._clients)

    def bind_client(self, client: object) -> None:
        """登记一个已完成连接初始化的 client。"""

        if client is None:
            raise TypeError("client is required")
        with self._lock:
            if not any(candidate is client for candidate in self._clients):
                self._clients.append(client)

    def unbind_client(self, client: object) -> None:
        """解除一个 adapter 所拥有的 client，不影响其他活动 client。"""

        with self._lock:
            self._clients = [candidate for candidate in self._clients if candidate is not client]

    def bind_manager(self, manager) -> None:
        """登记当前活动实例，不把客户端数量当作 profile 身份。"""
        if manager not in self._managers:
            self._managers.append(manager)

    def unbind_manager(self, manager) -> None:
        """移除已停止实例并立即失效它的调用关联。"""
        manager.stop()
        if manager in self._managers:
            self._managers.remove(manager)

    async def handle(self, raw_args: str) -> str:
        """处理 ``/milky``，并只返回安全分类或格式化成功信息。"""

        if not isinstance(raw_args, str):
            return "invalid_input: usage: /milky"
        stripped = raw_args.strip()
        if stripped:
            if stripped.split(maxsplit=1)[0].lower() == "allowlist":
                try:
                    operation = parse(stripped)
                except (ValueError, TypeError):
                    return "invalid_input: " + USAGE
                if len(self._managers) != 1:
                    return "unsupported: 无唯一活动实例"
                return await self._managers[0].handle(operation, current_invocation.get())
            if stripped.split(maxsplit=1)[0].lower() == "sticker":
                return await self._sticker_service.handle(raw_args)
            return "invalid_input: usage: /milky"
        client = self._unique_client()
        if client is None:
            return "unsupported: no unique active Milky client"
        method = getattr(client, "get_impl_info", None)
        if not callable(method):
            return "unsupported: get_impl_info is unavailable"
        try:
            result = method()
            if inspect.isawaitable(result):
                result = await result
        except asyncio.CancelledError:
            raise
        except ActionError as error:
            return self._failure(getattr(error, "classification", None))
        except Exception:  # noqa: BLE001 - 命令结果不得泄漏底层异常
            return "malformed: get_impl_info failed"
        if not isinstance(result, str) or not result:
            return "malformed: get_impl_info response is unavailable"
        try:
            return format_impl_info(result)
        except ActionError as error:
            return self._failure(getattr(error, "classification", None))

    def _unique_client(self) -> object | None:
        with self._lock:
            return self._clients[0] if len(self._clients) == 1 else None

    @staticmethod
    def _failure(classification: object) -> str:
        """将 Action 失败压缩为不含响应正文的用户可见结果。"""

        safe = (
            classification
            if isinstance(classification, str) and classification in _SAFE_FAILURES
            else "malformed"
        )
        return f"{safe}: get_impl_info failed"

    def close(self) -> None:
        """关闭命令 service 当前仍持有的贴纸操作资源。"""

        close = getattr(self._sticker_service, "close", None)
        if callable(close):
            close()


__all__ = ["SlashCommandService", "format_impl_info"]
