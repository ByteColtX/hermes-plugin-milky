"""验证 trigger 阶段的分类资源、文件和 reply resolver。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, replace
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
        self,
        user_id: object,
        file_id: object,
        file_hash: object,
        *,
        is_self_send: object | None = None,
    ) -> object:
        """返回私聊文件的下载 URL。"""

        self.calls.append(("get_private_file_download_url", (user_id, file_id, file_hash)))
        return self.private_file_response

    async def get_forwarded_messages(self, forward_id: object) -> object:
        """返回完整 forward 内容。"""

        self.calls.append(("get_forwarded_messages", (forward_id,)))
        return self.forward_response

    async def get_message(
        self, message_scene: object, peer_id: object, message_seq: object
    ) -> object:
        """返回完整 reply 内容。"""

        self.calls.append(("get_message", (message_scene, peer_id, message_seq)))
        return self.message_response


class FakeHermesMedia:
    """提供可观察的 Hermes 远端 URL helper seam。"""

    def __init__(self) -> None:
        self.url_calls: list[tuple[str, str]] = []

    async def cache_image_from_url(self, url: str, ext: str = ".jpg") -> str:
        """记录并异步返回合成的本地图片路径。"""

        self.url_calls.append(("image", url))
        await asyncio.sleep(0)
        return f"/synthetic/hermes/img_fixture123456{ext}"

    async def cache_audio_from_url(self, url: str, ext: str = ".ogg") -> str:
        """记录并异步返回合成的本地音频路径。"""

        self.url_calls.append(("audio", url))
        await asyncio.sleep(0)
        return "/synthetic/hermes/audio.ogg"


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


def test_trigger_resolves_media_file_and_forward_with_separate_actions() -> None:
    """trigger 应分类查询资源，并只把已确认的图片/语音交给 Hermes。"""

    result = canonicalize_event(load_fixture("events/message_receive.group.all_segments.json"))
    assert result.value is not None
    client = make_client()
    hermes = FakeHermesMedia()

    resolved = asyncio.run(ResourceResolver(client, hermes).resolve(result.value))

    assert "[video:NOT SUPPORTED]" in resolved.body
    assert "[file:NOT SUPPORTED]" in resolved.body
    assert len(resolved.hermes_attachment_materializations) == 2
    assert [item.kind for item in resolved.hermes_attachment_materializations] == [
        "image",
        "audio",
    ]
    assert [item.reference_kind for item in resolved.hermes_attachment_materializations] == [
        "image",
        "record",
    ]
    assert "[img:img_fixture123456.jpg]" in resolved.body
    assert [name for name, _ in hermes.url_calls] == ["image", "audio"]
    assert [name for name, _ in client.calls].count("get_resource_temp_url") == 3
    assert [name for name, _ in client.calls].count("get_group_file_download_url") == 1
    assert [name for name, _ in client.calls].count("get_forwarded_messages") == 0
    assert [name for name, _ in client.calls].count("get_message") == 0
    assert resolved.replies[0].body == "被引用的中性内容"
    assert resolved.forwards[0].messages == ()


def test_inline_reply_does_not_query_get_message() -> None:
    """已有完整 inline reply 时只能使用内嵌内容。"""

    result = canonicalize_event(load_fixture("events/message_receive.group.all_segments.json"))
    assert result.value is not None
    client = make_client()

    resolved = asyncio.run(ResourceResolver(client, FakeHermesMedia()).resolve(result.value))

    assert resolved.replies[0].message_seq == 1000
    assert not any(name == "get_message" for name, _ in client.calls)


def test_complete_reply_does_not_remove_another_reply_failure_marker() -> None:
    """后续完整 reply 不得误删前一个失败 reply 的降级标记。"""

    result = canonicalize_event(load_fixture("events/message_receive.friend.json"))
    assert result.value is not None
    client = make_client()
    client.message_response = make_envelope({"message": {}})
    message = replace(
        result.value,
        body="[reply:NOT SUPPORTED]",
        reply_references=(
            ReplyReference(message_seq=1001),
            ReplyReference(message_seq=1000, complete=True),
        ),
    )

    resolved = asyncio.run(ResourceResolver(client, FakeHermesMedia()).resolve(message))

    assert resolved.body == "[reply:NOT SUPPORTED]"
    assert [reply.message_seq for reply in resolved.replies] == [1001, 1000]
    assert resolved.replies[1].body == ""


def test_missing_private_file_hash_is_unsupported_before_action() -> None:
    """私聊 file 缺 hash 时不得调用私聊下载 Action。"""

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["segments"] = [
        {"type": "file", "data": {"file_id": "fixture-private-file", "file_name": "a.zip"}}
    ]
    result = canonicalize_event(payload)
    assert result.value is not None
    client = make_client()

    resolved = asyncio.run(ResourceResolver(client, FakeHermesMedia()).resolve(result.value))

    assert resolved.body == "[file:NOT SUPPORTED]"
    assert resolved.diagnostics[0].classification == "unsupported"
    assert not any(name == "get_private_file_download_url" for name, _ in client.calls)


def test_file_without_hermes_resource_entry_never_downloads_or_exposes_url() -> None:
    """没有 Hermes 文件资源入口时只保留占位，不能把远端 URL 当本地路径。"""

    payload = load_fixture("events/message_receive.group.all_segments.json")
    result = canonicalize_event(payload)
    assert result.value is not None
    client = make_client()
    hermes = SimpleNamespace()

    resolved = asyncio.run(ResourceResolver(client, hermes).resolve(result.value))

    file_diagnostics = [item for item in resolved.diagnostics if item.reference_kind == "file"]
    assert file_diagnostics[0].classification == "unsupported"
    assert "[file:NOT SUPPORTED]" in resolved.body
    assert not any("cdn.example.invalid" in str(item) for item in resolved.diagnostics)
    assert not any(
        "/synthetic" in item.path for item in resolved.hermes_attachment_materializations
    )


def test_group_file_without_hermes_entry_keeps_file_placeholder() -> None:
    """群文件查询成功但没有 Hermes 入口时保留不可用占位。"""

    payload = load_fixture("events/message_receive.group.all_segments.json")
    result = canonicalize_event(payload)
    assert result.value is not None
    client = make_client()
    hermes = FakeHermesMedia()

    resolved = asyncio.run(ResourceResolver(client, hermes).resolve(result.value))

    file_materializations = [
        item
        for item in resolved.hermes_attachment_materializations
        if item.reference_kind == "file"
    ]
    assert file_materializations == []
    assert any(item.reference_kind == "file" for item in resolved.diagnostics)


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

    resolved = asyncio.run(ResourceResolver(client, FakeHermesMedia()).resolve(result.value))

    assert (
        "get_private_file_download_url",
        (800000001, "fixture-private-file", "fixture-hash"),
    ) in client.calls
    assert resolved.hermes_attachment_materializations == ()
    assert resolved.diagnostics[0].classification == "unsupported"


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


def test_image_placeholders_follow_helper_basenames_in_segment_order() -> None:
    """多张图片应按 segment 顺序使用 helper 返回路径的 basename。"""

    class SequentialHermes(FakeHermesMedia):
        """为每张图片返回可观察但不含真实路径的 basename。"""

        def __init__(self) -> None:
            super().__init__()
            self.paths = iter(
                ("/synthetic/hermes/img_first123456.jpg", "/synthetic/hermes/img_second123456.jpg")
            )

        async def cache_image_from_url(self, url: str, ext: str = ".jpg") -> str:
            """按调用顺序返回合成的 Hermes 落盘路径。"""

            self.url_calls.append(("image", url))
            return next(self.paths)

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["segments"] = [
        {
            "type": "image",
            "data": {
                "resource_id": "fixture-image-first",
                "temp_url": "https://cdn.example.invalid/first",
                "summary": "[图片]",
            },
        },
        {
            "type": "image",
            "data": {
                "resource_id": "fixture-image-second",
                "temp_url": "https://cdn.example.invalid/second",
                "summary": "[图片]",
            },
        },
    ]
    result = canonicalize_event(payload)
    assert result.value is not None

    resolved = asyncio.run(
        ResourceResolver(make_client(), SequentialHermes()).resolve(result.value)
    )

    assert resolved.body == "[img:img_first123456.jpg][img:img_second123456.jpg]"
    assert [
        item.path.rsplit("/", 1)[-1] for item in resolved.hermes_attachment_materializations
    ] == [
        "img_first123456.jpg",
        "img_second123456.jpg",
    ]


def test_failed_image_helper_keeps_typed_placeholder_without_path() -> None:
    """image helper 返回无效路径时应降级且不把路径写入正文。"""

    class InvalidPathHermes(FakeHermesMedia):
        """返回不应被接受为本地落盘路径的值。"""

        async def cache_image_from_url(self, url: str, ext: str = ".jpg") -> str:
            """返回伪造的远端 URL。"""

            self.url_calls.append(("image", url))
            return "https://cdn.example.invalid/not-local.jpg"

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["segments"] = [
        {
            "type": "image",
            "data": {
                "resource_id": "fixture-image-resource",
                "temp_url": "https://cdn.example.invalid/image",
                "summary": "[图片]",
            },
        }
    ]
    result = canonicalize_event(payload)
    assert result.value is not None

    resolved = asyncio.run(
        ResourceResolver(make_client(), InvalidPathHermes()).resolve(result.value)
    )

    assert resolved.body == "[img:NOT SUPPORTED]"
    assert resolved.hermes_attachment_materializations == ()
    assert all("cdn.example.invalid" not in str(item) for item in resolved.diagnostics)


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

    assert resolved.body == "[img:NOT SUPPORTED]"
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
    assert "[img:NOT SUPPORTED]" in resolved.body
    assert "[forward:fixture-forward-id]" in resolved.body
    assert {item.classification for item in resolved.diagnostics} >= {
        "rejected",
        "unsupported",
    }
    assert all("cdn.example.invalid" not in str(item) for item in resolved.diagnostics)
    assert resolved.forward_results[0].forward_id == "fixture-forward-id"
    assert resolved.forward_results[0].messages == ()
    assert not any(name == "get_forwarded_messages" for name, _ in client.calls)


def test_remote_reply_is_fetched_only_when_inline_content_is_incomplete() -> None:
    """缺少 inline 原文时才按消息序号查询 reply。"""

    client = make_client()
    message = SimpleNamespace(
        body="[reply:NOT SUPPORTED]",
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
    assert client.calls[0] == ("get_message", ("friend", 800000001, 1005))


def test_failed_remote_reply_retains_target_id_and_placeholder() -> None:
    """reply 查询失败时仍保留目标序号和可解释占位。"""

    class FailingReplyClient(FakeResourceClient):
        """让 reply 查询失败。"""

        async def get_message(
            self, message_scene: object, peer_id: object, message_seq: object
        ) -> object:
            """返回传输未知分类。"""

            self.calls.append(("get_message", (message_scene, peer_id, message_seq)))
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
        body="[reply:NOT SUPPORTED]",
        scene="friend",
        peer_id=800000001,
        self_id=900000001,
        media_resource_references=(),
        file_attachment_references=(),
        forward_references=(),
        reply_references=(ReplyReference(message_seq=1005),),
    )

    resolved = asyncio.run(ResourceResolver(client, SimpleNamespace()).resolve(message))

    assert resolved.body == "[reply:NOT SUPPORTED]"
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
            body="[img:fixture-a]",
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
            body="[img:fixture-b]",
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
