"""验证 trigger 阶段的分类资源、文件和 reply resolver。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from inbound.canonical import canonicalize_event
from inbound.extractor import MediaResourceReference, ReplyReference
from milky.client import ActionError
from milky.models import MilkyEnvelope
from milky.resources import ResourceResolver

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "protocol"


def load_fixture(relative_path: str) -> object:
    """读取脱敏协议 fixture。"""

    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


def test_resource_resolver_is_available_for_trigger_batches() -> None:
    """资源 resolver 应以显式 trigger 入口提供最小完整 API。"""

    result = canonicalize_event(load_fixture("events/message_receive.friend.json"))

    assert result.value is not None
    resolver = ResourceResolver(client=object(), hermes=object())

    resolved = asyncio.run(resolver.resolve(result.value))

    assert resolved.body == "朋友消息"
    assert resolved.hermes_attachment_materializations == ()


@dataclass
class FakeResourceClient:
    """记录 resolver 的 Milky Action，并返回脱敏的协议 envelope。"""

    resource_response: object
    group_file_response: object
    private_file_response: object
    forward_response: object
    message_response: object

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def get_resource_temp_url(self, resource_id: object) -> object:
        """返回 media resource 的临时 URL。"""

        self.calls.append(("get_resource_temp_url", (resource_id,)))
        return self.resource_response

    async def get_group_file_download_url(self, group_id: object, file_id: object) -> object:
        """返回群文件的下载 URL。"""

        self.calls.append(("get_group_file_download_url", (group_id, file_id)))
        return self.group_file_response

    async def get_private_file_download_url(
        self, user_id: object, file_id: object, file_hash: object
    ) -> object:
        """返回私聊文件的下载 URL。"""

        self.calls.append(("get_private_file_download_url", (user_id, file_id, file_hash)))
        return self.private_file_response

    async def get_forwarded_messages(self, forward_id: object) -> object:
        """返回完整 forward 内容。"""

        self.calls.append(("get_forwarded_messages", (forward_id,)))
        return self.forward_response

    async def get_message(self, message_seq: object) -> object:
        """返回完整 reply 内容。"""

        self.calls.append(("get_message", (message_seq,)))
        return self.message_response


@dataclass
class FakeCachedMedia:
    """模拟 Hermes base.cache_media_bytes 的返回值。"""

    path: str
    media_type: str
    kind: str
    display_name: str


class FakeHermesMedia:
    """提供可观察的 Hermes URL 和 bytes helper seam。"""

    def __init__(self) -> None:
        self.url_calls: list[tuple[str, str]] = []
        self.bytes_calls: list[tuple[bytes, str, str, str]] = []

    async def cache_image_from_url(self, url: str, ext: str = ".jpg") -> str:
        """记录并异步返回合成的本地图片路径。"""

        self.url_calls.append(("image", url))
        await asyncio.sleep(0)
        return "/synthetic/hermes/image.png"

    async def cache_audio_from_url(self, url: str, ext: str = ".ogg") -> str:
        """记录并异步返回合成的本地音频路径。"""

        self.url_calls.append(("audio", url))
        await asyncio.sleep(0)
        return "/synthetic/hermes/audio.ogg"

    def cache_media_bytes(
        self,
        data: bytes,
        *,
        filename: str = "",
        mime_type: str = "",
        default_kind: str | None = None,
    ) -> FakeCachedMedia:
        """记录已由安全 seam 提供的 bytes，并归类为对应 kind。"""

        self.bytes_calls.append((data, filename, mime_type, default_kind or ""))
        suffix = "document" if default_kind == "document" else "video"
        return FakeCachedMedia(
            f"/synthetic/hermes/{suffix}",
            mime_type,
            default_kind or "document",
            filename,
        )


def make_envelope(data: object) -> MilkyEnvelope:
    """构造已通过通用协议边界的 fake envelope。"""

    assert isinstance(data, dict)
    return MilkyEnvelope("ok", 0, data)


def make_client() -> FakeResourceClient:
    """以 fixture 构造不含可访问 URL 的 fake client。"""

    resource = load_fixture("actions/get_resource_temp_url.ok.json")
    group_file = load_fixture("actions/get_group_file_download_url.ok.json")
    private_file = load_fixture("actions/get_private_file_download_url.ok.json")
    forward = load_fixture("actions/get_forwarded_messages.ok.json")
    message = load_fixture("actions/get_message.ok.json")
    assert all(
        isinstance(value, dict) for value in (resource, group_file, private_file, forward, message)
    )
    resource["data"]["url"] = "https://cdn.example.invalid/media"
    group_file["data"]["download_url"] = "https://cdn.example.invalid/group-file"
    private_file["data"]["download_url"] = "https://cdn.example.invalid/private-file"
    return FakeResourceClient(
        make_envelope(resource["data"]),
        make_envelope(group_file["data"]),
        make_envelope(private_file["data"]),
        make_envelope(forward["data"]),
        make_envelope(message["data"]),
    )


async def fake_url_to_bytes(url: str) -> bytes:
    """模拟由外部安全组件提供的 URL-to-bytes seam。"""

    await asyncio.sleep(0)
    return b"synthetic bytes"


def test_trigger_resolves_media_file_and_forward_with_separate_actions() -> None:
    """trigger 应分别解析三类媒体、群文件和 forward，且 await URL helper。"""

    result = canonicalize_event(load_fixture("events/message_receive.group.all_segments.json"))
    assert result.value is not None
    client = make_client()
    hermes = FakeHermesMedia()

    resolved = asyncio.run(
        ResourceResolver(client, hermes, url_to_bytes=fake_url_to_bytes).resolve(result.value)
    )

    assert resolved.body == result.value.body
    assert len(resolved.hermes_attachment_materializations) == 4
    assert [item.kind for item in resolved.hermes_attachment_materializations] == [
        "image",
        "audio",
        "video",
        "document",
    ]
    assert [item.reference_kind for item in resolved.hermes_attachment_materializations] == [
        "image",
        "record",
        "video",
        "file",
    ][: len(resolved.hermes_attachment_materializations)]
    assert [name for name, _ in hermes.url_calls] == ["image", "audio"]
    assert len(hermes.bytes_calls) == 2
    assert [name for name, _ in client.calls].count("get_resource_temp_url") == 3
    assert [name for name, _ in client.calls].count("get_group_file_download_url") == 1
    assert [name for name, _ in client.calls].count("get_forwarded_messages") == 1
    assert [name for name, _ in client.calls].count("get_message") == 0
    assert resolved.replies[0].body == "被引用的中性内容"
    assert resolved.forwards[0].messages[0].body == "转发中的中性内容"


def test_inline_reply_does_not_query_get_message() -> None:
    """已有完整 inline reply 时只能使用内嵌内容。"""

    result = canonicalize_event(load_fixture("events/message_receive.group.all_segments.json"))
    assert result.value is not None
    client = make_client()

    resolved = asyncio.run(ResourceResolver(client, FakeHermesMedia()).resolve(result.value))

    assert resolved.replies[0].message_seq == 1000
    assert not any(name == "get_message" for name, _ in client.calls)


def test_missing_private_file_hash_is_unsupported_before_action() -> None:
    """私聊 file 缺 hash 时不得调用私聊下载 Action。"""

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["segments"] = [
        {"type": "file", "data": {"file_id": "fixture-private-file", "file_name": "a.zip"}}
    ]
    result = canonicalize_event(payload)
    assert result.value is not None
    client = make_client()

    resolved = asyncio.run(
        ResourceResolver(client, FakeHermesMedia(), url_to_bytes=fake_url_to_bytes).resolve(
            result.value
        )
    )

    assert resolved.body == "[文件不可用]"
    assert resolved.diagnostics[0].classification == "unsupported"
    assert not any(name == "get_private_file_download_url" for name, _ in client.calls)


def test_file_without_url_to_bytes_seam_never_downloads_or_exposes_url() -> None:
    """没有安全 bytes seam 时只保留占位，不能把远端 URL 当本地路径。"""

    payload = load_fixture("events/message_receive.group.all_segments.json")
    result = canonicalize_event(payload)
    assert result.value is not None
    client = make_client()
    hermes = SimpleNamespace()

    resolved = asyncio.run(ResourceResolver(client, hermes).resolve(result.value))

    file_diagnostics = [item for item in resolved.diagnostics if item.reference_kind == "file"]
    assert file_diagnostics[0].classification == "unsupported"
    assert "[文件不可用]" in resolved.body
    assert not any("cdn.example.invalid" in str(item) for item in resolved.diagnostics)
    assert not any(
        "/synthetic" in item.path for item in resolved.hermes_attachment_materializations
    )


def test_group_file_materialization_only_exposes_hermes_local_result() -> None:
    """群文件成功后只交付 Hermes materialization，不交付远端 URL。"""

    payload = load_fixture("events/message_receive.group.all_segments.json")
    result = canonicalize_event(payload)
    assert result.value is not None
    client = make_client()
    hermes = FakeHermesMedia()

    resolved = asyncio.run(
        ResourceResolver(client, hermes, url_to_bytes=fake_url_to_bytes).resolve(result.value)
    )

    file_materializations = [
        item
        for item in resolved.hermes_attachment_materializations
        if item.reference_kind == "file"
    ]
    assert len(file_materializations) == 1
    assert file_materializations[0].kind == "document"
    assert file_materializations[0].path == "/synthetic/hermes/document"
    assert "cdn.example.invalid" not in file_materializations[0].path
    assert hermes.bytes_calls[-1][3] == "document"


def test_private_file_with_hash_uses_peer_as_user_id() -> None:
    """私聊文件具备 hash 时使用 peer/user ID 和私聊下载 Action。"""

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["segments"] = [
        {
            "type": "file",
            "data": {
                "file_id": "fixture-private-file",
                "file_name": "fixture.zip",
                "file_size": 8,
                "file_hash": "fixture-hash",
            },
        }
    ]
    result = canonicalize_event(payload)
    assert result.value is not None
    client = make_client()

    resolved = asyncio.run(
        ResourceResolver(client, FakeHermesMedia(), url_to_bytes=fake_url_to_bytes).resolve(
            result.value
        )
    )

    assert (
        "get_private_file_download_url",
        (800000001, "fixture-private-file", "fixture-hash"),
    ) in client.calls
    assert resolved.hermes_attachment_materializations[0].kind == "document"


def test_inline_temp_url_skips_resource_action() -> None:
    """segment 已有临时 URL 时不必重复查询 resource ID。"""

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["segments"] = [
        {
            "type": "image",
            "data": {
                "resource_id": "fixture-image-resource",
                "temp_url": "https://cdn.example.invalid/inline-image",
            },
        }
    ]
    result = canonicalize_event(payload)
    assert result.value is not None
    client = make_client()
    hermes = FakeHermesMedia()

    asyncio.run(ResourceResolver(client, hermes).resolve(result.value))

    assert not any(name == "get_resource_temp_url" for name, _ in client.calls)
    assert hermes.url_calls == [("image", "https://cdn.example.invalid/inline-image")]


def test_malformed_resource_envelope_keeps_reference_diagnostic() -> None:
    """资源 Action 缺少 data.url 时应归类 malformed 且不调用 Hermes。"""

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["segments"] = [
        {"type": "image", "data": {"resource_id": "fixture-image-resource"}}
    ]
    result = canonicalize_event(payload)
    assert result.value is not None
    client = make_client()
    client.resource_response = make_envelope({})
    hermes = FakeHermesMedia()

    resolved = asyncio.run(ResourceResolver(client, hermes).resolve(result.value))

    assert resolved.body == "[图片不可用]"
    assert resolved.diagnostics[0].classification == "malformed"
    assert resolved.diagnostics[0].reference_id == "fixture-image-resource"
    assert hermes.url_calls == []


def test_resource_and_reply_failures_keep_body_and_safe_diagnostics() -> None:
    """Action 或 reply 失败时正文仍在，诊断不回显不可信响应。"""

    class FailingClient(FakeResourceClient):
        """让资源和 reply 查询返回分类错误。"""

        async def get_resource_temp_url(self, resource_id: object) -> object:
            """返回脱敏的协议拒绝。"""

            self.calls.append(("get_resource_temp_url", (resource_id,)))
            raise ActionError("rejected", "get_resource_temp_url", "rejected")

        async def get_forwarded_messages(self, forward_id: object) -> object:
            """返回脱敏的传输未知。"""

            self.calls.append(("get_forwarded_messages", (forward_id,)))
            raise ActionError("transport_unknown", "get_forwarded_messages", "unknown")

    payload = load_fixture("events/message_receive.group.all_segments.json")
    result = canonicalize_event(payload)
    assert result.value is not None
    client = FailingClient(
        make_client().resource_response,
        make_client().group_file_response,
        make_client().private_file_response,
        make_client().forward_response,
        make_client().message_response,
    )

    resolved = asyncio.run(ResourceResolver(client, SimpleNamespace()).resolve(result.value))

    assert "中性文本" in resolved.body
    assert "[图片不可用]" in resolved.body
    assert "[转发不可用]" in resolved.body
    assert {item.classification for item in resolved.diagnostics} >= {
        "rejected",
        "transport_unknown",
        "unsupported",
    }
    assert all("cdn.example.invalid" not in str(item) for item in resolved.diagnostics)
    assert resolved.forward_results[0].forward_id == "fixture-forward-id"
    assert resolved.forward_results[0].messages == ()


def test_remote_reply_is_fetched_only_when_inline_content_is_incomplete() -> None:
    """缺少 inline 原文时才按消息序号查询 reply。"""

    client = make_client()
    message = SimpleNamespace(
        body="[引用不可用]",
        scene="friend",
        peer_id=800000001,
        self_id=900000001,
        media_resource_references=(),
        file_attachment_references=(),
        forward_references=(),
        reply_references=(ReplyReference(message_seq=1005),),
    )

    resolved = asyncio.run(ResourceResolver(client, SimpleNamespace()).resolve(message))

    assert resolved.replies[0].body == "远端回复中的中性内容"
    assert [name for name, _ in client.calls] == ["get_message"]


def test_failed_remote_reply_retains_target_id_and_placeholder() -> None:
    """reply 查询失败时仍保留目标序号和可解释占位。"""

    class FailingReplyClient(FakeResourceClient):
        """让 reply 查询失败。"""

        async def get_message(self, message_seq: object) -> object:
            """返回传输未知分类。"""

            self.calls.append(("get_message", (message_seq,)))
            raise ActionError("transport_unknown", "get_message", "unknown")

    base_client = make_client()
    client = FailingReplyClient(
        base_client.resource_response,
        base_client.group_file_response,
        base_client.private_file_response,
        base_client.forward_response,
        base_client.message_response,
    )
    message = SimpleNamespace(
        body="[引用不可用]",
        scene="friend",
        peer_id=800000001,
        self_id=900000001,
        media_resource_references=(),
        file_attachment_references=(),
        forward_references=(),
        reply_references=(ReplyReference(message_seq=1005),),
    )

    resolved = asyncio.run(ResourceResolver(client, SimpleNamespace()).resolve(message))

    assert resolved.body == "[引用不可用]"
    assert resolved.replies[0].message_seq == 1005
    assert resolved.replies[0].diagnostics[0].reference_id == "1005"
    assert resolved.replies[0].diagnostics[0].classification == "transport_unknown"


def test_resolver_does_not_serialize_or_log_remote_reference() -> None:
    """materialization 和诊断不得把远端 URL 写入结果。"""

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["segments"] = [
        {
            "type": "image",
            "data": {"temp_url": "https://cdn.example.invalid/private-image"},
        }
    ]
    result = canonicalize_event(payload)
    assert result.value is not None
    client = make_client()
    hermes = FakeHermesMedia()

    resolved = asyncio.run(ResourceResolver(client, hermes).resolve(result.value))

    assert resolved.hermes_attachment_materializations[0].path.startswith("/synthetic/")
    assert all("cdn.example.invalid" not in str(item) for item in resolved.diagnostics)


def test_independent_trigger_resolutions_can_progress_concurrently() -> None:
    """不同消息的资源处理不应共享会阻塞彼此的 resolver 锁。"""

    class BlockingHermes(FakeHermesMedia):
        """等待两个资源都进入后再完成 helper。"""

        def __init__(self) -> None:
            super().__init__()
            self.started = 0
            self.both_started = asyncio.Event()
            self.release = asyncio.Event()

        async def cache_image_from_url(self, url: str, ext: str = ".jpg") -> str:
            """记录进入并等待统一释放。"""

            self.url_calls.append(("image", url))
            self.started += 1
            if self.started == 2:
                self.both_started.set()
            await self.release.wait()
            return f"/synthetic/hermes/image-{self.started}.png"

    async def run() -> tuple[object, object]:
        """并行触发两个 chat 的同类资源处理。"""

        client = make_client()
        hermes = BlockingHermes()
        resolver = ResourceResolver(client, hermes)
        first = SimpleNamespace(
            body="[图片]",
            scene="friend",
            peer_id=800000001,
            self_id=900000001,
            media_resource_references=(
                MediaResourceReference(kind="image", temp_url="https://cdn.example.invalid/a"),
            ),
            file_attachment_references=(),
            forward_references=(),
            reply_references=(),
        )
        second = SimpleNamespace(
            body="[图片]",
            scene="group",
            peer_id=700000001,
            self_id=900000001,
            media_resource_references=(
                MediaResourceReference(kind="image", temp_url="https://cdn.example.invalid/b"),
            ),
            file_attachment_references=(),
            forward_references=(),
            reply_references=(),
        )
        tasks = asyncio.gather(resolver.resolve(first), resolver.resolve(second))
        await asyncio.wait_for(hermes.both_started.wait(), timeout=1)
        hermes.release.set()
        return await tasks

    first_result, second_result = asyncio.run(run())

    assert first_result.hermes_attachment_materializations
    assert second_result.hermes_attachment_materializations
