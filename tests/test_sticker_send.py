"""QQ 贴纸 Agent Tool 的脱敏契约和 fake 出站测试。"""

from __future__ import annotations

import asyncio
import base64
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from milky.client import ActionError
from outbound.sender import MilkyOutboundSender, OutboundSendResult
from outbound.tools import bind_sender, register_tools, unbind_sender
from stickers.errors import StickerStorageError, StickerUnsupportedError
from stickers.maintenance import StickerMaintenanceService
from stickers.sending import (
    StickerSendService,
    _Match,
    _StickerCandidate,
    normalize_sticker_text,
    parse_sticker_query,
    tokenize_sticker_text,
)
from stickers.storage import SCHEMA_VERSION, StickerStore

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
_GIF = base64.b64decode(
    "R0lGODlhAgACAIEAAP8AAAAAAAAAAAAAACH/C05FVFNDQVBFMi4wAwEAAAAh+QQAAgAAACwAAAAAAgACAAAIBgABCAQQEAAh+QQAAgAAACwAAAAAAgACAIEAAP8AAAAAAAAAAAAIBgABCAQQEAA7"
)


def _vision(*, emotion: str = "joy", tags: list[str] | None = None) -> str:
    return json.dumps(
        {
            "success": True,
            "analysis": json.dumps(
                {
                    "emotion": emotion,
                    "tags": tags or ["开心", "反应"],
                    "description": "小图表达情绪",
                    "is_sticker": True,
                },
                ensure_ascii=False,
            ),
        },
        ensure_ascii=False,
    )


class FakeStickerSender:
    """记录专用 sticker sender 的调用和 URI。"""

    def __init__(self, result: OutboundSendResult | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.result = result or OutboundSendResult(success=True, message_id="msg-1")

    async def send_sticker(self, chat_key: str, uri: str) -> OutboundSendResult:
        self.calls.append((chat_key, uri))
        return self.result


class FakeMilkySendClient:
    """记录 Milky 原生消息 Action 的最小 fake。"""

    def __init__(self, result: object = None) -> None:
        self.calls: list[tuple[str, int, list[dict[str, object]]]] = []
        self.result = result

    async def send_group_message(self, group_id: int, message: list[dict[str, object]]) -> object:
        self.calls.append(("group", group_id, message))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result or type("Result", (), {"message_seq": "23"})()

    async def send_private_message(self, user_id: int, message: list[dict[str, object]]) -> object:
        self.calls.append(("dm", user_id, message))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result or type("Result", (), {"message_seq": "24"})()


def _create_sticker(tmp_path: Path) -> str:
    inbox = tmp_path / "stickers" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "reaction.png").write_bytes(_PNG)
    service = StickerMaintenanceService(
        data_dir=tmp_path,
        vision_analyzer=lambda *_args, **_kwargs: _vision(),
    )
    assert asyncio.run(service.add())["created"] == 1
    item = service.list()
    return str(item["items"][0]["sticker_id"])


def _create_two_stickers(tmp_path: Path) -> tuple[str, str]:
    """创建两个不同 hash 的合成贴纸。"""

    inbox = tmp_path / "stickers" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "reaction.png").write_bytes(_PNG)
    (inbox / "reaction.gif").write_bytes(_GIF)
    service = StickerMaintenanceService(
        data_dir=tmp_path,
        vision_analyzer=lambda *_args, **_kwargs: _vision(),
    )
    assert asyncio.run(service.add())["created"] == 2
    items = service.list()["items"]
    assert len(items) == 2
    return str(items[0]["sticker_id"]), str(items[1]["sticker_id"])


def test_optional_tokenizer_is_stable_and_query_rejects_untrusted_fields() -> None:
    assert normalize_sticker_text("  ＮＦＫＣ，开心！ ") == "nfkc 开心"
    first = tokenize_sticker_text("表达情绪")
    assert first == tokenize_sticker_text("表达情绪")
    assert first
    with pytest.raises((TypeError, ValueError)):
        parse_sticker_query({"sticker_id": "opaque"})


def test_empty_store_does_not_create_storage(tmp_path: Path) -> None:
    service = StickerSendService(data_dir=tmp_path)
    assert service.is_available() is False
    assert not (tmp_path / "stickers.db").exists()
    assert not (tmp_path / "stickers").exists()


def test_availability_requires_a_real_library_file(tmp_path: Path) -> None:
    _create_sticker(tmp_path)
    library_file = next(
        path for path in (tmp_path / "stickers" / "library").rglob("*") if path.is_file()
    )
    library_file.unlink()
    assert StickerSendService(data_dir=tmp_path).is_available() is False


def test_missing_selected_file_returns_missing_file_without_sending(tmp_path: Path) -> None:
    _create_sticker(tmp_path)
    next(path for path in (tmp_path / "stickers" / "library").rglob("*") if path.is_file()).unlink()
    sender = FakeStickerSender()
    result = asyncio.run(
        StickerSendService(data_dir=tmp_path).send(
            parse_sticker_query({"tags": ["开心"]}), "group:700000001", sender
        )
    )
    assert result == {"status": "missing_file"}
    assert sender.calls == []


def test_hash_or_format_failure_returns_storage_error_without_sending(tmp_path: Path) -> None:
    _create_sticker(tmp_path)
    library_file = next(
        path for path in (tmp_path / "stickers" / "library").rglob("*") if path.is_file()
    )
    library_file.write_bytes(b"fixture-not-an-image")
    sender = FakeStickerSender()
    result = asyncio.run(
        StickerSendService(data_dir=tmp_path).send(
            parse_sticker_query({"intent": "表达情绪"}), "group:700000001", sender
        )
    )
    assert result == {"status": "storage_error"}
    assert sender.calls == []


def test_schema_v2_migrates_usage_without_changing_existing_statistics(tmp_path: Path) -> None:
    store = StickerStore(data_dir=tmp_path)
    store.open()
    assert store.connection is not None
    conn = store.connection
    conn.execute(
        "INSERT INTO sticker_items(sticker_id, file_sha256, format, mime_type, size_bytes, "
        "detected_emotion, detected_tags_json, detected_description, emotion, tags_json, "
        "description, emotion_source, tags_source, description_source, created_at, updated_at, "
        "detected_at, use_count, last_used_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "old-id",
            "a" * 64,
            "png",
            "image/png",
            1,
            "joy",
            "[]",
            "old",
            "joy",
            "[]",
            "old",
            "vision",
            "vision",
            "vision",
            "now",
            "now",
            "now",
            4,
            "old-time",
        ),
    )
    conn.execute("DROP TABLE sticker_send_usage")
    conn.execute("UPDATE sticker_schema_meta SET value = '2' WHERE key = 'schema_version'")
    conn.commit()
    store.close()

    migrated = StickerStore(data_dir=tmp_path)
    migrated.open()
    assert migrated.connection is not None
    assert migrated.connection.execute(
        "SELECT value FROM sticker_schema_meta WHERE key = 'schema_version'"
    ).fetchone() == (str(SCHEMA_VERSION),)
    assert migrated.connection.execute(
        "SELECT use_count, last_used_at FROM sticker_items WHERE sticker_id = 'old-id'"
    ).fetchone() == (4, "old-time")
    assert migrated.connection.execute(
        "SELECT name FROM sqlite_master WHERE name = 'sticker_send_usage'"
    ).fetchone()
    migrated.close()


def test_unknown_schema_fails_closed_without_replacing_existing_database(tmp_path: Path) -> None:
    store = StickerStore(data_dir=tmp_path)
    store.open()
    assert store.connection is not None
    store.connection.execute(
        "UPDATE sticker_schema_meta SET value = '99' WHERE key = 'schema_version'"
    )
    store.connection.commit()
    store.close()

    with pytest.raises(StickerUnsupportedError):
        StickerStore(data_dir=tmp_path).open()
    assert (tmp_path / "stickers.db").is_file()


def test_sticker_service_matches_current_metadata_and_claims_once(tmp_path: Path) -> None:
    sticker_id = _create_sticker(tmp_path)
    service = StickerSendService(data_dir=tmp_path)
    sender = FakeStickerSender()
    result = asyncio.run(
        service.send(parse_sticker_query({"intent": "表达情绪"}), "group:700000001", sender)
    )
    assert result == {"status": "sent", "message_id": "msg-1"}
    assert len(sender.calls) == 1
    assert sender.calls[0][0] == "group:700000001"
    assert sender.calls[0][1].startswith("base64://")

    store = StickerStore(data_dir=tmp_path)
    store.open()
    assert store.connection is not None
    assert store.connection.execute(
        "SELECT use_count FROM sticker_items WHERE sticker_id = ?", (sticker_id,)
    ).fetchone() == (1,)
    assert store.connection.execute(
        "SELECT chat_key, sticker_id, use_count FROM sticker_send_usage"
    ).fetchone() == ("group:700000001", sticker_id, 1)
    store.close()


def test_sender_sticker_path_uses_one_image_segment_and_routes_target() -> None:
    client = FakeMilkySendClient()
    sender = MilkyOutboundSender(client)
    result = asyncio.run(sender.send_sticker("dm:800000001", "base64://fixture"))
    assert result.success is True
    assert result.message_id == "24"
    assert client.calls == [
        (
            "dm",
            800000001,
            [{"type": "image", "data": {"uri": "base64://fixture", "sub_type": "sticker"}}],
        )
    ]


def test_sender_sticker_path_preserves_remote_failure_without_retry() -> None:
    client = FakeMilkySendClient(ActionError("transport_unknown", "send_group_message", "unknown"))
    sender = MilkyOutboundSender(client)
    result = asyncio.run(sender.send_sticker("group:700000001", "base64://fixture"))
    assert result.success is False
    assert result.error_kind == "transport_unknown"
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "classification",
    ["rejected", "http_error", "transport_unknown"],
)
def test_remote_failure_is_not_retried_but_keeps_claim(tmp_path: Path, classification: str) -> None:
    sticker_id = _create_sticker(tmp_path)
    service = StickerSendService(data_dir=tmp_path)
    sender = FakeStickerSender(
        OutboundSendResult(success=False, error_kind=classification, error="safe")
    )
    result = asyncio.run(
        service.send(parse_sticker_query({"tags": ["开心"]}), "dm:800000001", sender)
    )
    assert result == {"status": classification}
    assert len(sender.calls) == 1
    store = StickerStore(data_dir=tmp_path)
    store.open()
    assert store.connection is not None
    assert store.connection.execute(
        "SELECT use_count FROM sticker_items WHERE sticker_id = ?", (sticker_id,)
    ).fetchone() == (1,)
    store.close()


def test_timeout_is_normalized_to_transport_unknown(tmp_path: Path) -> None:
    _create_sticker(tmp_path)
    sender = FakeStickerSender(
        OutboundSendResult(success=False, error_kind="timeout", error="safe")
    )
    result = asyncio.run(
        StickerSendService(data_dir=tmp_path).send(
            parse_sticker_query({"tags": ["开心"]}), "dm:800000001", sender
        )
    )
    assert result == {"status": "transport_unknown"}
    assert len(sender.calls) == 1


def test_concurrent_calls_claim_usage_once_per_call(tmp_path: Path) -> None:
    sticker_id = _create_sticker(tmp_path)
    first_sender = FakeStickerSender()
    second_sender = FakeStickerSender()
    query = parse_sticker_query({"tags": ["开心"]})

    async def run() -> tuple[dict[str, object], dict[str, object]]:
        return await asyncio.gather(
            StickerSendService(data_dir=tmp_path).send(query, "group:700000001", first_sender),
            StickerSendService(data_dir=tmp_path).send(query, "group:700000001", second_sender),
        )

    results = asyncio.run(run())
    assert all(result["status"] == "sent" for result in results)
    assert len(first_sender.calls) == 1
    assert len(second_sender.calls) == 1
    store = StickerStore(data_dir=tmp_path)
    store.open()
    assert store.connection is not None
    assert store.connection.execute(
        "SELECT use_count FROM sticker_items WHERE sticker_id = ?", (sticker_id,)
    ).fetchone() == (2,)
    store.close()


def test_claim_failure_does_not_send_or_retry(tmp_path: Path, monkeypatch) -> None:
    _create_sticker(tmp_path)
    sender = FakeStickerSender()

    def fail_claim(*_args: object, **_kwargs: object) -> None:
        raise StickerStorageError("fixture storage failure")

    monkeypatch.setattr(StickerSendService, "_claim_use", staticmethod(fail_claim))
    result = asyncio.run(
        StickerSendService(data_dir=tmp_path).send(
            parse_sticker_query({"tags": ["开心"]}), "dm:800000001", sender
        )
    )
    assert result == {"status": "storage_error"}
    assert sender.calls == []


def test_more_relevant_candidate_wins_over_recent_usage(tmp_path: Path) -> None:
    first_id, second_id = _create_two_stickers(tmp_path)
    store = StickerStore(data_dir=tmp_path)
    store.open()
    assert store.connection is not None
    store.connection.execute(
        "UPDATE sticker_items SET description = CASE sticker_id WHEN ? THEN ? ELSE ? END, "
        "tags_json = ?",
        (first_id, "高匹配", "共同", json.dumps(["开心"], ensure_ascii=False)),
    )
    store.connection.execute(
        "INSERT INTO sticker_send_usage(chat_key, sticker_id, last_used_at, use_count) "
        "VALUES (?, ?, ?, 1)",
        ("group:700000001", first_id, "2099-01-01T00:00:00+00:00"),
    )
    store.connection.commit()
    store.close()

    result = asyncio.run(
        StickerSendService(data_dir=tmp_path).send(
            parse_sticker_query({"intent": "高匹配"}), "group:700000001", FakeStickerSender()
        )
    )
    assert result["status"] == "sent"
    assert result["message_id"]
    assert first_id != second_id
    store = StickerStore(data_dir=tmp_path)
    store.open()
    assert store.connection is not None
    assert store.connection.execute(
        "SELECT use_count FROM sticker_items WHERE sticker_id = ?", (first_id,)
    ).fetchone() == (1,)
    assert store.connection.execute(
        "SELECT use_count FROM sticker_items WHERE sticker_id = ?", (second_id,)
    ).fetchone() == (0,)
    store.close()


def test_equal_candidates_keep_recent_candidate_eligible_with_oldest_first_weights(
    monkeypatch,
) -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE sticker_send_usage "
        "(chat_key TEXT, sticker_id TEXT, last_used_at TEXT, use_count INTEGER)"
    )
    recent = _StickerCandidate("recent", "a" * 64, "png", "image/png", 1, "joy", (), "", "")
    old = _StickerCandidate("old", "b" * 64, "png", "image/png", 1, "joy", (), "", "")
    connection.execute(
        "INSERT INTO sticker_send_usage VALUES (?, ?, ?, ?)",
        ("group:700000001", "recent", "2099-01-01T00:00:00+00:00", 1),
    )
    connection.commit()
    captured: dict[str, object] = {}

    def choose(
        population: list[_StickerCandidate], weights: list[int], *, k: int
    ) -> list[_StickerCandidate]:
        captured["population"] = population
        captured["weights"] = weights
        return [population[-1]]

    monkeypatch.setattr("stickers.sending.random.choices", choose)
    selected = StickerSendService._select_candidate(
        connection,
        [
            _Match(recent, "phrase", 1, 0),
            _Match(old, "phrase", 1, 0),
        ],
        "group:700000001",
    )
    assert selected == recent
    assert captured["population"] == [old, recent]
    assert captured["weights"] == [2, 1]


def test_registered_sticker_handler_checks_context_and_rejects_extra_fields(
    tmp_path: Path, monkeypatch
) -> None:
    class Context:
        def __init__(self) -> None:
            self.registered: list[dict[str, Any]] = []

        def plugin_data_dir(self, _name: str) -> Path:
            return tmp_path

        def plugin_db(self, _name: str, *, filename: str) -> sqlite3.Connection:
            return sqlite3.connect(tmp_path / filename, check_same_thread=False)

        def register_tool(self, **kwargs: Any) -> None:
            self.registered.append(kwargs)

    gateway = ModuleType("gateway")
    session_context = ModuleType("gateway.session_context")
    values = {
        "HERMES_SESSION_PLATFORM": "milky",
        "HERMES_SESSION_CHAT_ID": "group:700000001",
    }
    session_context.get_session_env = lambda name, default="": values.get(name, default)  # type: ignore[attr-defined]
    gateway.session_context = session_context  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gateway", gateway)
    monkeypatch.setitem(sys.modules, "gateway.session_context", session_context)

    context = Context()
    register_tools(context)
    sticker_handler = next(
        item["handler"] for item in context.registered if item["name"] == "sticker_send"
    )
    bind_sender(MilkyOutboundSender(object()))
    try:
        result = json.loads(asyncio.run(sticker_handler({"intent": "x", "session_id": "bad"})))
        assert result == {"status": "invalid_input"}
        assert not (tmp_path / "stickers.db").exists()
    finally:
        unbind_sender()


@pytest.mark.parametrize(
    ("platform", "chat_key", "expected"),
    [
        ("", "group:700000001", "missing_session_context"),
        ("other", "group:700000001", "unsupported"),
        ("milky", "", "unsupported"),
        ("milky", "temp:700000001", "unsupported"),
        ("milky", "group:10000", "unsupported"),
    ],
)
def test_sticker_handler_rejects_untrusted_session_context_before_storage_or_network(
    tmp_path: Path,
    monkeypatch,
    platform: str,
    chat_key: str,
    expected: str,
) -> None:
    class Context:
        def __init__(self) -> None:
            self.registered: list[dict[str, Any]] = []

        def plugin_data_dir(self, _name: str) -> Path:
            return tmp_path

        def register_tool(self, **kwargs: Any) -> None:
            self.registered.append(kwargs)

    gateway = ModuleType("gateway")
    session_context = ModuleType("gateway.session_context")
    values = {
        "HERMES_SESSION_PLATFORM": platform,
        "HERMES_SESSION_CHAT_ID": chat_key,
    }
    session_context.get_session_env = lambda name, default="": values.get(name, default)  # type: ignore[attr-defined]
    gateway.session_context = session_context  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gateway", gateway)
    monkeypatch.setitem(sys.modules, "gateway.session_context", session_context)

    context = Context()
    register_tools(context)
    handler = next(item["handler"] for item in context.registered if item["name"] == "sticker_send")
    client = FakeMilkySendClient()
    bind_sender(MilkyOutboundSender(client))
    try:
        result = json.loads(asyncio.run(handler({"intent": "表达情绪"})))
    finally:
        unbind_sender()
    assert result == {"status": expected}
    assert client.calls == []
    assert not (tmp_path / "stickers.db").exists()


def test_registered_handler_uses_task_local_target_and_allows_repeated_calls(
    tmp_path: Path, monkeypatch
) -> None:
    _create_sticker(tmp_path)

    class Context:
        def __init__(self) -> None:
            self.registered: list[dict[str, Any]] = []

        def plugin_data_dir(self, _name: str) -> Path:
            return tmp_path

        def register_tool(self, **kwargs: Any) -> None:
            self.registered.append(kwargs)

    gateway = ModuleType("gateway")
    session_context = ModuleType("gateway.session_context")
    values = {
        "HERMES_SESSION_PLATFORM": "milky",
        "HERMES_SESSION_CHAT_ID": "dm:800000001",
    }
    session_context.get_session_env = lambda name, default="": values.get(name, default)  # type: ignore[attr-defined]
    gateway.session_context = session_context  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gateway", gateway)
    monkeypatch.setitem(sys.modules, "gateway.session_context", session_context)

    context = Context()
    register_tools(context)
    available_service = StickerSendService(plugin_context=context)
    available_store = available_service._new_store()
    available_store.open(read_only=True, create_dirs=False)
    assert available_store.connection is not None
    assert available_store.paths is not None
    available_candidates = available_service._read_candidates(
        available_store.connection, available_store.paths, require_file=True
    )
    available_store.close()
    assert available_candidates
    assert available_service.is_available() is True
    sticker_tool = next(item for item in context.registered if item["name"] == "sticker_send")
    assert sticker_tool["check_fn"]() is True
    handler = sticker_tool["handler"]
    client = FakeMilkySendClient()
    bind_sender(MilkyOutboundSender(client))
    try:
        first = json.loads(asyncio.run(handler({"tags": ["开心"]})))
        second = json.loads(asyncio.run(handler({"tags": ["开心"]})))
    finally:
        unbind_sender()

    assert first["status"] == "sent"
    assert second["status"] == "sent"
    assert first.keys() == second.keys() == {"status", "message_id"}
    assert len(client.calls) == 2
    assert all(call[0] == "dm" and call[1] == 800000001 for call in client.calls)
    assert all(len(call[2]) == 1 for call in client.calls)
    assert all(call[2][0]["type"] == "image" for call in client.calls)
    assert all(call[2][0]["data"]["sub_type"] == "sticker" for call in client.calls)
