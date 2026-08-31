"""验证多媒体出站的本地资源、native segment 和 adapter 交接边界。"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import inspect
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from adapter import MilkyAdapter
from milky.client import (
    MAX_LOCAL_MEDIA_BYTES,
    ActionError,
    SendResult,
    materialize_media_uri,
    validate_media_uri,
)
from milky.models import MilkyEnvelope
from outbound.materialization import OutboundMaterialization, validate_materialization
from outbound.sender import MilkyOutboundSender
from tests.fixtures.multimedia_inputs import (
    AGENT_ATTACHMENT_ENUMERATION,
    AGENT_NON_MEDIA_RESPONSES,
    HERMES_MATERIALIZATION_FIXTURES,
    MATERIALIZATION_BOUNDARY_FIXTURES,
    MEDIA_ENTRY_OWNERSHIP,
    SYNTHETIC_MEDIA_URIS,
)


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
    assert set(HERMES_MATERIALIZATION_FIXTURES) == {"image", "audio", "video", "document"}
    assert set(MATERIALIZATION_BOUNDARY_FIXTURES) == {
        "empty",
        "missing",
        "unconfirmed_local",
        "unknown_kind",
        "text_only",
    }
    assert all("/Users/" not in repr(value) for value in HERMES_MATERIALIZATION_FIXTURES.values())
    assert "Bearer " not in repr(HERMES_MATERIALIZATION_FIXTURES)


@pytest.mark.parametrize(
    ("value_name", "classification"),
    [
        ("empty", "invalid_input"),
        ("missing", "unsupported"),
        ("unconfirmed_local", "unsupported"),
        ("unknown_kind", "unsupported"),
        ("text_only", "unsupported"),
    ],
)
def test_materialization_result_boundary_is_typed_and_fail_closed(
    value_name: str, classification: str
) -> None:
    """缺失、未知 kind 和未确认路径不得越过 URI 校验边界。"""

    value = MATERIALIZATION_BOUNDARY_FIXTURES[value_name]
    with pytest.raises(ActionError) as error_info:
        validate_materialization(value, expected_kind="image")

    assert error_info.value.classification == classification
    if value:
        assert str(value) not in str(error_info.value)


def test_materialization_fixture_keeps_kind_uri_and_document_name() -> None:
    """四类合成 materialization 应保留类型、URI 和文档名。"""

    image = validate_materialization(HERMES_MATERIALIZATION_FIXTURES["image"])
    document = validate_materialization(HERMES_MATERIALIZATION_FIXTURES["document"])

    assert image.kind == "image"
    assert image.uri == "base64://fixture-image"
    assert document.kind == "document"
    assert document.file_name == "fixture-report.txt"


def test_local_dispatch_preserves_attachment_order_and_kind(tmp_path: Path) -> None:
    """同一 Agent turn 的四类本地附件应按顺序进入 native/upload 边界。"""

    client = MultimediaClient()
    sender = MilkyOutboundSender(client)
    adapter = object.__new__(MilkyAdapter)
    adapter._connected = True
    adapter._closed = False
    adapter._outbound = sender
    paths = {
        "image": tmp_path / "fixture-image.png",
        "audio": tmp_path / "fixture-audio.ogg",
        "video": tmp_path / "fixture-video.mp4",
        "document": tmp_path / "fixture-report.txt",
    }
    for kind, path in paths.items():
        path.write_bytes(f"fixture-{kind}".encode())

    async def scenario() -> None:
        await adapter.send_image_file("group:700000001", paths["image"])
        await adapter.send_voice("group:700000001", paths["audio"])
        await adapter.send_video("group:700000001", paths["video"])
        await adapter.send_document("group:700000001", paths["document"])

    asyncio.run(scenario())

    assert [item[0] for item in client.calls] == [
        "send_group_message",
        "send_group_message",
        "send_group_message",
        "upload_group_file",
    ]
    assert [item[1]["message"][0]["type"] for item in client.calls[:3]] == [
        "image",
        "record",
        "video",
    ]
    assert client.calls[3][1]["file_name"] == "fixture-report.txt"
    assert all("file" not in str(body.get("message", [])) for _, body in client.calls[:3])
    assert all(
        body["message"][0]["data"]["uri"].startswith("base64://") for _, body in client.calls[:3]
    )
    assert client.calls[3][1]["file_uri"].startswith("base64://")


@dataclass
class FakeHermesAgentDispatcher:
    """模拟 Hermes 对 Agent 文件枚举结果逐项分派。"""

    attachments: dict[str, Path]

    async def dispatch(self, adapter: MilkyAdapter, chat_id: str, output: object) -> list[object]:
        """只将明确枚举的附件交给 adapter，其他响应不伪装成媒体。"""

        if output in AGENT_NON_MEDIA_RESPONSES:
            return []
        results: list[object] = []
        for kind, _fixture_path in AGENT_ATTACHMENT_ENUMERATION:
            path = self.attachments[kind]
            if kind == "image":
                result = await adapter.send_image_file(chat_id, path)
            elif kind == "audio":
                result = await adapter.send_voice(chat_id, path)
            elif kind == "video":
                result = await adapter.send_video(chat_id, path)
            else:
                result = await adapter.send_document(chat_id, path, file_name="fixture-report.txt")
            results.append(result)
        return results


def test_agent_file_enumeration_reaches_each_native_boundary(tmp_path: Path) -> None:
    """Agent 枚举附件应逐项发送，shell 错误或 text-only 不应伪造媒体成功。"""

    client = MultimediaClient()
    sender = MilkyOutboundSender(client)
    adapter = object.__new__(MilkyAdapter)
    adapter._connected = True
    adapter._closed = False
    adapter._outbound = sender
    attachments = {kind: tmp_path / Path(path).name for kind, path in AGENT_ATTACHMENT_ENUMERATION}
    for kind, path in attachments.items():
        path.write_bytes(f"agent-{kind}".encode())
    dispatcher = FakeHermesAgentDispatcher(attachments)

    async def scenario() -> tuple[list[object], list[object], object]:
        attachments = await dispatcher.dispatch(adapter, "dm:800000001", "agent files")
        shell_error = await dispatcher.dispatch(
            adapter, "dm:800000001", AGENT_NON_MEDIA_RESPONSES[1]
        )
        text_result = await adapter.send("dm:800000001", AGENT_NON_MEDIA_RESPONSES[0])
        return attachments, shell_error, text_result

    attachments, shell_error, text_result = asyncio.run(scenario())

    assert all(result.success for result in attachments)
    assert shell_error == []
    assert text_result.success is True
    assert [name for name, _ in client.calls] == [
        "send_private_message",
        "send_private_message",
        "send_private_message",
        "upload_private_file",
        "send_private_message",
    ]
    assert all(
        body["message"][0]["data"]["uri"].startswith("base64://")
        for name, body in client.calls[:3]
        if name == "send_private_message"
    )


def test_adapter_validates_target_before_reading_local_media(tmp_path: Path) -> None:
    """非法目标必须在本地文件读取和 Milky 网络之前被拒绝。"""

    sender = RecordingMediaSender()
    adapter = object.__new__(MilkyAdapter)
    adapter._connected = True
    adapter._closed = False
    adapter._outbound = sender
    media_path = tmp_path / "fixture-image.png"
    media_path.write_bytes(b"fixture")

    result = asyncio.run(adapter.send_image_file("group:1", media_path))

    assert result.success is False
    assert result.error_kind == "invalid_input"
    assert sender.calls == []


def test_adapter_validates_document_name_before_reading_local_media(tmp_path: Path) -> None:
    """不安全文件名必须在本地文件读取和 Milky 网络前被拒绝。"""

    sender = RecordingMediaSender()
    adapter = object.__new__(MilkyAdapter)
    adapter._connected = True
    adapter._closed = False
    adapter._outbound = sender
    media_path = tmp_path / "fixture-report.txt"
    media_path.write_bytes(b"fixture")

    result = asyncio.run(
        adapter.send_document(
            "group:700000001",
            media_path,
            file_name="../fixture-report.txt",
        )
    )

    assert result.success is False
    assert result.error_kind == "invalid_input"
    assert sender.calls == []


def test_local_media_materializes_once_and_preserves_bytes(tmp_path: Path) -> None:
    """本地文件应只读一次并转换为可发送的 Base64 URI。"""

    media_path = tmp_path / "fixture-video.mp4"
    content = b"synthetic-video-bytes"
    media_path.write_bytes(content)

    uri = asyncio.run(materialize_media_uri(media_path, action="send_video"))

    assert uri == "base64://" + base64.b64encode(content).decode("ascii")


@pytest.mark.parametrize("input_kind", ["path", "path_object", "file_localhost"])
def test_local_media_accepts_supported_path_shapes(tmp_path: Path, input_kind: str) -> None:
    """本地字符串、Path 和 file://localhost 应共用一次读取边界。"""

    media_path = tmp_path / "fixture-local.bin"
    content = b"path-shape-fixture"
    media_path.write_bytes(content)
    values: dict[str, object] = {
        "path": str(media_path),
        "path_object": media_path,
        "file_localhost": f"file://localhost{media_path}",
    }

    uri = asyncio.run(materialize_media_uri(values[input_kind], action="send_image"))

    assert uri == "base64://" + base64.b64encode(content).decode("ascii")


@pytest.mark.parametrize(
    "value",
    [
        "https://media.example.invalid/fixture.bin",
        "base64://UklGRg==",
    ],
)
def test_materialize_media_preserves_explicit_uri(value: str) -> None:
    """远端和显式 Base64 URI 不应被读取、下载或重编码。"""

    assert asyncio.run(materialize_media_uri(value)) == value


@pytest.mark.parametrize(
    ("name", "value", "classification"),
    [
        ("missing", "/fixture/missing.mp4", "invalid_input"),
        ("empty", "__EMPTY__", "invalid_input"),
        ("too_large", "__TOO_LARGE__", "invalid_input"),
    ],
)
def test_local_media_boundary_rejects_invalid_files(
    tmp_path: Path, name: str, value: str, classification: str
) -> None:
    """不存在、空文件和超限文件必须在网络前被拒绝。"""

    if name == "empty":
        path = tmp_path / "empty.mp4"
        path.write_bytes(b"")
    elif name == "too_large":
        path = tmp_path / "too-large.mp4"
        with path.open("wb") as stream:
            stream.truncate(MAX_LOCAL_MEDIA_BYTES + 1)
    else:
        path = Path(value)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(materialize_media_uri(path, action="send_video"))

    assert error_info.value.classification == classification
    assert str(path) not in str(error_info.value)


@pytest.mark.parametrize(
    ("value", "classification"),
    [
        ("ftp://media.example.invalid/fixture.bin", "unsupported"),
        ("file://remote.example.invalid/fixture.bin", "invalid_input"),
        ("file://localhost", "invalid_input"),
    ],
)
def test_local_media_rejects_unknown_and_remote_file_schemes(
    value: str, classification: str
) -> None:
    """未知 scheme 和远端 file URI 必须在本地读取前失败。"""

    with pytest.raises(ActionError) as error_info:
        asyncio.run(materialize_media_uri(value, action="send_video"))

    assert error_info.value.classification == classification
    assert value not in str(error_info.value)


def test_local_media_accepts_exact_size_limit(tmp_path: Path) -> None:
    """恰好达到 8 MiB 上限的常规文件仍可被完整读取。"""

    media_path = tmp_path / "fixture-limit.bin"
    media_path.write_bytes(b"x" * MAX_LOCAL_MEDIA_BYTES)

    uri = asyncio.run(materialize_media_uri(media_path, action="send_video"))

    assert uri.startswith("base64://")
    assert len(uri) == len("base64://") + ((MAX_LOCAL_MEDIA_BYTES + 2) // 3) * 4


def test_local_media_rejects_directory(tmp_path: Path) -> None:
    """目录不能越过常规文件读取边界。"""

    directory = tmp_path / "fixture-directory"
    directory.mkdir()

    with pytest.raises(ActionError) as error_info:
        asyncio.run(materialize_media_uri(directory, action="send_video"))

    assert error_info.value.classification == "invalid_input"
    assert str(directory) not in str(error_info.value)


def test_media_entry_ownership_matrix_matches_adapter_refactor() -> None:
    """入口矩阵应区分 adapter 和 sender 的正式出站入口。"""

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

    candidates = []
    configured_root = os.environ.get("HERMES_SOURCE_ROOT")
    if configured_root:
        candidates.append(configured_root)
    candidates.extend(sys.path)
    for entry in candidates:
        root = Path(entry or ".").resolve()
        if (
            root != Path(__file__).resolve().parents[1]
            and (root / "gateway" / "platforms" / "base.py").is_file()
        ):
            return root
    return None


def test_actual_hermes_multiple_image_dispatch_uses_inherited_entries(tmp_path: Path) -> None:
    """Hermes 基类分流本地图片后，插件应读取并发送 native segment。"""

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
        local_image = tmp_path / "fixture-image.png"
        local_image.write_bytes(b"host-image")
        expected_local_image = "base64://" + base64.b64encode(b"host-image").decode("ascii")

        async def scenario() -> None:
            await adapter.send_multiple_images(
                "dm:800000001",
                [
                    ("https://media.example.invalid/fixture.png", "普通"),
                    ("https://media.example.invalid/fixture.gif", "动画"),
                    (f"file://{local_image}", "本地"),
                ],
            )
            await adapter.send_voice("dm:800000001", "base64://fixture-audio")
            await adapter.send_video("dm:800000001", "base64://fixture-video")
            await adapter.send_document(
                "dm:800000001",
                "base64://fixture-document",
                file_name="fixture-report.txt",
            )

        asyncio.run(scenario())
        assert [name for name, _ in sender.calls] == [
            "send_image",
            "send_image",
            "send_image",
            "send_voice",
            "send_video",
            "send_document",
        ]
        assert [call[1]["args"][1] for call in sender.calls] == [
            "https://media.example.invalid/fixture.png",
            "https://media.example.invalid/fixture.gif",
            expected_local_image,
            "base64://fixture-audio",
            "base64://fixture-video",
            "base64://fixture-document",
        ]
        assert "send_multiple_images" not in module.MilkyAdapter.__dict__
        assert "send_animation" not in module.MilkyAdapter.__dict__
        assert module.MilkyAdapter.send_animation is host_base.BasePlatformAdapter.send_animation
        assert (
            module.MilkyAdapter.send_multiple_images
            is host_base.BasePlatformAdapter.send_multiple_images
        )
        assert module.MilkyAdapter.send_voice is not host_base.BasePlatformAdapter.send_voice
        assert module.MilkyAdapter.send_video is not host_base.BasePlatformAdapter.send_video
        assert module.MilkyAdapter.send_document is not host_base.BasePlatformAdapter.send_document
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
def test_validate_media_uri_keeps_local_paths_out_of_uri_only_boundary(value: str) -> None:
    """只做 URI 形状校验时仍不能把本地路径误认成远端 URI。"""

    with pytest.raises(ActionError) as error_info:
        validate_media_uri(value)

    assert error_info.value.classification == "unsupported"
    assert value not in str(error_info.value)


@pytest.mark.parametrize(
    ("target", "method_name", "argument", "segment_type"),
    [
        ("group:700000001", "send_image", "https://media.example.invalid/fixture.png", "image"),
        ("dm:800000001", "send_image", "https://media.example.invalid/fixture.png", "image"),
        ("group:700000001", "send_voice", "base64://fixture-audio", "record"),
        ("dm:800000001", "send_voice", "base64://fixture-audio", "record"),
        ("group:700000001", "send_video", "https://media.example.invalid/fixture.mp4", "video"),
        ("dm:800000001", "send_video", "https://media.example.invalid/fixture.mp4", "video"),
    ],
)
def test_sender_native_media_uses_materialized_uri_and_keeps_caption_order(
    target: str, method_name: str, argument: str, segment_type: str
) -> None:
    """图片、语音和视频应进入 native segment，而不是路径文本。"""

    client = MultimediaClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(
        getattr(sender, method_name)(
            target,
            argument,
            caption="合成说明",
        )
    )

    assert result.success is True
    assert len(client.calls) == 1
    assert client.calls[0][0] == (
        "send_group_message" if target.startswith("group:") else "send_private_message"
    )
    body = client.calls[0][1]["message"]
    assert body[0] == {"type": "text", "data": {"text": "合成说明"}}
    assert body[1]["type"] == segment_type
    assert body[1]["data"]["uri"] == argument


def test_sender_text_only_uses_only_the_plain_message_action() -> None:
    """纯文本 turn 不应猜测附件或调用 upload。"""

    client = MultimediaClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send("group:700000001", "仅有文本"))

    assert result.success is True
    assert [name for name, _ in client.calls] == ["send_group_message"]
    assert client.calls[0][1]["message"] == [{"type": "text", "data": {"text": "仅有文本"}}]


def test_structured_attachment_dispatch_keeps_native_upload_boundary() -> None:
    """结构化附件逐项交接时应保持顺序和 native/upload 边界。"""

    client = MultimediaClient()
    sender = MilkyOutboundSender(client)
    attachments = (
        OutboundMaterialization("image", "base64://fixture-image"),
        OutboundMaterialization("audio", "base64://fixture-audio"),
        OutboundMaterialization("video", "base64://fixture-video"),
        OutboundMaterialization(
            "document", "base64://fixture-document", file_name="fixture-report.txt"
        ),
    )

    async def dispatch() -> list[object]:
        """模拟 Hermes 对同一 turn 的逐项附件交接。"""

        results: list[object] = []
        for attachment in attachments:
            if attachment.kind == "image":
                item = await sender.send_image("dm:800000001", attachment.uri)
            elif attachment.kind == "audio":
                item = await sender.send_voice("dm:800000001", attachment.uri)
            elif attachment.kind == "video":
                item = await sender.send_video("dm:800000001", attachment.uri)
            else:
                item = await sender.send_document(
                    "dm:800000001", attachment.uri, file_name=attachment.file_name
                )
            results.append(item)
        return results

    results = asyncio.run(dispatch())

    assert all(result.success for result in results)
    assert results[-1].message_id == "fixture-upload-private"
    assert [name for name, _ in client.calls] == [
        "send_private_message",
        "send_private_message",
        "send_private_message",
        "upload_private_file",
    ]
    assert [body["message"][0]["type"] for _, body in client.calls[:3]] == [
        "image",
        "record",
        "video",
    ]
    assert "message" not in client.calls[3][1]


@dataclass
class FailingAfterFirstMultimediaClient(MultimediaClient):
    """在第二个可能产生副作用的 Action 处返回协议拒绝。"""

    async def send_group_message(self, group_id: int, message: list[dict[str, Any]]) -> SendResult:
        if self.calls:
            self.calls.append(("send_group_message", {"group_id": group_id, "message": message}))
            raise ActionError("rejected", "send_group_message", "fixture rejection")
        return await super().send_group_message(group_id, message)


def test_fake_hermes_attachment_dispatch_stops_at_first_failure_without_fallback_or_retry() -> None:
    """fake Hermes 部分失败应保留已成功数量和位置，不能重复 Action。"""

    client = FailingAfterFirstMultimediaClient()
    sender = MilkyOutboundSender(client)
    attachments = (
        OutboundMaterialization("image", "base64://fixture-image"),
        OutboundMaterialization("video", "base64://fixture-video"),
        OutboundMaterialization(
            "document", "base64://fixture-document", file_name="fixture-report.txt"
        ),
    )

    async def dispatch() -> tuple[list[object], int | None]:
        """按宿主逐项 dispatch 规则交接并停止在首个失败处。"""

        results: list[object] = []
        for index, attachment in enumerate(attachments):
            if attachment.kind == "image":
                item = await sender.send_image("group:700000001", attachment.uri)
            elif attachment.kind == "video":
                item = await sender.send_video("group:700000001", attachment.uri)
            else:
                item = await sender.send_document(
                    "group:700000001", attachment.uri, file_name=attachment.file_name
                )
            results.append(item)
            if not item.success:
                return results, index
        return results, None

    results, failed_index = asyncio.run(dispatch())

    assert results[0].success is True
    assert results[1].success is False
    assert results[1].error_kind == "rejected"
    assert failed_index == 1
    assert len(results) == 2
    assert len(client.calls) == 2
    assert all(name != "upload_group_file" for name, _ in client.calls)


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


def test_adapter_media_methods_delegate_without_base_text_fallback(tmp_path: Path) -> None:
    """连接后的 adapter 各媒体入口应独立委托给 sender。"""

    sender = RecordingMediaSender()
    adapter = object.__new__(MilkyAdapter)
    adapter._connected = True
    adapter._closed = False
    adapter._outbound = sender
    local_files = {
        "image": tmp_path / "fixture-image.png",
        "audio": tmp_path / "fixture-audio.ogg",
        "video": tmp_path / "fixture-video.mp4",
        "document": tmp_path / "fixture-report.txt",
    }
    for kind, path in local_files.items():
        path.write_bytes(f"adapter-{kind}".encode())

    async def scenario() -> None:
        await adapter.send_image("dm:800000001", "https://media.example.invalid/a.png")
        await adapter.send_image_file(
            "dm:800000001", local_files["image"], hermes_extension="fixture"
        )
        await adapter.send_voice("dm:800000001", local_files["audio"])
        await adapter.send_video("dm:800000001", local_files["video"])
        await adapter.send_document("dm:800000001", local_files["document"])

    asyncio.run(scenario())

    assert [name for name, _ in sender.calls] == [
        "send_image",
        "send_image",
        "send_voice",
        "send_video",
        "send_document",
    ]
    assert [details["args"][1] for _, details in sender.calls] == [
        "https://media.example.invalid/a.png",
        "base64://" + base64.b64encode(b"adapter-image").decode("ascii"),
        "base64://" + base64.b64encode(b"adapter-audio").decode("ascii"),
        "base64://" + base64.b64encode(b"adapter-video").decode("ascii"),
        "base64://" + base64.b64encode(b"adapter-document").decode("ascii"),
    ]
    assert sender.calls[-1][1]["file_name"] == "fixture-report.txt"


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


def test_missing_local_media_is_rejected_without_network() -> None:
    """不存在的本地附件应在 Milky 网络边界前分类失败。"""

    client = MultimediaClient()
    adapter = object.__new__(MilkyAdapter)
    adapter._connected = True
    adapter._closed = False
    adapter._outbound = MilkyOutboundSender(client)
    result = asyncio.run(adapter.send_document("group:700000001", "/fixture/report.txt"))

    assert result.success is False
    assert result.error_kind == "invalid_input"
    assert client.calls == []
