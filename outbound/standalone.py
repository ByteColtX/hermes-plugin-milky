"""提供 Hermes cron 独立进程使用的一次性 Milky 出站 sender。"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Sequence

from config import ConfigError, MilkyConfig, load_config
from milky.client import ActionError, MilkyClient

from .chunking import chunk_text
from .formatter import OutboundFormatError, format_message
from .sender import (
    MilkyOutboundSender,
    OutboundSendResult,
    parse_outbound_target,
)

ClientFactory = Callable[[MilkyConfig], object]

_SAFE_CLASSIFICATIONS = frozenset(
    {
        "invalid_input",
        "unsupported",
        "rejected",
        "transport_unknown",
        "malformed",
        "http_error",
    }
)


def make_standalone_sender(
    config: MilkyConfig,
    *,
    client_factory: ClientFactory = MilkyClient,
) -> Callable[..., Awaitable[dict[str, object]]]:
    """创建绑定启动配置的独立 cron sender。"""

    if not callable(getattr(config, "action_url", None)) or not isinstance(
        getattr(config, "auth_headers", None), dict
    ):
        raise TypeError("config must provide Milky HTTP configuration")

    async def send(
        pconfig: object,
        chat_id: object,
        message: object,
        *,
        thread_id: object = None,
        media_files: Sequence[object] | None = None,
        force_document: object = False,
    ) -> dict[str, object]:
        """执行一次受控的 standalone 文本投递。"""

        return await standalone_send(
            pconfig,
            chat_id,
            message,
            thread_id=thread_id,
            media_files=media_files,
            force_document=force_document,
            config=config,
            client_factory=client_factory,
        )

    return send


async def standalone_send(
    pconfig: object,
    chat_id: object,
    message: object,
    *,
    thread_id: object = None,
    media_files: Sequence[object] | None = None,
    force_document: object = False,
    config: MilkyConfig | None = None,
    client_factory: ClientFactory = MilkyClient,
) -> dict[str, object]:
    """在无 live adapter 时发送一条文本并释放所有临时资源。"""

    del pconfig
    local_error = _validate_standalone_inputs(
        chat_id,
        message,
        thread_id=thread_id,
        media_files=media_files,
        force_document=force_document,
    )
    if local_error is not None:
        return local_error

    try:
        resolved_config = config or load_config()
        client = client_factory(resolved_config)
    except (ConfigError, TypeError, ValueError):
        return _failure("invalid_input")
    except Exception:  # noqa: BLE001 - 创建连接失败不得暴露底层文本
        return _failure("transport_unknown")

    sender = MilkyOutboundSender(
        client,
        max_local_media_bytes=resolved_config.max_local_media_bytes,
    )
    try:
        result = await sender.send(chat_id, message)  # type: ignore[arg-type]
        return _result_dict(result)
    except asyncio.CancelledError:
        raise
    except (ActionError, OSError, TimeoutError, TypeError, ValueError):
        return _failure(_exception_classification())
    except Exception:  # noqa: BLE001 - standalone 边界不得泄露异常正文
        return _failure("malformed")
    finally:
        await _close_quietly(sender)
        await _close_quietly(client)


def _validate_standalone_inputs(
    chat_id: object,
    message: object,
    *,
    thread_id: object,
    media_files: Sequence[object] | None,
    force_document: object,
) -> dict[str, object] | None:
    """在创建 HTTP client 前拒绝 standalone 不支持的输入。"""

    if not isinstance(force_document, bool):
        return _failure("invalid_input")
    if thread_id is not None:
        return _failure("unsupported")
    if media_files:
        return _failure("unsupported")
    if force_document:
        return _failure("unsupported")
    if not isinstance(chat_id, str) or not chat_id.strip():
        return _failure("invalid_input")
    try:
        parse_outbound_target(chat_id)
        if isinstance(message, str):
            chunks = chunk_text(message)
            if not chunks:
                format_message(message)
            else:
                for chunk in chunks:
                    format_message(chunk)
        else:
            format_message(message)
    except OutboundFormatError as error:
        return _failure(error.classification)
    return None


def _result_dict(result: OutboundSendResult) -> dict[str, object]:
    """把统一 sender 结果转换成宿主 standalone hook 的安全字典。"""

    if bool(getattr(result, "success", False)):
        message_id = getattr(result, "message_id", None)
        if isinstance(message_id, str) and message_id:
            return {"success": True, "message_id": message_id}
        return _failure("malformed")
    classification = getattr(result, "error_kind", None)
    if classification not in _SAFE_CLASSIFICATIONS:
        classification = getattr(result, "classification", None)
    if classification not in _SAFE_CLASSIFICATIONS:
        classification = "malformed"
    return _failure(classification)


def _failure(classification: str) -> dict[str, object]:
    """生成不带异常正文、目标、凭证或媒体路径的错误结果。"""

    safe_classification = classification if classification in _SAFE_CLASSIFICATIONS else "malformed"
    return {
        "success": False,
        "classification": safe_classification,
        "error": f"{safe_classification}: standalone send failed",
    }


def _exception_classification() -> str:
    """为未携带安全分类的 standalone 异常选择固定错误类别。"""

    return "malformed"


async def _close_quietly(resource: object) -> None:
    """尽力关闭资源且不让清理异常覆盖原始投递结果。"""

    close = getattr(resource, "close", None)
    if not callable(close):
        return
    try:
        result = close()
        if inspect.isawaitable(result):
            await result
    except Exception:  # noqa: BLE001 - 清理错误只能留在本地生命周期边界
        return


__all__ = ["make_standalone_sender", "standalone_send"]
