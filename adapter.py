"""Milky platform adapter 的生命周期薄层。"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import deque

from config import MilkyConfig, load_config
from gates import GateRegistry
from inbound.pipeline import InboundPipeline
from milky.client import MilkyClient
from milky.event_stream import SseEventStream
from milky.observability import log_event
from milky.resources import HermesMediaHelpers, ResourceResolver
from outbound.formatter import OutboundFormatError
from outbound.materialization import (
    MaterializationKind,
    OutboundMaterialization,
    prepare_materialization,
)
from outbound.sender import MilkyOutboundSender, OutboundSendResult, parse_outbound_target
from session import BotIdentitySnapshot, ChatAdmissionCoordinator, TtlDeduplicator, WaitBuffer
from state import MuteTracker
from will import build_engine

try:
    from gateway.config import Platform
    from gateway.platforms.base import BasePlatformAdapter
except ImportError:  # pragma: no cover - Hermes 未安装时的测试兼容分支

    class _FallbackPlatform:
        """提供脱离 Hermes 宿主时的最小 platform 值。"""

        def __init__(self, value: str) -> None:
            self.value = value

    class BasePlatformAdapter:
        """提供本地单元测试所需的最小宿主 adapter 边界。"""

        def __init__(self, config: object, platform: object) -> None:
            self.config = config
            self.platform = platform
            self._running = False

        def _mark_connected(self) -> None:
            self._running = True

        def _mark_disconnected(self) -> None:
            self._running = False

        def _set_fatal_error(self, code: str, message: str, *, retryable: bool) -> None:
            del code, message, retryable
            self._running = False

    Platform = _FallbackPlatform


logger = logging.getLogger(__name__)

_MAX_DIAGNOSTICS = 128


class _HermesMediaHelperBridge:
    """延迟调用 Hermes 公共媒体 helper，不在插件内实现下载或缓存。"""

    async def cache_image_from_url(self, url: str, ext: str = ".jpg", retries: int = 2) -> str:
        """把图片 URL 交给 Hermes 的异步 helper。"""

        from gateway.platforms.base import cache_image_from_url

        return await cache_image_from_url(url, ext=ext, retries=retries)

    async def cache_audio_from_url(self, url: str, ext: str = ".ogg", retries: int = 2) -> str:
        """把音频 URL 交给 Hermes 的异步 helper。"""

        from gateway.platforms.base import cache_audio_from_url

        return await cache_audio_from_url(url, ext=ext, retries=retries)


class MilkyAdapter(BasePlatformAdapter):
    """连接 Milky client、事件流、状态和 Hermes 入站/出站边界。"""

    splits_long_messages = True
    PLATFORM_NAME = "milky"

    def __init__(
        self,
        platform_config: object,
        *,
        milky_config: MilkyConfig | None = None,
        client: object | None = None,
        event_stream: object | None = None,
        mute_tracker: object | None = None,
        resource_resolver: object | None = None,
        will_engine: object | None = None,
        pipeline: object | None = None,
        outbound_sender: object | None = None,
        hermes_media_helpers: HermesMediaHelpers | None = None,
        slash_command_service: object | None = None,
        identity_snapshot: BotIdentitySnapshot | None = None,
    ) -> None:
        """组装进程内依赖；构造阶段不建立网络连接或后台任务。"""

        super().__init__(platform_config, Platform(self.PLATFORM_NAME))
        self._config = milky_config or load_config()
        self._client = client if client is not None else MilkyClient(self._config)
        self._event_stream = (
            event_stream if event_stream is not None else SseEventStream(self._config)
        )
        self._mute_tracker = (
            mute_tracker
            if mute_tracker is not None
            else MuteTracker(self._client, allowed_chats=self._config.allowed_chats)
        )
        self._resource_resolver = (
            resource_resolver
            if resource_resolver is not None
            else ResourceResolver(
                self._client,
                hermes_media_helpers or _HermesMediaHelperBridge(),
            )
        )
        self._will_engine = (
            will_engine if will_engine is not None else build_engine(self._config.will_policy)
        )
        self._gate_registry = GateRegistry(self._config.allowed_chats)
        self._wait_buffer = WaitBuffer(self._config.session_buffer_size)
        self._admission = ChatAdmissionCoordinator()
        self._deduplicator = TtlDeduplicator()
        self._outbound = (
            outbound_sender
            if outbound_sender is not None
            else MilkyOutboundSender(self._client, mute_tracker=self._mute_tracker)
        )
        if slash_command_service is None:
            from slash_commands import SlashCommandService

            slash_command_service = SlashCommandService()
        self._slash_command_service = slash_command_service
        self._identity_snapshot = (
            identity_snapshot if identity_snapshot is not None else BotIdentitySnapshot()
        )
        self._pipeline = pipeline
        self._self_id: int | None = None
        self._event_task: asyncio.Task[None] | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._initial_sync_complete = False
        self._pipeline_started = False
        self._connected = False
        self._closed = False
        self._sender_bound = False
        self._nickname: str | None = None
        self._identity_published = False
        self._diagnostics: deque[str] = deque(maxlen=_MAX_DIAGNOSTICS)

    @property
    def name(self) -> str:
        """返回稳定的 adapter 名称。"""

        return "Milky"

    @property
    def is_connected(self) -> bool:
        """返回当前是否已完成初始化并运行事件流。"""

        return self._connected

    @property
    def ready(self) -> bool:
        """返回普通消息入口是否已经开放。"""

        return self._connected and self._initial_sync_complete and self._pipeline is not None

    @property
    def self_id(self) -> int | None:
        """返回初始同步确认的 Bot 身份。"""

        return self._self_id

    @property
    def nickname(self) -> str | None:
        """返回初始同步确认的 Bot 昵称。"""

        return self._nickname

    @property
    def identity_snapshot(self) -> BotIdentitySnapshot:
        """返回与根入口 system prompt section 共享的身份快照。"""

        return self._identity_snapshot

    @property
    def diagnostics(self) -> tuple[str, ...]:
        """返回不包含凭证、正文、URL 或本地路径的生命周期诊断。"""

        return tuple(self._diagnostics)

    @property
    def client(self) -> object:
        """返回注入的 Milky client。"""

        return self._client

    @property
    def event_stream(self) -> object:
        """返回注入的 SSE 事件流。"""

        return self._event_stream

    @property
    def mute_tracker(self) -> object:
        """返回群禁言状态拥有者。"""

        return self._mute_tracker

    @property
    def pipeline(self) -> object | None:
        """返回当前入站 pipeline。"""

        return self._pipeline

    @property
    def outbound_sender(self) -> object:
        """返回出站 sender。"""

        return self._outbound

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        """先完成初始状态同步，再启动 SSE 事件消费。"""

        del is_reconnect
        async with self._lifecycle_lock:
            if self._closed:
                self._record("connect_after_stop")
                log_event(
                    logger,
                    "milky_adapter_connect_failed",
                    logging.WARNING,
                    stage="lifecycle",
                    classification="unsupported",
                    reason="stopped",
                )
                return False
            if self._connected and self._event_task is not None and not self._event_task.done():
                return True
            log_event(logger, "milky_adapter_connecting", logging.INFO, stage="lifecycle")
            try:
                if not self._initial_sync_complete:
                    await self._initialize_state()
                if self._pipeline is None:
                    self._pipeline = self._build_pipeline()
                if not self._pipeline_started:
                    start = getattr(self._pipeline, "start", None)
                    if callable(start):
                        start()
                    self._pipeline_started = True
                self._mark_connected()
                self._connected = True
                self._bind_command_service()
                self._bind_sender()
                self._event_task = asyncio.create_task(
                    self._run_event_stream(),
                    name="milky-event-stream",
                )
                if not self._identity_published:
                    self._identity_published = self._identity_snapshot.publish(
                        self._self_id, self._nickname
                    )
                log_event(
                    logger,
                    "milky_adapter_ready",
                    logging.INFO,
                    stage="lifecycle",
                    self_id=self._self_id,
                )
                return True
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - 连接边界必须 fail-closed
                self._connected = False
                self._mark_disconnected()
                self._unbind_command_service()
                self._unbind_sender()
                self._record(f"connect_failed:{_safe_error_category(error)}")
                log_event(
                    logger,
                    "milky_adapter_connect_failed",
                    logging.WARNING,
                    stage="lifecycle",
                    classification=_error_classification(error),
                    reason="initial_sync_failed",
                )
                self._set_fatal_error_safely()
                return False

    async def disconnect(self) -> None:
        """幂等停止事件流、pipeline detached 任务和 HTTP client。"""

        async with self._lifecycle_lock:
            if self._closed:
                return
            self._closed = True
            self._connected = False
            log_event(logger, "milky_adapter_stopping", logging.INFO, stage="lifecycle")
            event_task = self._event_task
            self._event_task = None

            await self._close_component(self._event_stream, "event_stream_close_failed")
            if event_task is not None and event_task is not asyncio.current_task():
                if not event_task.done():
                    event_task.cancel()
                await asyncio.gather(event_task, return_exceptions=True)

            await self._close_component(self._pipeline, "pipeline_close_failed")
            await self._close_component(self._outbound, "outbound_close_failed")
            await self._close_component(self._mute_tracker, "mute_tracker_close_failed")
            self._unbind_command_service()
            await self._close_component(self._client, "client_close_failed")
            self._unbind_sender()
            self._mark_disconnected()
            log_event(logger, "milky_adapter_stopped", logging.INFO, stage="lifecycle")

    async def send(
        self,
        chat_id: str,
        content: object,
        reply_to: object = None,
        metadata: object = None,
    ) -> object:
        """把已连接 adapter 的出站调用委托给统一 sender。"""

        del reply_to
        if not self._connected or self._closed:
            return OutboundSendResult(
                success=False,
                error="unsupported: adapter is disconnected",
                error_kind="unsupported",
            )
        return await self._outbound.send(chat_id, content, None, metadata)

    async def send_image(
        self,
        chat_id: str,
        image_url: object,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: object = None,
    ) -> object:
        """将图片交给统一 Milky segment sender。"""

        attachment, failure = await self._prepare_outbound_attachment(
            chat_id,
            image_url,
            expected_kind="image",
            action="send_image",
        )
        if failure is not None:
            return failure
        return await self._delegate_outbound(
            "send_image",
            chat_id,
            attachment.uri,
            caption=caption,
            reply_to=reply_to,
            metadata=metadata,
        )

    async def send_image_file(
        self,
        chat_id: str,
        image_path: object,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: object = None,
        **kwargs: object,
    ) -> object:
        """将 Hermes 提供的图片路径交给统一 sender。"""

        del kwargs
        return await self.send_image(
            chat_id,
            image_path,
            caption=caption,
            reply_to=reply_to,
            metadata=metadata,
        )

    async def send_voice(
        self,
        chat_id: str,
        audio_path: object,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: object = None,
        **kwargs: object,
    ) -> object:
        """将语音交给统一 Milky segment sender。"""

        attachment, failure = await self._prepare_outbound_attachment(
            chat_id,
            audio_path,
            expected_kind="audio",
            action="send_voice",
        )
        if failure is not None:
            return failure
        return await self._delegate_outbound(
            "send_voice",
            chat_id,
            attachment.uri,
            caption=caption,
            reply_to=reply_to,
            metadata=metadata,
            **kwargs,
        )

    async def send_video(
        self,
        chat_id: str,
        video_path: object,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: object = None,
        **kwargs: object,
    ) -> object:
        """将视频交给统一 Milky segment sender。"""

        attachment, failure = await self._prepare_outbound_attachment(
            chat_id,
            video_path,
            expected_kind="video",
            action="send_video",
        )
        if failure is not None:
            return failure
        return await self._delegate_outbound(
            "send_video",
            chat_id,
            attachment.uri,
            caption=caption,
            reply_to=reply_to,
            metadata=metadata,
            **kwargs,
        )

    async def send_document(
        self,
        chat_id: str,
        file_path: object,
        caption: str | None = None,
        file_name: str | None = None,
        reply_to: str | None = None,
        metadata: object = None,
        **kwargs: object,
    ) -> object:
        """将文件交给独立 Milky upload Action。"""

        attachment, failure = await self._prepare_outbound_attachment(
            chat_id,
            file_path,
            expected_kind="document",
            action="send_document",
            file_name=file_name,
        )
        if failure is not None:
            return failure
        effective_file_name = file_name if file_name is not None else attachment.file_name
        return await self._delegate_outbound(
            "send_document",
            chat_id,
            attachment.uri,
            caption=caption,
            file_name=effective_file_name,
            reply_to=reply_to,
            metadata=metadata,
            **kwargs,
        )

    async def _send_with_retry(
        self,
        chat_id: str,
        content: object,
        reply_to: object = None,
        metadata: object = None,
        max_retries: int = 2,
        base_delay: float = 2.0,
    ) -> object:
        """一次性发送 Milky 消息，不委托宿主的通用 fallback。"""

        del max_retries, base_delay, reply_to
        return await self.send(chat_id, content, None, metadata)

    async def _delegate_outbound(self, method_name: str, *args: object, **kwargs: object) -> object:
        """在不触发宿主 fallback 的前提下调用 sender 方法。"""

        if not self._connected or self._closed:
            return OutboundSendResult(
                success=False,
                error="unsupported: adapter is disconnected",
                error_kind="unsupported",
            )
        method = getattr(self._outbound, method_name, None)
        if not callable(method):
            return OutboundSendResult(
                success=False,
                error="unsupported: outbound capability is unavailable",
                error_kind="unsupported",
            )
        result = method(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _prepare_outbound_attachment(
        self,
        chat_id: str,
        value: object,
        *,
        expected_kind: MaterializationKind,
        action: str,
        file_name: object = None,
    ) -> tuple[OutboundMaterialization | None, OutboundSendResult | None]:
        """在 adapter 边界 materialize 本地资源，并隐藏所有错误正文。"""

        if not self._connected or self._closed:
            return None, _materialization_failure("unsupported", action=action)
        if file_name is not None and not isinstance(file_name, str):
            return None, _materialization_failure("invalid_input", action=action)
        try:
            parse_outbound_target(chat_id)
        except OutboundFormatError as error:
            return None, _materialization_failure(error.classification, action=action)
        try:
            attachment = await prepare_materialization(
                value,
                expected_kind=expected_kind,
                action=action,
                file_name=file_name if isinstance(file_name, str) else None,
            )
        except Exception as error:  # noqa: BLE001 - adapter 边界不得泄漏错误正文
            classification = getattr(error, "classification", None)
            if classification not in {
                "invalid_input",
                "unsupported",
                "rejected",
                "transport_unknown",
                "malformed",
                "http_error",
            }:
                classification = (
                    "transport_unknown"
                    if isinstance(error, (OSError, TimeoutError))
                    else "unsupported"
                )
            return None, _materialization_failure(classification, action=action)
        return attachment, None

    async def get_chat_info(self, chat_id: str) -> dict[str, str]:
        """只根据 namespaced chat key 返回本地可确认的最小信息。"""

        target = parse_outbound_target(chat_id)
        return {"name": chat_id, "type": target.scene}

    async def _initialize_state(self) -> None:
        """完成一次登录身份和群禁言初始同步。"""

        initialize = getattr(self._mute_tracker, "initialize", None)
        if not callable(initialize):
            raise TypeError("mute tracker initial sync is unavailable")
        result = initialize()
        if inspect.isawaitable(result):
            await result
        if result is False:
            raise RuntimeError("mute tracker initial sync was not completed")
        self_id = getattr(self._mute_tracker, "self_id", None)
        if isinstance(self_id, bool) or not isinstance(self_id, int) or self_id < 0:
            raise ValueError("initial state sync did not confirm self identity")
        self._self_id = self_id
        nickname = getattr(self._mute_tracker, "nickname", None)
        self._nickname = nickname if isinstance(nickname, str) else None
        self._initial_sync_complete = True
        start = getattr(self._mute_tracker, "start", None)
        if callable(start):
            result = start()
            if inspect.isawaitable(result):
                await result

    def _build_pipeline(self) -> InboundPipeline:
        """使用初始同步确认的 Bot 身份组装入站 pipeline。"""

        if self._self_id is None:
            raise RuntimeError("pipeline requires a confirmed self identity")
        return InboundPipeline(
            self_id=self._self_id,
            hermes=self,
            resource_resolver=self._resource_resolver,
            gate_registry=self._gate_registry,
            will_engine=self._will_engine,
            wait_buffer=self._wait_buffer,
            admission=self._admission,
            deduplicator=self._deduplicator,
            mute_tracker=self._mute_tracker,
        )

    async def _run_event_stream(self) -> None:
        """将 SSE 事件交给 pipeline，并隔离流任务异常。"""

        try:
            handler = getattr(self._pipeline, "handle_event", None)
            if not callable(handler):
                raise TypeError("inbound pipeline event handler is unavailable")
            result = self._event_stream.run(handler)
            if inspect.isawaitable(result):
                await result
            if not self._closed:
                self._connected = False
                self._record("event_stream_stopped")
                self._unbind_command_service()
                self._mark_disconnected()
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - 事件流任务不得泄漏异常
            self._record(f"event_stream_failed:{_safe_error_category(error)}")
            if not self._closed:
                self._connected = False
                self._unbind_command_service()
                self._mark_disconnected()

    def _bind_sender(self) -> None:
        """在生命周期连接后启用显式 Hermes 工具的出站 sender。"""

        if self._sender_bound or not isinstance(self._outbound, MilkyOutboundSender):
            return
        from outbound.tools import bind_sender

        bind_sender(self._outbound)
        self._sender_bound = True

    def _bind_command_service(self) -> None:
        """将已连接的同一 Milky client 交给命令 service。"""

        bind = getattr(self._slash_command_service, "bind_client", None)
        if callable(bind):
            bind(self._client)

    def _unbind_command_service(self) -> None:
        """在连接失败或停止后解除命令 service 的 client 绑定。"""

        unbind = getattr(self._slash_command_service, "unbind_client", None)
        if callable(unbind):
            unbind(self._client)

    def _unbind_sender(self) -> None:
        """在生命周期停止后撤销显式工具的 sender。"""

        if not self._sender_bound:
            return
        from outbound.tools import unbind_sender

        unbind_sender()
        self._sender_bound = False

    async def _close_component(self, component: object | None, reason: str) -> None:
        """安全关闭一个可选异步资源并记录固定诊断。"""

        close = getattr(component, "close", None)
        if not callable(close):
            return
        try:
            result = close()
            if inspect.isawaitable(result):
                await result
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - 关闭流程必须继续释放其余资源
            self._record(reason)
            log_event(
                logger,
                "milky_adapter_component_close_failed",
                logging.WARNING,
                stage="lifecycle",
                classification="malformed",
                reason="component_close_failed",
                component=reason.removesuffix("_close_failed"),
            )

    def _set_fatal_error_safely(self) -> None:
        """将启动失败报告给 Hermes，同时不暴露异常正文。"""

        setter = getattr(self, "_set_fatal_error", None)
        if not callable(setter):
            return
        try:
            setter(
                "milky_initial_sync_failed",
                "Milky initial state synchronization failed",
                retryable=True,
            )
        except Exception:  # noqa: BLE001 - 诊断失败不得覆盖原始失败结果
            self._record("fatal_error_report_failed")
            log_event(
                logger,
                "milky_adapter_fatal_error_report_failed",
                logging.WARNING,
                stage="lifecycle",
                classification="internal_error",
                reason="fatal_error_report_failed",
            )

    def _record(self, reason: str) -> None:
        """记录有界且不包含敏感内容的诊断。"""

        self._diagnostics.append(reason[:96])


def _safe_error_category(error: BaseException) -> str:
    """把异常类型转换为固定安全类别。"""

    return type(error).__name__.lower().replace("error", "")[:48] or "failure"


def _error_classification(error: BaseException) -> str:
    """将生命周期异常转换为日志允许的固定分类。"""

    classification = getattr(error, "classification", None)
    if classification in {
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
        "state_sync_failed",
    }:
        return classification
    return "state_sync_failed"


def _materialization_failure(
    classification: str, *, action: str | None = None
) -> OutboundSendResult:
    """创建不包含附件引用或底层异常正文的安全失败结果。"""

    safe_classification = (
        classification
        if classification
        in {
            "invalid_input",
            "unsupported",
            "rejected",
            "transport_unknown",
            "malformed",
            "http_error",
        }
        else "unsupported"
    )
    reason = {
        "invalid_input": "input is invalid",
        "unsupported": "operation is unsupported",
        "rejected": "operation was rejected",
        "transport_unknown": "request outcome is unknown",
        "malformed": "response or result is malformed",
        "http_error": "HTTP request failed",
    }[safe_classification]
    result = OutboundSendResult(
        success=False,
        error=f"{safe_classification}: {reason}",
        error_kind=safe_classification,
    )
    if action is not None:
        log_event(
            logger,
            "milky_outbound_materialization_failed",
            logging.WARNING,
            stage="outbound",
            action=action,
            classification=safe_classification,
            reason=(
                "invalid_input"
                if safe_classification == "invalid_input"
                else "operation_unsupported"
                if safe_classification == "unsupported"
                else "send_failed"
            ),
        )
    return result


__all__ = ["MilkyAdapter"]
