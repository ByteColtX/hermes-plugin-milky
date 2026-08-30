"""Hermes 插件斜杠命令和 Milky client 生命周期交接。"""

from __future__ import annotations

import asyncio
import inspect
from threading import RLock

from milky.client import ActionError

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


class SlashCommandService:
    """提供固定的 ``/milky`` 命令并绑定活动 Milky client。"""

    def __init__(self) -> None:
        self._clients: list[object] = []
        self._lock = RLock()

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

    async def handle(self, raw_args: str) -> str:
        """处理无参数 ``/milky``，并只返回安全分类或完整成功 JSON。"""

        if not isinstance(raw_args, str) or raw_args.strip():
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
        return result

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


__all__ = ["SlashCommandService"]
