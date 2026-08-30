"""执行脱敏的 Milky 本地 smoke。

默认只执行登录、群列表、Bot 成员禁言同步和有界 SSE 连接。出站消息及文件上传
必须显式传入 ``--allow-write``，并且目标还必须出现在 ``MILKY_ALLOWED_CHATS`` 中。
脚本只输出 Action 分类、数量和状态，不输出 token、chat ID、响应正文、URL 或路径。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import ConfigError, MilkyConfig, load_config
from milky.client import ActionError, MilkyClient
from milky.event_stream import SseEventStream, UrllibSseTransport
from outbound.sender import (
    MilkyOutboundSender,
    OutboundSendResult,
    parse_outbound_target,
)
from state import MuteSyncError, MuteTracker

_SAFE_CLASSIFICATIONS = frozenset(
    {
        "accepted",
        "invalid_input",
        "malformed",
        "rejected",
        "transport_unknown",
        "http_error",
        "unsupported",
        "state_sync_failed",
        "timeout",
        "stopped",
    }
)


def _classification(error: BaseException, fallback: str = "malformed") -> str:
    """提取固定错误分类，不把异常正文带入 smoke 输出。"""

    value = getattr(error, "classification", None)
    if isinstance(value, str) and value in _SAFE_CLASSIFICATIONS:
        return value
    return fallback


def _send_summary(result: OutboundSendResult) -> dict[str, object]:
    """把出站结果压缩为不含消息 ID 和错误正文的摘要。"""

    if result.success:
        return {"status": "accepted"}
    return {"status": _classification(result, "malformed")}


async def _probe_event_stream(config: MilkyConfig, timeout: float) -> dict[str, object]:
    """在时间上有界地连接 SSE，只统计收到的事件数量。"""

    transport = _CountingSseTransport()
    stream = SseEventStream(
        config,
        transport=transport,
        initial_backoff=1.0,
        max_backoff=4.0,
    )
    received = 0
    received_event = asyncio.Event()

    async def handler(_event: object) -> None:
        nonlocal received
        received += 1
        received_event.set()

    stream_task = asyncio.create_task(stream.run(handler), name="milky-smoke-sse")
    wait_task = asyncio.create_task(received_event.wait(), name="milky-smoke-sse-wait")
    outcome = "timeout"
    try:
        done, _ = await asyncio.wait(
            {stream_task, wait_task}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        if wait_task in done:
            outcome = "accepted"
        elif stream_task in done:
            outcome = "stopped"
            if stream_task.cancelled() or stream_task.exception() is not None:
                outcome = "transport_unknown"
    finally:
        wait_task.cancel()
        await asyncio.gather(wait_task, return_exceptions=True)
        await stream.close()
        await asyncio.gather(stream_task, return_exceptions=True)

    categories = sorted(
        {
            item.classification
            for item in stream.diagnostics
            if item.classification in _SAFE_CLASSIFICATIONS
        }
    )
    return {
        "status": outcome,
        "connection_attempt_count": transport.attempts,
        "received_event_count": received,
        "diagnostic_categories": categories,
    }


class _CountingSseTransport:
    """包裹标准 SSE transport，只统计连接次数，不保存 URL 或响应。"""

    def __init__(self) -> None:
        self._transport = UrllibSseTransport()
        self.attempts = 0

    async def connect(self, url: str, headers: dict[str, str], timeout: float) -> object:
        """统计并转发一次 SSE 连接。"""

        self.attempts += 1
        return await self._transport.connect(url, headers, timeout)

    async def close(self) -> None:
        """释放标准 SSE transport。"""

        await self._transport.close()


def _target_allowed(config: MilkyConfig, value: str) -> bool:
    """要求出站目标经过严格解析且显式出现在 allowlist。"""

    try:
        target = parse_outbound_target(value)
    except (TypeError, ValueError):
        return False
    normalized = f"{target.scene}:{target.peer_id}"
    return normalized in config.allowed_chats


async def _run_writes(
    config: MilkyConfig,
    client: MilkyClient,
    tracker: MuteTracker,
    arguments: argparse.Namespace,
) -> dict[str, object]:
    """执行用户明确开启且经过 allowlist 校验的受控出站 smoke。"""

    requested = any(
        value is not None
        for value in (
            arguments.group_chat,
            arguments.dm_chat,
            arguments.upload_group_chat,
            arguments.upload_dm_chat,
        )
    )
    if not requested:
        return {"status": "skipped_no_target"}
    if not arguments.allow_write:
        return {"status": "blocked_write_flag"}

    sender = MilkyOutboundSender(client, mute_tracker=tracker)
    results: dict[str, object] = {}
    for label, target in (
        ("group_message", arguments.group_chat),
        ("dm_message", arguments.dm_chat),
    ):
        if target is None:
            continue
        if not _target_allowed(config, target):
            results[label] = {"status": "blocked_target"}
            continue
        result = await sender.send(target, arguments.message)
        results[label] = _send_summary(result)

    if arguments.file is not None:
        for label, target in (
            ("group_file_upload", arguments.upload_group_chat),
            ("dm_file_upload", arguments.upload_dm_chat),
        ):
            if target is None:
                continue
            if not _target_allowed(config, target):
                results[label] = {"status": "blocked_target"}
                continue
            result = await sender.send_document(target, arguments.file)
            results[label] = _send_summary(result)
    return results


async def run_smoke(arguments: argparse.Namespace) -> dict[str, object]:
    """执行只读同步、SSE 探测和可选受控出站 smoke。"""

    config = load_config()
    client = MilkyClient(config, timeout=arguments.request_timeout)
    result: dict[str, object] = {
        "security": "sanitized_summary_only",
        "read_only": not arguments.allow_write,
    }
    tracker = MuteTracker(client, allowed_chats=config.allowed_chats)
    try:
        try:
            login = await client.get_login_info()
            result["get_login_info"] = "accepted"
            result["self_identity_confirmed"] = isinstance(login.uin, int)
        except (ActionError, TypeError, ValueError) as error:
            result["get_login_info"] = _classification(error, "transport_unknown")
            return result

        try:
            groups = await client.get_group_list()
            result["get_group_list"] = "accepted"
            result["group_count"] = len(groups.groups)
        except (ActionError, TypeError, ValueError) as error:
            result["get_group_list"] = _classification(error, "transport_unknown")
            return result

        try:
            await tracker.initialize()
            result["mute_sync"] = "accepted"
            result["mute_group_count"] = len(tracker.group_ids)
        except MuteSyncError:
            result["mute_sync"] = "state_sync_failed"
        except (ActionError, TypeError, ValueError) as error:
            result["mute_sync"] = _classification(error, "state_sync_failed")

        result["sse"] = await _probe_event_stream(config, arguments.event_timeout)
        if arguments.allow_write or any(
            value is not None
            for value in (
                arguments.group_chat,
                arguments.dm_chat,
                arguments.upload_group_chat,
                arguments.upload_dm_chat,
                arguments.file,
            )
        ):
            result["writes"] = await _run_writes(config, client, tracker, arguments)
        return result
    finally:
        await client.close()


def _parser() -> argparse.ArgumentParser:
    """创建 smoke 参数解析器。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-timeout", type=float, default=5.0)
    parser.add_argument("--request-timeout", type=float, default=10.0)
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--group-chat")
    parser.add_argument("--dm-chat")
    parser.add_argument("--upload-group-chat")
    parser.add_argument("--upload-dm-chat")
    parser.add_argument("--file")
    parser.add_argument("--message", default="T19 smoke")
    return parser


def main() -> int:
    """运行 smoke 并以 JSON 输出安全摘要。"""

    arguments = _parser().parse_args()
    if arguments.event_timeout <= 0 or arguments.request_timeout <= 0:
        print(json.dumps({"configuration": "invalid_input"}, ensure_ascii=False))
        return 2
    try:
        result = asyncio.run(run_smoke(arguments))
    except ConfigError:
        result = {"configuration": "invalid_input"}
        status = 2
    except Exception as error:  # noqa: BLE001
        result = {"smoke": _classification(error, "transport_unknown")}
        status = 1
    else:
        status = 0
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
