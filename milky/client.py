"""Milky HTTP Action 客户端。

本模块只负责 HTTP 传输、通用 envelope 和 Action 的最小协议校验，不负责事件排序、
Gate、Will 或 Hermes 业务。默认 transport 延迟使用 Hermes 提供的 HTTPX，测试可以
注入 fake transport 而不建立真实连接。
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import stat
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Self
from urllib.parse import unquote, urlsplit

from config import MilkyConfig

from .models import (
    GroupEntity,
    GroupList,
    GroupMemberInfo,
    GroupMemberList,
    LoginInfo,
    MilkyEnvelope,
)
from .observability import log_event
from .parser import ParseError, parse_action_response, parse_envelope

_ACTION_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
_NON_NEGATIVE_INTEGER_PATTERN = re.compile(r"^(0|[1-9][0-9]*)$")
_MIN_QQ_ID = 10001
_MAX_QQ_ID = 4294967295
_MAX_SAFE_INTEGER = 9007199254740991
MAX_LOCAL_MEDIA_BYTES = 8 * 1024 * 1024
_TRANSPORT_PHASES = frozenset({"connect", "write", "read", "pool", "unknown"})
_TOOL_ACTIONS = frozenset(
    {
        "send_profile_like",
        "send_friend_nudge",
        "send_group_nudge",
        "recall_group_message",
        "get_group_info",
        "get_group_member_list",
        "get_group_member_info",
        "set_group_member_mute",
        "set_group_whole_mute",
        "get_forwarded_messages",
        "get_group_file_download_url",
        "get_group_files",
        "get_private_file_download_url",
        "accept_group_request",
        "reject_group_request",
        "accept_group_invitation",
        "reject_group_invitation",
        "kick_group_member",
        "quit_group",
        "delete_friend",
        "get_friend_requests",
        "get_friend_info",
        "accept_friend_request",
        "reject_friend_request",
        "set_group_member_special_title",
    }
)
_MISSING = object()

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TransportResponse:
    """保存已读取且已与底层连接分离的 HTTP 响应。"""

    status_code: int
    body: bytes
    headers: Mapping[str, str]


class HttpTransport(Protocol):
    """定义可注入的异步 HTTP transport。"""

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> TransportResponse:
        """执行一次已经编码好的 HTTP 请求。"""

    async def close(self) -> None:
        """释放 transport 资源。"""


class HttpxTransportError(OSError):
    """表示 HTTPX transport 不可用或网络请求结果未知。"""

    def __init__(
        self, reason: str = "request outcome is unknown", *, phase: str = "unknown"
    ) -> None:
        """保存安全的传输阶段，不保留底层异常文本。"""

        del reason
        self.phase = _safe_transport_phase(phase)
        super().__init__("request outcome is unknown")


def _import_httpx() -> Any:
    """延迟导入 Hermes 核心提供的 HTTPX。"""

    try:
        import httpx
    except ImportError:
        raise HttpxTransportError("httpx dependency is unavailable") from None
    return httpx


class HttpxTransport:
    """使用可复用的 HTTPX 异步客户端执行请求。"""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self._closed = False
        self._close_lock = asyncio.Lock()

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> TransportResponse:
        """使用有限的连接、写入、读取和连接池超时执行请求。"""

        if self._closed:
            raise HttpxTransportError("transport is closed")
        httpx = _import_httpx()
        if self._client is None:
            self._client = httpx.AsyncClient()
        request_timeout = httpx.Timeout(
            timeout,
            connect=timeout,
            read=timeout,
            write=timeout,
            pool=timeout,
        )
        try:
            response = await self._client.request(
                method,
                url,
                headers=headers,
                content=body,
                timeout=request_timeout,
            )
            try:
                return TransportResponse(
                    response.status_code,
                    response.content,
                    dict(response.headers),
                )
            finally:
                await response.aclose()
        except asyncio.CancelledError:
            raise
        except httpx.HTTPError as error:
            raise HttpxTransportError(phase=_httpx_transport_phase(httpx, error)) from None

    async def close(self) -> None:
        """幂等关闭 HTTPX 连接池。"""

        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
            if self._client is None:
                return
            try:
                await self._client.aclose()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - 关闭失败统一归类为 transport 错误
                raise HttpxTransportError("transport close failed") from None


class ActionError(Exception):
    """表示 Action 输入、传输、HTTP 或协议结果不可用。"""

    def __init__(
        self,
        classification: str,
        action: str,
        reason: str,
        *,
        phase: str | None = None,
    ) -> None:
        self.classification = classification
        self.action = action
        self.reason = reason
        self.phase = _safe_transport_phase(phase) if phase is not None else None
        super().__init__(f"{classification}: {action}: {reason}")


# 供调用方按更具体的名称导入，同时保持唯一的错误语义。
MilkyActionError = ActionError


async def materialize_media_uri(value: object, *, action: str = "media") -> str:
    """将远端、内联或受限本地资源转换为 Milky URI。"""

    return await asyncio.to_thread(_materialize_media_uri, value, action)


def validate_media_uri(value: object, *, action: str = "media") -> str:
    """只接受远端或显式内联资源 URI。

    本函数不读取本地文件、不下载远端内容，也不生成新的 ``base64://`` URI。
    """

    if not isinstance(value, str):
        raise ActionError("unsupported", action, "Hermes resource entry is unavailable")
    raw = value.strip()
    if not raw:
        raise ActionError("invalid_input", action, "media URI is invalid")
    try:
        parsed = urlsplit(raw)
    except ValueError:
        raise ActionError("invalid_input", action, "media URI is invalid") from None
    if parsed.scheme in {"http", "https"}:
        if not parsed.netloc:
            raise ActionError("invalid_input", action, "media URI is invalid")
        return raw
    if parsed.scheme == "base64" and raw.startswith("base64://"):
        if parsed.netloc or parsed.path:
            return raw
        raise ActionError("invalid_input", action, "media URI is invalid")
    raise ActionError("unsupported", action, "Hermes resource entry is unavailable")


def _materialize_media_uri(value: object, action: str) -> str:
    """在工作线程中执行 URI 校验或一次性本地文件读取。"""

    if isinstance(value, Path):
        raw = str(value).strip()
    elif isinstance(value, str):
        raw = value.strip()
    else:
        raise ActionError("invalid_input", action, "media URI is invalid")
    if not raw:
        raise ActionError("invalid_input", action, "media URI is invalid")

    try:
        parsed = urlsplit(raw)
    except ValueError:
        raise ActionError("invalid_input", action, "media URI is invalid") from None
    if parsed.scheme in {"http", "https", "base64"}:
        return validate_media_uri(raw, action=action)
    if parsed.scheme == "file":
        if parsed.netloc.casefold() not in {"", "localhost"} or not parsed.path:
            raise ActionError("invalid_input", action, "media URI is invalid")
        raw = unquote(parsed.path)
    elif parsed.scheme:
        raise ActionError("unsupported", action, "media URI scheme is unsupported")

    return _local_file_as_base64_uri(raw, action)


def _local_file_as_base64_uri(file_path: object, action: str) -> str:
    """将一个安全的本地常规文件编码为受限 Base64 URI。"""

    try:
        path = Path(file_path).expanduser()
        resolved = path.resolve(strict=True)
        with resolved.open("rb") as stream:
            file_stat = os.fstat(stream.fileno())
            if not stat.S_ISREG(file_stat.st_mode):
                raise ActionError("invalid_input", action, "file path is unavailable")
            if file_stat.st_size > MAX_LOCAL_MEDIA_BYTES:
                raise ActionError("invalid_input", action, "media file is too large")
            data = stream.read(MAX_LOCAL_MEDIA_BYTES + 1)
    except ActionError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError):
        raise ActionError("invalid_input", action, "file path is unavailable") from None
    if len(data) > MAX_LOCAL_MEDIA_BYTES:
        raise ActionError("invalid_input", action, "media file is too large")
    if not data:
        raise ActionError("invalid_input", action, "media file is empty")
    return "base64://" + base64.b64encode(data).decode("ascii")


@dataclass(frozen=True, slots=True)
class SendResult:
    """保存 Milky send Action 返回的稳定远端消息序号。"""

    message_id: str


class MilkyClient:
    """调用 Milky HTTP Action 的最小客户端。"""

    def __init__(
        self,
        config: MilkyConfig,
        transport: HttpTransport | None = None,
        *,
        timeout: float = 10.0,
    ) -> None:
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            raise ValueError("timeout must be a positive number")
        self._config = config
        self._transport = transport or HttpxTransport()
        self._timeout = float(timeout)
        self._closed = False

    async def call(
        self,
        action: str,
        params: Mapping[str, Any] | None = None,
    ) -> MilkyEnvelope:
        """发送一次 Action 并返回已校验的成功 envelope。"""
        envelope, _ = await self._call_raw(action, params)
        return envelope

    async def _call_raw(
        self,
        action: str,
        params: Mapping[str, Any] | None = None,
    ) -> tuple[MilkyEnvelope, bytes]:
        """发送 Action 并保留已校验响应的 UTF-8 字节。"""

        started = time.perf_counter()
        status_code: int | None = None
        safe_action = _safe_log_action(action)
        try:
            if self._closed:
                raise ActionError("transport_unknown", safe_action, "client is closed")
            if not isinstance(action, str) or _ACTION_PATTERN.fullmatch(action) is None:
                raise ActionError("invalid_input", "invalid", "invalid action name")
            if params is None:
                request_params: Mapping[str, Any] = {}
            elif isinstance(params, Mapping):
                request_params = params
            else:
                raise ActionError("invalid_input", action, "parameters must be an object")
            try:
                body = json.dumps(
                    dict(request_params), ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
            except (TypeError, ValueError):
                raise ActionError(
                    "invalid_input", action, "parameters are not JSON serializable"
                ) from None

            try:
                response = await self._transport.request(
                    "POST",
                    self._config.action_url(action),
                    {**self._config.auth_headers, "Content-Type": "application/json"},
                    body,
                    self._timeout,
                )
            except asyncio.CancelledError:
                raise
            except (TimeoutError, OSError) as error:
                raise ActionError(
                    "transport_unknown",
                    action,
                    "request outcome is unknown",
                    phase=_safe_transport_phase(getattr(error, "phase", "unknown")),
                ) from None
            except Exception:  # noqa: BLE001 - transport details are never exposed
                raise ActionError(
                    "transport_unknown", action, "request outcome is unknown", phase="unknown"
                ) from None

            if not isinstance(response, TransportResponse):
                raise ActionError("malformed", action, "transport returned an invalid response")
            status_code = response.status_code
            if not 200 <= response.status_code < 300:
                raise ActionError("http_error", action, "HTTP status is not successful")
            payload = self._decode_json(response.body, action)
            try:
                envelope = parse_envelope(payload)
            except ParseError:
                raise ActionError("malformed", action, "response envelope is malformed") from None
            if envelope.status != "ok" or envelope.retcode != 0:
                raise ActionError("rejected", action, "Milky Action envelope rejected")
            if not isinstance(envelope.data, Mapping):
                raise ActionError("malformed", action, "response data is malformed")
            if action == "get_impl_info":
                _validate_impl_info_data(envelope.data, action)
            log_event(
                logger,
                "milky_action_succeeded",
                logging.INFO,
                stage="action",
                action=action,
                status_code=status_code,
                duration_ms=_duration_ms(started),
            )
            return envelope, _response_body_bytes(response.body, action)
        except asyncio.CancelledError:
            raise
        except ActionError as error:
            failure_fields: dict[str, object] = {
                "stage": "action",
                "action": _safe_log_action(error.action),
                "classification": _safe_action_classification(error.classification),
                "reason": _safe_action_reason(error.classification),
                "duration_ms": _duration_ms(started),
            }
            if status_code is not None:
                failure_fields["status_code"] = status_code
            if error.phase is not None:
                failure_fields["transport_phase"] = error.phase
            log_event(
                logger,
                "milky_action_failed",
                logging.WARNING,
                **failure_fields,
            )
            raise

    async def action(
        self,
        action: str,
        params: Mapping[str, Any] | None = None,
    ) -> MilkyEnvelope:
        """以兼容名称调用通用 Action。"""

        return await self.call(action, params)

    async def call_tool(
        self,
        action: str,
        params: Mapping[str, Any] | None = None,
    ) -> MilkyEnvelope:
        """调用已注册 Tool 并返回完整 raw envelope。"""

        if action not in _TOOL_ACTIONS:
            raise ActionError("unsupported", action, "Action is not registered as a Tool")
        _validate_tool_params(action, params)
        envelope = await self.call(action, params)
        _validate_tool_response(action, envelope)
        return envelope

    async def get_impl_info(self) -> str:
        """获取并原样返回已校验的 ``get_impl_info`` JSON 响应。"""

        _, body = await self._call_raw("get_impl_info", {})
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            # ``_call_raw`` 已经完成 JSON 解码；此分支只防止未来 transport 改变
            # body 类型后把底层解码细节泄漏给命令调用方。
            raise ActionError("malformed", "get_impl_info", "response is not valid UTF-8") from None

    async def get_login_info(self) -> LoginInfo:
        """获取登录身份并校验 ``data.uin``。"""

        envelope = await self.call("get_login_info")
        result = self._parse_typed(envelope, "get_login_info")
        assert isinstance(result, LoginInfo)
        return result

    async def get_group_list(self) -> GroupList:
        """获取群列表并校验 ``data.groups``。"""

        envelope = await self.call("get_group_list")
        result = self._parse_typed(envelope, "get_group_list")
        assert isinstance(result, GroupList)
        return result

    async def get_group_info(
        self, group_id: object, *, no_cache: bool | None = False
    ) -> GroupEntity:
        """获取群信息，并按需绕过 Milky 缓存。"""

        group_value = _validate_id(
            group_id,
            "group_id",
            "get_group_info",
            minimum=_MIN_QQ_ID,
            maximum=_MAX_QQ_ID,
        )
        if no_cache is not None and not isinstance(no_cache, bool):
            raise ActionError("invalid_input", "get_group_info", "no_cache is invalid")
        params: dict[str, Any] = {"group_id": group_value}
        if no_cache is not False:
            params["no_cache"] = no_cache
        envelope = await self.call("get_group_info", params)
        result = self._parse_typed(envelope, "get_group_info")
        assert isinstance(result, GroupEntity)
        return result

    async def get_group_member_list(
        self, group_id: object, *, no_cache: bool | None = False
    ) -> GroupMemberList:
        """获取群成员列表，并按需绕过 Milky 缓存。"""

        group_value = _validate_id(
            group_id,
            "group_id",
            "get_group_member_list",
            minimum=_MIN_QQ_ID,
            maximum=_MAX_QQ_ID,
        )
        if no_cache is not None and not isinstance(no_cache, bool):
            raise ActionError("invalid_input", "get_group_member_list", "no_cache is invalid")
        params: dict[str, Any] = {"group_id": group_value}
        if no_cache is not False:
            params["no_cache"] = no_cache
        envelope = await self.call("get_group_member_list", params)
        result = self._parse_typed(envelope, "get_group_member_list")
        assert isinstance(result, GroupMemberList)
        return result

    async def get_group_member_info(
        self,
        group_id: object,
        user_id: object,
        *,
        no_cache: bool | None = False,
    ) -> GroupMemberInfo:
        """获取指定群的成员信息，并按需绕过 Milky 缓存。"""

        group_value = _validate_id(
            group_id,
            "group_id",
            "get_group_member_info",
            minimum=_MIN_QQ_ID,
            maximum=_MAX_QQ_ID,
        )
        user_value = _validate_id(
            user_id,
            "user_id",
            "get_group_member_info",
            minimum=_MIN_QQ_ID,
            maximum=_MAX_QQ_ID,
        )
        if no_cache is not None and not isinstance(no_cache, bool):
            raise ActionError("invalid_input", "get_group_member_info", "no_cache is invalid")
        params: dict[str, Any] = {"group_id": group_value, "user_id": user_value}
        if no_cache is not False:
            params["no_cache"] = no_cache
        envelope = await self.call("get_group_member_info", params)
        result = self._parse_typed(envelope, "get_group_member_info")
        assert isinstance(result, GroupMemberInfo)
        return result

    async def set_group_member_mute(
        self,
        group_id: object,
        user_id: object,
        duration: object = _MISSING,
    ) -> MilkyEnvelope:
        """设置群成员禁言状态；``duration=0`` 表示取消禁言。"""

        params: dict[str, Any] = {
            "group_id": _validate_id(
                group_id,
                "group_id",
                "set_group_member_mute",
                minimum=_MIN_QQ_ID,
                maximum=_MAX_QQ_ID,
            ),
            "user_id": _validate_id(
                user_id,
                "user_id",
                "set_group_member_mute",
                minimum=_MIN_QQ_ID,
                maximum=_MAX_QQ_ID,
            ),
        }
        if duration is not _MISSING:
            params["duration"] = (
                None
                if duration is None
                else _validate_id(
                    duration,
                    "duration",
                    "set_group_member_mute",
                    maximum=_MAX_SAFE_INTEGER,
                )
            )
        return await self.call("set_group_member_mute", params)

    async def set_group_whole_mute(
        self, group_id: object, is_mute: object = _MISSING
    ) -> MilkyEnvelope:
        """设置群全员禁言状态。"""

        params: dict[str, Any] = {
            "group_id": _validate_id(
                group_id,
                "group_id",
                "set_group_whole_mute",
                minimum=_MIN_QQ_ID,
                maximum=_MAX_QQ_ID,
            )
        }
        if is_mute is not _MISSING:
            if is_mute is not None and not isinstance(is_mute, bool):
                raise ActionError("invalid_input", "set_group_whole_mute", "is_mute is invalid")
            params["is_mute"] = is_mute
        return await self.call("set_group_whole_mute", params)

    async def send_group_message(self, group_id: object, message: object) -> SendResult:
        """向群发送 segments，并只接受远端 ``message_seq``。"""

        group_value = _validate_id(
            group_id,
            "group_id",
            "send_group_message",
            minimum=_MIN_QQ_ID,
            maximum=_MAX_QQ_ID,
        )
        message_value = _validate_segments(message, "send_group_message")
        envelope = await self.call(
            "send_group_message",
            {"group_id": group_value, "message": message_value},
        )
        return _parse_send_result(envelope, "send_group_message")

    async def send_private_message(self, user_id: object, message: object) -> SendResult:
        """向好友发送 segments，并只接受远端 ``message_seq``。"""

        user_value = _validate_id(
            user_id,
            "user_id",
            "send_private_message",
            minimum=_MIN_QQ_ID,
            maximum=_MAX_QQ_ID,
        )
        message_value = _validate_segments(message, "send_private_message")
        envelope = await self.call(
            "send_private_message",
            {"user_id": user_value, "message": message_value},
        )
        return _parse_send_result(envelope, "send_private_message")

    async def send_profile_like(self, user_id: object, count: object = _MISSING) -> MilkyEnvelope:
        """向好友发送名片点赞，并校验 Action 的对象响应。"""

        params: dict[str, Any] = {
            "user_id": _validate_id(
                user_id,
                "user_id",
                "send_profile_like",
                minimum=_MIN_QQ_ID,
                maximum=_MAX_QQ_ID,
            )
        }
        if count is not _MISSING:
            params["count"] = (
                None
                if count is None
                else _validate_id(
                    count,
                    "count",
                    "send_profile_like",
                    maximum=_MAX_SAFE_INTEGER,
                )
            )
        return await self.call("send_profile_like", params)

    async def send_friend_nudge(self, user_id: object, is_self: object = _MISSING) -> MilkyEnvelope:
        """向好友发送戳一戳，并校验可选的 ``is_self``。"""

        params: dict[str, Any] = {
            "user_id": _validate_id(
                user_id,
                "user_id",
                "send_friend_nudge",
                minimum=_MIN_QQ_ID,
                maximum=_MAX_QQ_ID,
            )
        }
        if is_self is not _MISSING:
            if is_self is not None and not isinstance(is_self, bool):
                raise ActionError("invalid_input", "send_friend_nudge", "is_self is invalid")
            params["is_self"] = is_self
        return await self.call("send_friend_nudge", params)

    async def send_group_nudge(self, group_id: object, user_id: object) -> MilkyEnvelope:
        """向群成员发送戳一戳。"""

        params = {
            "group_id": _validate_id(
                group_id,
                "group_id",
                "send_group_nudge",
                minimum=_MIN_QQ_ID,
                maximum=_MAX_QQ_ID,
            ),
            "user_id": _validate_id(
                user_id,
                "user_id",
                "send_group_nudge",
                minimum=_MIN_QQ_ID,
                maximum=_MAX_QQ_ID,
            ),
        }
        return await self.call("send_group_nudge", params)

    async def recall_group_message(self, group_id: object, message_seq: object) -> MilkyEnvelope:
        """撤回群消息；调用方负责决定是否再次尝试。"""

        params = {
            "group_id": _validate_id(
                group_id,
                "group_id",
                "recall_group_message",
                minimum=_MIN_QQ_ID,
                maximum=_MAX_QQ_ID,
            ),
            "message_seq": _validate_id(
                message_seq,
                "message_seq",
                "recall_group_message",
                maximum=_MAX_SAFE_INTEGER,
            ),
        }
        return await self.call("recall_group_message", params)

    async def get_message(
        self, message_scene: object, peer_id: object, message_seq: object
    ) -> MilkyEnvelope:
        """按场景、会话对象和远端消息序号查询完整消息。"""

        scene = _validate_message_scene(message_scene, "get_message")
        peer_value = _validate_id(
            peer_id,
            "peer_id",
            "get_message",
            minimum=_MIN_QQ_ID,
            maximum=_MAX_QQ_ID,
        )
        sequence = _validate_id(
            message_seq,
            "message_seq",
            "get_message",
            maximum=_MAX_SAFE_INTEGER,
        )
        return await self.call(
            "get_message",
            {"message_scene": scene, "peer_id": peer_value, "message_seq": sequence},
        )

    async def get_forwarded_messages(self, forward_id: object) -> MilkyEnvelope:
        """按 forward ID 查询完整转发内容。"""

        envelope = await self.call(
            "get_forwarded_messages",
            {"forward_id": _validate_text(forward_id, "forward_id", "get_forwarded_messages")},
        )
        _validate_tool_response("get_forwarded_messages", envelope)
        return envelope

    async def get_resource_temp_url(self, resource_id: object) -> MilkyEnvelope:
        """按资源 ID 查询临时引用地址。"""

        return await self.call(
            "get_resource_temp_url",
            {"resource_id": _validate_text(resource_id, "resource_id", "get_resource_temp_url")},
        )

    async def get_group_file_download_url(self, group_id: object, file_id: object) -> MilkyEnvelope:
        """按群号和文件 ID 查询群文件下载地址。"""

        envelope = await self.call(
            "get_group_file_download_url",
            {
                "group_id": _validate_id(
                    group_id,
                    "group_id",
                    "get_group_file_download_url",
                    minimum=_MIN_QQ_ID,
                    maximum=_MAX_QQ_ID,
                ),
                "file_id": _validate_text(file_id, "file_id", "get_group_file_download_url"),
            },
        )
        _validate_tool_response("get_group_file_download_url", envelope)
        return envelope

    async def get_group_files(
        self,
        group_id: object,
        *,
        parent_folder_id: object = _MISSING,
    ) -> MilkyEnvelope:
        """查询群文件和文件夹列表，并保留完整协议 envelope。"""

        params: dict[str, Any] = {
            "group_id": _validate_tool_integer(
                group_id,
                "group_id",
                "get_group_files",
                minimum=_MIN_QQ_ID,
                maximum=_MAX_QQ_ID,
            )
        }
        if parent_folder_id is not _MISSING:
            params["parent_folder_id"] = _validate_optional_nonempty_tool_text(
                parent_folder_id, "parent_folder_id", "get_group_files"
            )
        envelope = await self.call("get_group_files", params)
        _validate_tool_response("get_group_files", envelope)
        return envelope

    async def accept_group_request(
        self,
        notification_seq: object,
        notification_type: object,
        group_id: object,
        *,
        is_filtered: object = _MISSING,
    ) -> MilkyEnvelope:
        """接受入群请求；只在调用方明确提供完整参数时提交。"""

        params = _group_request_params(
            "accept_group_request",
            notification_seq,
            notification_type,
            group_id,
            is_filtered=is_filtered,
        )
        envelope = await self.call("accept_group_request", params)
        _validate_tool_response("accept_group_request", envelope)
        return envelope

    async def reject_group_request(
        self,
        notification_seq: object,
        notification_type: object,
        group_id: object,
        *,
        is_filtered: object = _MISSING,
        reason: object = _MISSING,
    ) -> MilkyEnvelope:
        """拒绝入群请求；reason 仅作为明确的协议参数传递。"""

        params = _group_request_params(
            "reject_group_request",
            notification_seq,
            notification_type,
            group_id,
            is_filtered=is_filtered,
        )
        if reason is not _MISSING:
            params["reason"] = _validate_optional_nonempty_tool_text(
                reason, "reason", "reject_group_request"
            )
        envelope = await self.call("reject_group_request", params)
        _validate_tool_response("reject_group_request", envelope)
        return envelope

    async def accept_group_invitation(
        self, group_id: object, invitation_seq: object
    ) -> MilkyEnvelope:
        """接受群邀请；只在显式调用时提交一次。"""

        params = {
            "group_id": _validate_tool_integer(
                group_id,
                "group_id",
                "accept_group_invitation",
                minimum=_MIN_QQ_ID,
                maximum=_MAX_QQ_ID,
            ),
            "invitation_seq": _validate_tool_integer(
                invitation_seq,
                "invitation_seq",
                "accept_group_invitation",
            ),
        }
        envelope = await self.call("accept_group_invitation", params)
        _validate_tool_response("accept_group_invitation", envelope)
        return envelope

    async def reject_group_invitation(
        self, group_id: object, invitation_seq: object
    ) -> MilkyEnvelope:
        """拒绝群邀请；只在显式调用时提交一次。"""

        params = {
            "group_id": _validate_tool_integer(
                group_id,
                "group_id",
                "reject_group_invitation",
                minimum=_MIN_QQ_ID,
                maximum=_MAX_QQ_ID,
            ),
            "invitation_seq": _validate_tool_integer(
                invitation_seq,
                "invitation_seq",
                "reject_group_invitation",
            ),
        }
        envelope = await self.call("reject_group_invitation", params)
        _validate_tool_response("reject_group_invitation", envelope)
        return envelope

    async def get_private_file_download_url(
        self,
        user_id: object,
        file_id: object,
        file_hash: object,
        *,
        is_self_send: object = _MISSING,
    ) -> MilkyEnvelope:
        """按用户号、文件 ID 和 hash 查询私聊文件下载地址。"""

        params: dict[str, Any] = {
            "user_id": _validate_tool_integer(
                user_id,
                "user_id",
                "get_private_file_download_url",
                minimum=_MIN_QQ_ID,
                maximum=_MAX_QQ_ID,
            ),
            "file_id": _validate_text(file_id, "file_id", "get_private_file_download_url"),
            "file_hash": _validate_text(file_hash, "file_hash", "get_private_file_download_url"),
        }
        if is_self_send is not _MISSING:
            if is_self_send is not None and not isinstance(is_self_send, bool):
                raise ActionError(
                    "invalid_input",
                    "get_private_file_download_url",
                    "is_self_send is invalid",
                )
            params["is_self_send"] = is_self_send
        envelope = await self.call(
            "get_private_file_download_url",
            params,
        )
        _validate_tool_response("get_private_file_download_url", envelope)
        return envelope

    async def kick_group_member(
        self,
        group_id: object,
        user_id: object,
        *,
        reject_add_request: object = _MISSING,
    ) -> MilkyEnvelope:
        """将群成员移出群聊；调用方负责确认高影响操作。"""

        params: dict[str, Any] = {
            "group_id": _validate_tool_integer(
                group_id,
                "group_id",
                "kick_group_member",
                minimum=_MIN_QQ_ID,
                maximum=_MAX_QQ_ID,
            ),
            "user_id": _validate_tool_integer(
                user_id,
                "user_id",
                "kick_group_member",
                minimum=_MIN_QQ_ID,
                maximum=_MAX_QQ_ID,
            ),
        }
        if reject_add_request is not _MISSING:
            if reject_add_request is not None and not isinstance(reject_add_request, bool):
                raise ActionError(
                    "invalid_input", "kick_group_member", "reject_add_request is invalid"
                )
            params["reject_add_request"] = reject_add_request
        envelope = await self.call("kick_group_member", params)
        _validate_tool_response("kick_group_member", envelope)
        return envelope

    async def quit_group(self, group_id: object) -> MilkyEnvelope:
        """退出指定群聊；调用方负责确认高影响操作。"""

        envelope = await self.call(
            "quit_group",
            {
                "group_id": _validate_tool_integer(
                    group_id,
                    "group_id",
                    "quit_group",
                    minimum=_MIN_QQ_ID,
                    maximum=_MAX_QQ_ID,
                )
            },
        )
        _validate_tool_response("quit_group", envelope)
        return envelope

    async def delete_friend(self, user_id: object) -> MilkyEnvelope:
        """删除好友关系；调用方负责确认高影响操作。"""

        envelope = await self.call(
            "delete_friend",
            {
                "user_id": _validate_tool_integer(
                    user_id,
                    "user_id",
                    "delete_friend",
                    minimum=_MIN_QQ_ID,
                    maximum=_MAX_QQ_ID,
                )
            },
        )
        _validate_tool_response("delete_friend", envelope)
        return envelope

    async def get_friend_requests(
        self,
        *,
        limit: object = _MISSING,
        is_filtered: object = _MISSING,
    ) -> MilkyEnvelope:
        """查询好友请求列表并保留原始协议 envelope。"""

        params: dict[str, Any] = {}
        if limit is not _MISSING:
            params["limit"] = (
                None
                if limit is None
                else _validate_tool_integer(
                    limit,
                    "limit",
                    "get_friend_requests",
                    maximum=_MAX_SAFE_INTEGER,
                )
            )
        if is_filtered is not _MISSING:
            if is_filtered is not None and not isinstance(is_filtered, bool):
                raise ActionError("invalid_input", "get_friend_requests", "is_filtered is invalid")
            params["is_filtered"] = is_filtered
        envelope = await self.call("get_friend_requests", params)
        _validate_tool_response("get_friend_requests", envelope)
        return envelope

    async def get_friend_info(self, user_id: object) -> MilkyEnvelope:
        """查询指定好友信息，并保留目标服务返回的 opaque object。"""

        envelope = await self.call(
            "get_friend_info",
            {
                "user_id": _validate_tool_integer(
                    user_id,
                    "user_id",
                    "get_friend_info",
                    minimum=_MIN_QQ_ID,
                    maximum=_MAX_QQ_ID,
                )
            },
        )
        _validate_tool_response("get_friend_info", envelope)
        return envelope

    async def accept_friend_request(
        self,
        initiator_uid: object,
        *,
        is_filtered: object = _MISSING,
    ) -> MilkyEnvelope:
        """接受好友请求；调用方负责确认高影响操作。"""

        params: dict[str, Any] = {
            "initiator_uid": _validate_text(
                initiator_uid,
                "initiator_uid",
                "accept_friend_request",
            )
        }
        if is_filtered is not _MISSING:
            if is_filtered is not None and not isinstance(is_filtered, bool):
                raise ActionError(
                    "invalid_input", "accept_friend_request", "is_filtered is invalid"
                )
            params["is_filtered"] = is_filtered
        envelope = await self.call("accept_friend_request", params)
        _validate_tool_response("accept_friend_request", envelope)
        return envelope

    async def reject_friend_request(
        self,
        initiator_uid: object,
        *,
        is_filtered: object = _MISSING,
        reason: object = _MISSING,
    ) -> MilkyEnvelope:
        """拒绝好友请求；调用方负责确认高影响操作。"""

        params: dict[str, Any] = {
            "initiator_uid": _validate_text(
                initiator_uid,
                "initiator_uid",
                "reject_friend_request",
            )
        }
        if is_filtered is not _MISSING:
            if is_filtered is not None and not isinstance(is_filtered, bool):
                raise ActionError(
                    "invalid_input", "reject_friend_request", "is_filtered is invalid"
                )
            params["is_filtered"] = is_filtered
        if reason is not _MISSING:
            if reason is not None and not isinstance(reason, str):
                raise ActionError("invalid_input", "reject_friend_request", "reason is invalid")
            params["reason"] = reason
        envelope = await self.call("reject_friend_request", params)
        _validate_tool_response("reject_friend_request", envelope)
        return envelope

    async def set_group_member_special_title(
        self,
        group_id: object,
        user_id: object,
        special_title: object,
    ) -> MilkyEnvelope:
        """设置群成员专属头衔并原样保留字符串值。"""

        if not isinstance(special_title, str):
            raise ActionError(
                "invalid_input",
                "set_group_member_special_title",
                "special_title is invalid",
            )
        params = {
            "group_id": _validate_tool_integer(
                group_id,
                "group_id",
                "set_group_member_special_title",
                minimum=_MIN_QQ_ID,
                maximum=_MAX_QQ_ID,
            ),
            "user_id": _validate_tool_integer(
                user_id,
                "user_id",
                "set_group_member_special_title",
                minimum=_MIN_QQ_ID,
                maximum=_MAX_QQ_ID,
            ),
            "special_title": special_title,
        }
        envelope = await self.call("set_group_member_special_title", params)
        _validate_tool_response("set_group_member_special_title", envelope)
        return envelope

    async def upload_group_file(
        self,
        group_id: object,
        file_uri: object,
        file_name: object,
        *,
        parent_folder_id: object = _MISSING,
    ) -> MilkyEnvelope:
        """按 Milky 文件 URI 向群上传文件。"""

        params: dict[str, Any] = {
            "group_id": _validate_id(
                group_id,
                "group_id",
                "upload_group_file",
                minimum=_MIN_QQ_ID,
                maximum=_MAX_QQ_ID,
            ),
            "file_uri": validate_media_uri(file_uri, action="upload_group_file"),
            "file_name": _validate_text(file_name, "file_name", "upload_group_file"),
        }
        if parent_folder_id is not _MISSING:
            params["parent_folder_id"] = _validate_nullable_text(
                parent_folder_id, "parent_folder_id", "upload_group_file"
            )
        envelope = await self.call("upload_group_file", params)
        return _parse_upload_result(envelope, "upload_group_file")

    async def upload_private_file(
        self, user_id: object, file_uri: object, file_name: object
    ) -> MilkyEnvelope:
        """按 Milky 文件 URI 向好友上传文件。"""

        envelope = await self.call(
            "upload_private_file",
            {
                "user_id": _validate_id(
                    user_id,
                    "user_id",
                    "upload_private_file",
                    minimum=_MIN_QQ_ID,
                    maximum=_MAX_QQ_ID,
                ),
                "file_uri": validate_media_uri(file_uri, action="upload_private_file"),
                "file_name": _validate_text(file_name, "file_name", "upload_private_file"),
            },
        )
        return _parse_upload_result(envelope, "upload_private_file")

    async def close(self) -> None:
        """释放底层 transport，重复关闭保持安全。"""

        if self._closed:
            return
        self._closed = True
        try:
            await self._transport.close()
        except (TimeoutError, OSError):
            raise ActionError("transport_unknown", "<client>", "transport close failed") from None

    async def __aenter__(self) -> Self:
        """支持用异步上下文管理器自动释放 transport。"""

        return self

    async def __aexit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        """离开异步上下文时关闭 transport。"""

        await self.close()

    @staticmethod
    def _decode_json(body: object, action: str) -> object:
        """解码 JSON 响应，不把原始内容放入异常。"""

        if not isinstance(body, (bytes, bytearray, str)):
            raise ActionError("malformed", action, "response body is not JSON text")
        try:
            if isinstance(body, (bytes, bytearray)):
                body = bytes(body).decode("utf-8")
            return json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ActionError("malformed", action, "response is not valid JSON") from None

    @staticmethod
    def _parse_typed(envelope: MilkyEnvelope, action: str) -> object:
        """使用 T04 parser 校验已成功 envelope 的 Action 专属 data。"""

        payload = {
            "status": envelope.status,
            "retcode": envelope.retcode,
            "data": envelope.data,
        }
        try:
            return parse_action_response(payload, action).value
        except ParseError:
            raise ActionError("malformed", action, "response data is malformed") from None


def _validate_id(
    value: object,
    field: str,
    action: str,
    *,
    minimum: int = 0,
    maximum: int = _MAX_SAFE_INTEGER,
) -> int:
    """校验 Milky 整数参数范围，拒绝 bool 和带额外分隔符的字符串。"""

    if isinstance(value, bool):
        raise ActionError("invalid_input", action, f"{field} is invalid")
    if isinstance(value, int) and minimum <= value <= maximum:
        return value
    if isinstance(value, str) and _NON_NEGATIVE_INTEGER_PATTERN.fullmatch(value):
        integer_value = int(value)
        if minimum <= integer_value <= maximum:
            return integer_value
    raise ActionError("invalid_input", action, f"{field} is invalid")


def _validate_message_scene(value: object, action: str) -> str:
    """校验 get_message 的 Milky 场景枚举。"""

    if not isinstance(value, str) or value not in {"friend", "group", "temp"}:
        raise ActionError("invalid_input", action, "message_scene is invalid")
    return value


def _validate_nullable_text(value: object, field: str, action: str) -> str | None:
    """校验可选且可为空的 Milky 字符串参数。"""

    if value is None:
        return None
    if not isinstance(value, str):
        raise ActionError("invalid_input", action, f"{field} is invalid")
    return value


def _safe_action_name(value: object) -> str:
    """只在诊断中保留协议允许的 Action 名称。"""

    if isinstance(value, str) and _ACTION_PATTERN.fullmatch(value):
        return value
    return "<invalid>"


def _safe_log_action(value: object) -> str:
    """将 Action 名称转换为日志允许的非空标识。"""

    return value if isinstance(value, str) and _ACTION_PATTERN.fullmatch(value) else "invalid"


def _safe_transport_phase(value: object) -> str:
    """将传输阶段收敛到固定的安全枚举。"""

    return value if isinstance(value, str) and value in _TRANSPORT_PHASES else "unknown"


def _httpx_transport_phase(httpx: Any, error: BaseException) -> str:
    """按 HTTPX 异常类型推导安全传输阶段。"""

    phase_types = (
        ("pool", ("PoolTimeout",)),
        ("connect", ("ConnectTimeout", "ConnectError", "ProxyError")),
        ("write", ("WriteTimeout", "WriteError")),
        ("read", ("ReadTimeout", "ReadError", "RemoteProtocolError")),
    )
    for phase, names in phase_types:
        error_types = tuple(
            candidate for name in names if isinstance(candidate := getattr(httpx, name, None), type)
        )
        if error_types and isinstance(error, error_types):
            return phase
    return "unknown"


def _safe_action_classification(value: object) -> str:
    """将 Action 错误分类收敛到日志允许的固定集合。"""

    allowed = {
        "rejected",
        "transport_unknown",
        "malformed",
        "unsupported",
        "invalid_input",
        "http_error",
        "stream_error",
        "protocol_error",
        "connection_error",
        "timeout",
        "unknown",
    }
    return value if isinstance(value, str) and value in allowed else "unknown"


def _safe_action_reason(value: object) -> str:
    """将 Action 错误映射为不含原始异常的固定 reason。"""

    return {
        "rejected": "action_rejected",
        "transport_unknown": "request_unknown",
        "malformed": "malformed_response",
        "unsupported": "operation_unsupported",
        "invalid_input": "invalid_input",
        "http_error": "http_error",
    }.get(value, "unknown")


def _duration_ms(started: float) -> float:
    """返回非负的单调耗时。"""

    return round(max(0.0, (time.perf_counter() - started) * 1000), 3)


def _validate_text(value: object, field: str, action: str) -> str:
    """校验非空文本参数且不在错误中回显参数值。"""

    if not isinstance(value, str) or not value.strip():
        raise ActionError("invalid_input", action, f"{field} is invalid")
    return value.strip()


def _validate_tool_params(action: str, params: Mapping[str, Any] | None) -> None:
    """在显式 Tool Action 进入 HTTP 前校验完整参数集合。"""

    if params is None:
        values: Mapping[str, Any] = {}
    elif isinstance(params, Mapping):
        values = params
    else:
        raise ActionError("invalid_input", action, "parameters must be an object")

    schemas: dict[str, tuple[set[str], set[str]]] = {
        "send_profile_like": ({"user_id", "count"}, {"user_id"}),
        "send_friend_nudge": ({"user_id", "is_self"}, {"user_id"}),
        "send_group_nudge": ({"group_id", "user_id"}, {"group_id", "user_id"}),
        "recall_group_message": ({"group_id", "message_seq"}, {"group_id", "message_seq"}),
        "get_group_info": ({"group_id", "no_cache"}, {"group_id"}),
        "get_group_member_list": ({"group_id", "no_cache"}, {"group_id"}),
        "get_group_member_info": (
            {"group_id", "user_id", "no_cache"},
            {"group_id", "user_id"},
        ),
        "set_group_member_mute": (
            {"group_id", "user_id", "duration"},
            {"group_id", "user_id"},
        ),
        "set_group_whole_mute": ({"group_id", "is_mute"}, {"group_id"}),
        "get_forwarded_messages": ({"forward_id"}, {"forward_id"}),
        "get_private_file_download_url": (
            {"user_id", "file_id", "file_hash", "is_self_send"},
            {"user_id", "file_id", "file_hash"},
        ),
        "get_group_file_download_url": (
            {"group_id", "file_id"},
            {"group_id", "file_id"},
        ),
        "accept_group_request": (
            {"notification_seq", "notification_type", "group_id", "is_filtered"},
            {"notification_seq", "notification_type", "group_id"},
        ),
        "reject_group_request": (
            {"notification_seq", "notification_type", "group_id", "is_filtered", "reason"},
            {"notification_seq", "notification_type", "group_id"},
        ),
        "accept_group_invitation": (
            {"group_id", "invitation_seq"},
            {"group_id", "invitation_seq"},
        ),
        "reject_group_invitation": (
            {"group_id", "invitation_seq"},
            {"group_id", "invitation_seq"},
        ),
        "get_group_files": (
            {"group_id", "parent_folder_id"},
            {"group_id"},
        ),
        "kick_group_member": (
            {"group_id", "user_id", "reject_add_request"},
            {"group_id", "user_id"},
        ),
        "quit_group": ({"group_id"}, {"group_id"}),
        "delete_friend": ({"user_id"}, {"user_id"}),
        "get_friend_requests": ({"limit", "is_filtered"}, set()),
        "get_friend_info": ({"user_id"}, {"user_id"}),
        "accept_friend_request": ({"initiator_uid", "is_filtered"}, {"initiator_uid"}),
        "reject_friend_request": (
            {"initiator_uid", "is_filtered", "reason"},
            {"initiator_uid"},
        ),
        "set_group_member_special_title": (
            {"group_id", "user_id", "special_title"},
            {"group_id", "user_id", "special_title"},
        ),
    }
    allowed, required = schemas[action]
    if set(values) - allowed or not required.issubset(values):
        raise ActionError("invalid_input", action, "parameters are invalid")

    id_fields = {
        "user_id",
        "group_id",
    }
    for field in id_fields & set(values):
        _validate_tool_integer(values[field], field, action, minimum=_MIN_QQ_ID, maximum=_MAX_QQ_ID)
    if "message_seq" in values:
        _validate_tool_integer(values["message_seq"], "message_seq", action)
    if "count" in values and values["count"] is not None:
        _validate_tool_integer(values["count"], "count", action)
    if "duration" in values and values["duration"] is not None:
        _validate_tool_integer(values["duration"], "duration", action)
    if "limit" in values and values["limit"] is not None:
        _validate_tool_integer(values["limit"], "limit", action)
    for field in ("notification_seq", "invitation_seq"):
        if field in values:
            _validate_tool_integer(values[field], field, action)

    for field in (
        "is_self",
        "no_cache",
        "is_mute",
        "is_self_send",
        "reject_add_request",
        "is_filtered",
    ):
        if field in values and values[field] is not None and not isinstance(values[field], bool):
            raise ActionError("invalid_input", action, f"{field} is invalid")
    for field in ("forward_id", "file_id", "file_hash", "initiator_uid"):
        if field in values:
            _validate_nonempty_tool_text(values[field], field, action)
    if "special_title" in values and not isinstance(values["special_title"], str):
        raise ActionError("invalid_input", action, "special_title is invalid")
    if "notification_type" in values and (
        not isinstance(values["notification_type"], str)
        or values["notification_type"] not in {"join_request", "invited_join_request"}
    ):
        raise ActionError("invalid_input", action, "notification_type is invalid")
    if "parent_folder_id" in values:
        _validate_optional_nonempty_tool_text(
            values["parent_folder_id"], "parent_folder_id", action
        )
    if "reason" in values and values["reason"] is not None:
        if action == "reject_group_request":
            _validate_nonempty_tool_text(values["reason"], "reason", action)
        elif not isinstance(values["reason"], str):
            raise ActionError("invalid_input", action, "reason is invalid")


def _validate_tool_response(action: str, envelope: MilkyEnvelope) -> None:
    """校验显式 Tool Action 的最小成功 data 结构。"""

    data = envelope.data
    if not isinstance(data, Mapping):
        raise ActionError("malformed", action, "response data is malformed")
    if action == "get_forwarded_messages":
        messages = data.get("messages")
        if not _is_object_array(messages):
            raise ActionError("malformed", action, "response messages are malformed")
    elif action in {"get_private_file_download_url", "get_group_file_download_url"}:
        if not isinstance(data.get("download_url"), str):
            raise ActionError("malformed", action, "response download_url is malformed")
    elif action == "get_group_files":
        if not _is_object_array(data.get("files")) or not _is_object_array(data.get("folders")):
            raise ActionError("malformed", action, "response files or folders are malformed")
    elif action == "get_friend_requests":
        if not _is_object_array(data.get("requests")):
            raise ActionError("malformed", action, "response requests are malformed")
    elif action == "get_friend_info" and not data:
        raise ActionError("malformed", action, "response data is malformed")
    elif (
        action
        in {
            "kick_group_member",
            "quit_group",
            "delete_friend",
            "accept_friend_request",
            "reject_friend_request",
            "set_group_member_special_title",
            "accept_group_request",
            "reject_group_request",
            "accept_group_invitation",
            "reject_group_invitation",
        }
        and data
    ):
        raise ActionError("malformed", action, "response data is not an empty object")
    elif action in {"get_group_info", "get_group_member_list", "get_group_member_info"}:
        try:
            parse_action_response(
                {
                    "status": envelope.status,
                    "retcode": envelope.retcode,
                    "data": envelope.data,
                },
                action,
            )
        except ParseError:
            raise ActionError("malformed", action, "response data is malformed") from None


def _validate_tool_integer(
    value: object,
    field: str,
    action: str,
    *,
    minimum: int = 0,
    maximum: int = _MAX_SAFE_INTEGER,
) -> int:
    """校验 Tool schema 使用的严格整数范围。"""

    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ActionError("invalid_input", action, f"{field} is invalid")
    return value


def _validate_nonempty_tool_text(value: object, field: str, action: str) -> str:
    """校验 Tool schema 使用的非空字符串。"""

    if not isinstance(value, str) or not value.strip():
        raise ActionError("invalid_input", action, f"{field} is invalid")
    return value


def _validate_optional_nonempty_tool_text(value: object, field: str, action: str) -> str | None:
    """校验允许显式 null 的非空字符串参数。"""

    if value is None:
        return None
    return _validate_nonempty_tool_text(value, field, action)


def _group_request_params(
    action: str,
    notification_seq: object,
    notification_type: object,
    group_id: object,
    *,
    is_filtered: object,
) -> dict[str, Any]:
    """校验群请求参数并保留可选字段的省略/null 区别。"""

    if not isinstance(notification_type, str) or notification_type not in {
        "join_request",
        "invited_join_request",
    }:
        raise ActionError("invalid_input", action, "notification_type is invalid")
    params: dict[str, Any] = {
        "notification_seq": _validate_tool_integer(notification_seq, "notification_seq", action),
        "notification_type": notification_type,
        "group_id": _validate_tool_integer(
            group_id,
            "group_id",
            action,
            minimum=_MIN_QQ_ID,
            maximum=_MAX_QQ_ID,
        ),
    }
    if is_filtered is not _MISSING:
        if is_filtered is not None and not isinstance(is_filtered, bool):
            raise ActionError("invalid_input", action, "is_filtered is invalid")
        params["is_filtered"] = is_filtered
    return params


def _is_object_array(value: object) -> bool:
    """确认协议数组由对象元素组成，同时不改变其 raw 内容。"""

    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
        and all(isinstance(item, Mapping) for item in value)
    )


def _validate_segments(value: object, action: str) -> list[Mapping[str, Any]]:
    """校验 message 为有序 segment 对象列表。"""

    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ActionError("invalid_input", action, "message must be an array")
    if any(not isinstance(segment, Mapping) for segment in value):
        raise ActionError("invalid_input", action, "message segments must be objects")
    return [dict(segment) for segment in value]


def _parse_send_result(envelope: MilkyEnvelope, action: str) -> SendResult:
    """校验发送成功的最小 data.message_seq 结构。"""

    if not isinstance(envelope.data, Mapping):
        raise ActionError("malformed", action, "response data is malformed")
    sequence = envelope.data.get("message_seq")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ActionError("malformed", action, "response is missing message_seq")
    return SendResult(str(sequence))


def _parse_upload_result(envelope: MilkyEnvelope, action: str) -> MilkyEnvelope:
    """校验上传成功的最小 data.file_id 结构。"""

    if not isinstance(envelope.data, Mapping) or not isinstance(envelope.data.get("file_id"), str):
        raise ActionError("malformed", action, "response is missing file_id")
    return envelope


def _validate_impl_info_data(data: Mapping[str, Any], action: str) -> None:
    """校验 ``get_impl_info`` 成功响应的五个稳定字符串字段。"""

    required_fields = (
        "impl_name",
        "impl_version",
        "milky_version",
        "qq_protocol_type",
        "qq_protocol_version",
    )
    if any(not isinstance(data.get(field), str) for field in required_fields):
        raise ActionError("malformed", action, "response data is missing implementation info")


def _response_body_bytes(body: object, action: str) -> bytes:
    """将已验证的响应正文转换为可原样交付的 UTF-8 字节。"""

    if isinstance(body, bytes):
        return body
    if isinstance(body, bytearray):
        return bytes(body)
    if isinstance(body, str):
        return body.encode("utf-8")
    raise ActionError("malformed", action, "response body is not JSON text")


__all__ = [
    "MAX_LOCAL_MEDIA_BYTES",
    "ActionError",
    "HttpTransport",
    "HttpxTransport",
    "HttpxTransportError",
    "MilkyActionError",
    "MilkyClient",
    "SendResult",
    "TransportResponse",
    "materialize_media_uri",
    "validate_media_uri",
]
