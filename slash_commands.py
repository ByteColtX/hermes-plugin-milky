"""Hermes 插件斜杠命令和 Milky client 生命周期交接。"""

from __future__ import annotations

import asyncio
import inspect
import json
from threading import RLock

from command_text import format_usage
from management.allowlist import HELP, UNAVAILABLE, current_invocation, parse, usage_for
from milky.client import ActionError
from stickers.maintenance import StickerMaintenanceService

HELP_TEXT = """Milky · 命令帮助

Usage:
  /milky [command] [args...]

不带参数时查看实现信息。

Commands:
  status      查看运行状态
  sticker     维护贴纸库
  allowlist   管理会话白名单
  help        显示帮助

子命令帮助: /milky <command> help（sticker、allowlist）"""

_FAILURE_TEXT = {
    "unsupported": "Milky 信息暂不可用\n\n请检查插件连接状态后重试。",
    "rejected": "查询请求被拒绝\n\n请检查 Milky 服务的访问设置。",
    "malformed": "无法读取 Milky 信息\n\n服务返回的信息格式不正确。",
    "http_error": "Milky 服务请求失败\n\n请检查服务状态后重试。",
    "transport_unknown": "无法确认查询结果\n\n请检查连接状态后重新查询。",
    "invalid_input": "查询参数无效\n\n请检查插件与 Milky 服务的兼容性。",
}
STATUS_UNAVAILABLE = "运行状态暂不可用\n\n无法确认当前插件实例及其归属。"


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
            "Milky · 实现信息",
            "",
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
        self._status_providers: list[object] = []
        self._status_revision = 0
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

    def bind_status_provider(self, provider: object) -> None:
        """登记生命周期拥有的本地状态观察者。"""
        with self._lock:
            if not any(item is provider for item in self._status_providers):
                self._status_providers.append(provider)
                self._status_revision += 1

    def unbind_status_provider(self, provider: object) -> None:
        """解绑状态观察者并使等待中的读取失效。"""
        with self._lock:
            self._status_providers = [
                item for item in self._status_providers if item is not provider
            ]
            self._status_revision += 1

    async def _status(self) -> str:
        """只调用唯一观察者，并在等待后复核绑定代次。"""
        with self._lock:
            if len(self._status_providers) != 1:
                return STATUS_UNAVAILABLE
            provider = self._status_providers[0]
            revision = self._status_revision
        try:
            result = await provider.status()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - 状态错误不得暴露配置或异常正文
            return STATUS_UNAVAILABLE
        with self._lock:
            if revision != self._status_revision:
                return STATUS_UNAVAILABLE
        return result if isinstance(result, str) and result else STATUS_UNAVAILABLE

    async def handle(self, raw_args: str) -> str:
        """处理 ``/milky``，并只返回安全分类或格式化成功信息。"""

        if not isinstance(raw_args, str):
            return format_usage("/milky [command] [args...]", "/milky help")
        stripped = raw_args.strip()
        if stripped:
            parts = stripped.split()
            branch = parts[0].lower()
            if branch in {"help", "status"}:
                if len(parts) != 1:
                    return format_usage(f"/milky {branch}", "/milky help")
                return HELP_TEXT if branch == "help" else await self._status()
            if stripped.split(maxsplit=1)[0].lower() == "allowlist":
                try:
                    operation = parse(stripped)
                except (ValueError, TypeError):
                    return usage_for(stripped)
                if operation.verb == "help":
                    return HELP
                if len(self._managers) != 1:
                    return UNAVAILABLE
                return await self._managers[0].handle(operation, current_invocation.get())
            if stripped.split(maxsplit=1)[0].lower() == "sticker":
                return await self._sticker_service.handle(raw_args)
            return format_usage("/milky [command] [args...]", "/milky help")
        client = self._unique_client()
        if client is None:
            return self._failure("unsupported")
        method = getattr(client, "get_impl_info", None)
        if not callable(method):
            return self._failure("unsupported")
        try:
            result = method()
            if inspect.isawaitable(result):
                result = await result
        except asyncio.CancelledError:
            raise
        except ActionError as error:
            return self._failure(getattr(error, "classification", None))
        except Exception:  # noqa: BLE001 - 命令结果不得泄漏底层异常
            return self._failure("malformed")
        if not isinstance(result, str) or not result:
            return self._failure("malformed")
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

        if not isinstance(classification, str):
            classification = "malformed"
        return _FAILURE_TEXT.get(classification, _FAILURE_TEXT["malformed"])

    def close(self) -> None:
        """关闭命令 service 当前仍持有的贴纸操作资源。"""

        close = getattr(self._sticker_service, "close", None)
        if callable(close):
            close()


__all__ = ["SlashCommandService", "format_impl_info"]
