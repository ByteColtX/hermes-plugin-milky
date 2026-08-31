"""验证多媒体出站的本地资源、native segment 和 adapter 交接边界。"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from adapter import MilkyAdapter
from milky.client import ActionError, SendResult, validate_media_uri
from milky.models import MilkyEnvelope
from outbound.sender import MilkyOutboundSender
from tests.fixtures.multimedia_inputs import MEDIA_ENTRY_OWNERSHIP, SYNTHETIC_MEDIA_URIS


@dataclass
class MultimediaClient:
    """记录 group/dm message 和 upload Action 的脱敏 fake。"""

    error: ActionError | None = None
    message_sequences: list[int] = field(default_factory=lambda: [101, 102, 103, 104])
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def send_group_message(self, group_id: int, message: list[dict[str, Any]]) -> SendResult:
        self.calls.append(("send_group_message", {"group_id": group_id, "message": message}))
        if self.error is not None:
            raise self.error
        return SendResult(str(self.message_sequences.pop(0)))

    async def send_private_message(self, user_id: int, message: list[dict[str, Any]]) -> SendResult:
        self.calls.append(("send_private_message", {"user_id": user_id, "message": message}))
        if self.error is not None:
            raise self.error
        return SendResult(str(self.message_sequences.pop(0)))

    async def upload_group_file(
        self,
        group_id: int,
        file_uri: str,
        file_name: str,
        *,
        parent_folder_id: object = None,
    ) -> MilkyEnvelope:
        self.calls.append(
            (
                "upload_group_file",
                {
                    "group_id": group_id,
                    "file_uri": file_uri,
                    "file_name": file_name,
                    "parent_folder_id": parent_folder_id,
                },
            )
        )
        if self.error is not None:
            raise self.error
        return MilkyEnvelope("ok", 0, {"file_id": "fixture-upload-group"})

    async def upload_private_file(
        self, user_id: int, file_uri: str, file_name: str
    ) -> MilkyEnvelope:
        self.calls.append(
            (
                "upload_private_file",
                {"user_id": user_id, "file_uri": file_uri, "file_name": file_name},
            )
        )
        if self.error is not None:
            raise self.error
        return MilkyEnvelope("ok", 0, {"file_id": "fixture-upload-private"})


def test_multimedia_fixture_is_synthetic_and_covers_uri_boundaries() -> None:
    """多媒体 fixture 只包含合成地址，不携带主机路径、凭证或 live 地址。"""

    assert set(SYNTHETIC_MEDIA_URIS) == {
        "remote_image",
        "remote_animation",
        "inline_audio",
        "local_image",
        "local_audio",
        "local_video",
        "local_document",
        "empty",
        "unknown_scheme",
    }
    assert all(
        ".invalid" in value
        for name, value in SYNTHETIC_MEDIA_URIS.items()
        if name.startswith("remote")
    )
    rendered = repr(SYNTHETIC_MEDIA_URIS)
    assert "Bearer " not in rendered
    assert "/Users/" not in rendered


def test_media_entry_ownership_matrix_matches_adapter_refactor() -> None:
    """入口矩阵应区分 adapter 兼容桥、Hermes 继承入口和 sender 正式入口。"""

    adapter_methods = MilkyAdapter.__dict__
    sender_methods = MilkyOutboundSender.__dict__

    assert all(name in adapter_methods for name in MEDIA_ENTRY_OWNERSHIP["adapter_native"])
    assert all(name in sender_methods for name in MEDIA_ENTRY_OWNERSHIP["sender_native"])
    assert all(name not in adapter_methods for name in MEDIA_ENTRY_OWNERSHIP["adapter_removed"])
    assert all(name not in sender_methods for name in MEDIA_ENTRY_OWNERSHIP["sender_removed"])
    assert inspect.iscoroutinefunction(adapter_methods["send_image_file"])
    assert "send_animation" not in sender_methods
    assert "send_multiple_images" not in adapter_methods


def _hermes_host_root() -> Path | None:
    """从当前测试环境查找可选的 Hermes 源码根目录。"""

    for entry in sys.path:
        root = Path(entry or ".").resolve()
        if (
            root != Path(__file__).resolve().parents[1]
            and (root / "gateway" / "platforms" / "base.py").is_file()
        ):
            return root
    return None


def test_actual_hermes_multiple_image_dispatch_uses_inherited_entries() -> None:
    """Hermes 基类应负责 GIF/本地图片分流，插件只保留图片兼容桥。"""

    host_root = _hermes_host_root()
    if host_root is None:
        pytest.skip("Hermes host unavailable in the current test environment")

    original_path = list(sys.path)
    original_tools = sys.modules.get("tools")
    original_gateway_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "gateway" or name.startswith("gateway.")
    }
    module_name = "_milky_media_dispatch_host_test"
    try:
        sys.path[:] = [
            str(host_root),
            *(entry for entry in original_path if Path(entry or ".").resolve() != host_root),
            str(Path(__file__).resolve().parents[1]),
        ]
        loaded_tools = sys.modules.get("tools")
        tools_path = getattr(loaded_tools, "__file__", None)
        if isinstance(tools_path, str) and Path(tools_path).resolve() == (
            Path(__file__).resolve().parents[1] / "tools.py"
        ):
            sys.modules.pop("tools", None)
        for name in tuple(sys.modules):
            if name == "gateway" or name.startswith("gateway."):
                sys.modules.pop(name, None)
        host_base = pytest.importorskip("gateway.platforms.base")
        spec = importlib.util.spec_from_file_location(
            module_name, Path(__file__).resolve().parents[1] / "adapter.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        sender = RecordingMediaSender()
        adapter = object.__new__(module.MilkyAdapter)
        adapter._connected = True
        adapter._closed = False
        adapter._outbound = sender

        async def scenario() -> None:
            await adapter.send_multiple_images(
                "dm:800000001",
                [
                    ("https://media.example.invalid/fixture.png", "普通"),
                    ("https://media.example.invalid/fixture.gif", "动画"),
                    ("file:///fixture/workspace/image.png", "本地"),
                ],
            )

        asyncio.run(scenario())
        assert [name for name, _ in sender.calls] == ["send_image", "send_image", "send_image"]
        assert [call[1]["args"][1] for call in sender.calls] == [
            "https://media.example.invalid/fixture.png",
            "https://media.example.invalid/fixture.gif",
            "/fixture/workspace/image.png",
        ]
        assert "send_multiple_images" not in module.MilkyAdapter.__dict__
        assert "send_animation" not in module.MilkyAdapter.__dict__
        assert module.MilkyAdapter.send_animation is host_base.BasePlatformAdapter.send_animation
        assert (
            module.MilkyAdapter.send_multiple_images
            is host_base.BasePlatformAdapter.send_multiple_images
        )
    finally:
        sys.modules.pop(module_name, None)
        if original_tools is not None:
            sys.modules["tools"] = original_tools
        else:
            sys.modules.pop("tools", None)
        for name in tuple(sys.modules):
            if name == "gateway" or name.startswith("gateway."):
                sys.modules.pop(name, None)
        sys.modules.update(original_gateway_modules)
        sys.path[:] = original_path


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("http", "https://media.example.invalid/fixture.png"),
        ("base64", "base64://UklGRg=="),
    ],
)
def test_explicit_media_uris_are_preserved(name: str, value: str) -> None:
    """Hermes 已 materialize 的远端和内联 URI 不应被插件改写。"""

    assert validate_media_uri(value) == value
    assert name in {"http", "base64"}


@pytest.mark.parametrize(
    "value", ["/fixture/workspace/image.png", "file:///fixture/workspace/image.png"]
)
def test_local_media_is_unsupported_without_reading(value: str) -> None:
    """本地资源没有 Hermes 出站 seam 时必须在读取前降级。"""

    with pytest.raises(ActionError) as error_info:
        validate_media_uri(value)

    assert error_info.value.classification == "unsupported"
    assert value not in str(error_info.value)


@pytest.mark.parametrize(
    ("method_name", "argument", "segment_type"),
    [
        ("send_image", "https://media.example.invalid/fixture.png", "image"),
        ("send_voice", "base64://fixture-audio", "record"),
        ("send_video", "https://media.example.invalid/fixture.mp4", "video"),
    ],
)
def test_sender_native_media_uses_materialized_uri_and_keeps_caption_order(
    method_name: str, argument: str, segment_type: str
) -> None:
    """图片、语音和视频应进入 native segment，而不是路径文本。"""

    client = MultimediaClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(
        getattr(sender, method_name)(
            "group:700000001",
            argument,
            caption="合成说明",
        )
    )

    assert result.success is True
    assert len(client.calls) == 1
    body = client.calls[0][1]["message"]
    assert body[0] == {"type": "text", "data": {"text": "合成说明"}}
    assert body[1]["type"] == segment_type
    assert body[1]["data"]["uri"] == argument


def test_sender_routes_remote_animation_to_dm_without_download() -> None:
    """远端动画 URI 经统一图片入口保留并调用私聊 message Action。"""

    client = MultimediaClient()
    sender = MilkyOutboundSender(client)
    remote_uri = "https://media.example.invalid/fixture.gif"

    result = asyncio.run(sender.send_image("dm:800000001", remote_uri, caption="动画"))

    assert result.success is True
    assert client.calls[0][0] == "send_private_message"
    assert client.calls[0][1]["message"][-1] == {
        "type": "image",
        "data": {"uri": remote_uri},
    }


@pytest.mark.parametrize("target", ["group:700000001", "dm:800000001"])
def test_sender_uploads_materialized_file_with_explicit_file_uri(target: str) -> None:
    """Hermes 提供的文件 URI 必须走独立 upload。"""

    client = MultimediaClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(
        sender.send_document(
            target,
            "https://media.example.invalid/fixture-report.txt",
            file_name="fixture-report.txt",
        )
    )

    assert result.success is True
    action, body = client.calls[0]
    assert action == ("upload_group_file" if target.startswith("group:") else "upload_private_file")
    assert body["file_uri"] == "https://media.example.invalid/fixture-report.txt"
    assert body["file_name"] == "fixture-report.txt"
    assert "file_path" not in body


def test_sender_requires_file_name_for_explicit_base64_upload() -> None:
    """内联文件没有可安全推导的名称时应在网络前拒绝。"""

    client = MultimediaClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send_document("dm:800000001", "base64://synthetic-file"))

    assert result.success is False
    assert result.error_kind == "invalid_input"
    assert client.calls == []


def test_sender_preserves_media_failure_and_does_not_send_fallback() -> None:
    """协议拒绝应原样分类，且不能二次发送文本 fallback。"""

    client = MultimediaClient(error=ActionError("rejected", "send_group_message", "denied"))
    sender = MilkyOutboundSender(client)

    result = asyncio.run(
        sender.send_image("group:700000001", "https://media.example.invalid/fixture.png")
    )

    assert result.success is False
    assert result.error_kind == "rejected"
    assert len(client.calls) == 1
    assert client.calls[0][1]["message"][0]["type"] == "image"


def test_media_logs_do_not_include_uri_path_or_base64(caplog: pytest.LogCaptureFixture) -> None:
    """媒体 Action 失败日志只允许安全分类和路由字段。"""

    caplog.set_level(logging.DEBUG)
    client = MultimediaClient(error=ActionError("transport_unknown", "send_group_message", "x"))
    sender = MilkyOutboundSender(client)
    media_uri = "base64://synthetic-secret-payload"

    result = asyncio.run(sender.send_image("group:700000001", media_uri))

    assert result.error_kind == "transport_unknown"
    rendered = caplog.text
    assert media_uri not in rendered
    assert "send_group_message" not in rendered


@dataclass
class RecordingMediaSender:
    """记录 adapter native media 委托，不读取传入资源。"""

    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def _record(self, name: str, *args: Any, **kwargs: Any) -> SimpleNamespace:
        self.calls.append((name, {"args": args, **kwargs}))
        return SimpleNamespace(success=True, message_id=name)

    async def send_image(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        return await self._record("send_image", *args, **kwargs)

    async def send_voice(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        return await self._record("send_voice", *args, **kwargs)

    async def send_video(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        return await self._record("send_video", *args, **kwargs)

    async def send_document(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        return await self._record("send_document", *args, **kwargs)


def test_adapter_media_methods_delegate_without_base_text_fallback() -> None:
    """连接后的 adapter 各媒体入口应独立委托给 sender。"""

    sender = RecordingMediaSender()
    adapter = object.__new__(MilkyAdapter)
    adapter._connected = True
    adapter._closed = False
    adapter._outbound = sender

    async def scenario() -> None:
        await adapter.send_image("dm:800000001", "https://media.example.invalid/a.png")
        await adapter.send_image_file(
            "dm:800000001", "/fixture/image.png", hermes_extension="fixture"
        )
        await adapter.send_voice("dm:800000001", "/fixture/audio.ogg")
        await adapter.send_video("dm:800000001", "/fixture/video.mp4")
        await adapter.send_document("dm:800000001", "/fixture/report.txt")

    asyncio.run(scenario())

    assert [name for name, _ in sender.calls] == [
        "send_image",
        "send_image",
        "send_voice",
        "send_video",
        "send_document",
    ]


def test_adapter_media_gate_prevents_read_and_sender_call_after_disconnect(tmp_path: Path) -> None:
    """断开后的媒体入口应在 sender 和本地文件边界之前返回 unsupported。"""

    media_path = tmp_path / "not-read.png"
    media_path.write_bytes(b"should-not-be-read")
    sender = RecordingMediaSender()
    adapter = object.__new__(MilkyAdapter)
    adapter._connected = False
    adapter._closed = True
    adapter._outbound = sender

    result = asyncio.run(adapter.send_image_file("group:700000001", media_path))

    assert result.success is False
    assert result.error_kind == "unsupported"
    assert sender.calls == []


def test_media_transport_unknown_is_not_retried_or_fallbacked() -> None:
    """媒体 Action 的未知结果只能提交一次，并保留原始分类。"""

    client = MultimediaClient(
        error=ActionError("transport_unknown", "send_group_message", "unknown")
    )
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send_voice("group:700000001", "base64://fixture-audio"))

    assert result.success is False
    assert result.error_kind == "transport_unknown"
    assert len(client.calls) == 1
    assert client.calls[0][1]["message"][0]["type"] == "record"


def test_unmaterialized_hermes_media_is_rejected_without_network() -> None:
    """Hermes 未提供确认资源 URI 时 adapter 不读取路径或访问 Milky。"""

    client = MultimediaClient()
    adapter = object.__new__(MilkyAdapter)
    adapter._connected = True
    adapter._closed = False
    adapter._outbound = MilkyOutboundSender(client)
    result = asyncio.run(adapter.send_document("group:700000001", "/fixture/report.txt"))

    assert result.success is False
    assert result.error_kind == "unsupported"
    assert client.calls == []
