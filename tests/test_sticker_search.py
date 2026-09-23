"""QQ 贴纸搜索和 opaque ID 发送的本地契约测试。"""

from __future__ import annotations

import asyncio
import base64
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import pytest

from outbound.sender import MilkyOutboundSender, OutboundSendResult
from outbound.tools import bind_sender, register_tools, unbind_sender
from stickers.maintenance import StickerMaintenanceService
from stickers.sending import (
    StickerSendService,
    parse_sticker_search_request,
    parse_sticker_send_request,
)

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
_GIF = base64.b64decode(
    "R0lGODlhAgACAIEAAP8AAAAAAAAAAAAAACH/C05FVFNDQVBFMi4wAwEAAAAh+QQAAgAAACwAAAAAAgACAAAIBgABCAQQEAAh+QQAAgAAACwAAAAAAgACAIEAAP8AAAAAAAAAAAAIBgABCAQQEAA7"
)


class _Sender:
    """记录一次贴纸发送。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def send_sticker(self, chat_key: str, uri: str) -> OutboundSendResult:
        self.calls.append((chat_key, uri))
        return OutboundSendResult(success=True, message_id="synthetic-message")


def _create_library(tmp_path: Path) -> tuple[str, str]:
    inbox = tmp_path / "stickers" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "one.png").write_bytes(_PNG)

    def vision(*_args: object, **_kwargs: object) -> str:
        return json.dumps(
            {
                "success": True,
                "analysis": json.dumps(
                    {
                        "emotion": "joy",
                        "tags": ["开心", "反应"],
                        "description": "表达开心",
                        "is_sticker": True,
                    },
                    ensure_ascii=False,
                ),
            },
            ensure_ascii=False,
        )

    service = StickerMaintenanceService(data_dir=tmp_path, vision_analyzer=vision)
    assert json.loads(asyncio.run(service.handle("sticker add")))["created"] == 1
    item = json.loads(asyncio.run(service.handle("sticker list")))["items"][0]
    return str(item["sticker_id"]), str(item["file_sha256"])


def _create_two_item_library(tmp_path: Path) -> tuple[str, str]:
    inbox = tmp_path / "stickers" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "one.png").write_bytes(_PNG)
    (inbox / "two.gif").write_bytes(_GIF)

    def vision(*_args: object, **_kwargs: object) -> str:
        return json.dumps(
            {
                "success": True,
                "analysis": json.dumps(
                    {
                        "emotion": "joy",
                        "tags": ["共同", "标签"],
                        "description": "共同描述",
                        "is_sticker": True,
                    },
                    ensure_ascii=False,
                ),
            },
            ensure_ascii=False,
        )

    service = StickerMaintenanceService(data_dir=tmp_path, vision_analyzer=vision)
    assert json.loads(asyncio.run(service.handle("sticker add")))["created"] == 2
    items = json.loads(asyncio.run(service.handle("sticker list")))["items"]
    ids = sorted(str(item["sticker_id"]) for item in items)
    return ids[0], ids[1]


def test_search_request_and_send_request_are_strict() -> None:
    assert parse_sticker_search_request({"tags": ["开心"]}).limit == 5
    assert parse_sticker_search_request({"emotion": "joy", "limit": 10}).limit == 10
    assert parse_sticker_send_request({"sticker_id": "opaque-id"}).sticker_id == "opaque-id"
    for value in ({"mode": "strict"}, {"limit": True}, {"tags": ["开心"], "limit": 11}):
        with pytest.raises((TypeError, ValueError)):
            parse_sticker_search_request(value)
    for value in (
        {"sticker_id": None},
        {"sticker_id": "opaque id"},
        {"sticker_id": "opaque-id", "tags": ["开心"]},
    ):
        with pytest.raises((TypeError, ValueError)):
            parse_sticker_send_request(value)


def test_search_returns_bounded_metadata_without_usage_changes(tmp_path: Path) -> None:
    sticker_id, _file_hash = _create_library(tmp_path)
    service = StickerSendService(data_dir=tmp_path)
    result = service.search(
        parse_sticker_search_request({"intent": "开心", "limit": 5}),
        "group:700000001",
    )
    assert result["status"] == "ok"
    assert result["items"] == [
        {
            "sticker_id": sticker_id,
            "emotion": "joy",
            "tags": ["开心", "反应"],
            "description": "表达开心",
        }
    ]
    store = sqlite3.connect(tmp_path / "stickers.db")
    assert store.execute("SELECT use_count FROM sticker_items").fetchone() == (0,)
    store.close()


def test_search_orders_all_matching_levels_and_applies_and_filters(tmp_path: Path) -> None:
    first_id, second_id = _create_two_item_library(tmp_path)
    store = sqlite3.connect(tmp_path / "stickers.db")
    store.execute(
        "UPDATE sticker_items SET description = CASE sticker_id WHEN ? THEN ? ELSE ? END, "
        "tags_json = CASE sticker_id WHEN ? THEN ? ELSE ? END",
        (
            first_id,
            "完整短语命中",
            "部分命中",
            first_id,
            json.dumps(["第一"], ensure_ascii=False),
            json.dumps(["第二"], ensure_ascii=False),
        ),
    )
    store.commit()
    store.close()

    service = StickerSendService(data_dir=tmp_path)
    phrase = service.search(
        parse_sticker_search_request({"intent": "完整短语", "limit": 1}),
        "group:700000001",
    )
    assert phrase["status"] == "ok"
    assert phrase["items"][0]["sticker_id"] == first_id

    tags = service.search(
        parse_sticker_search_request({"tags": ["第一", "第二"], "limit": 10}),
        "group:700000001",
    )
    assert [item["sticker_id"] for item in tags["items"]] == [first_id, second_id]

    and_filter = service.search(
        parse_sticker_search_request({"emotion": "joy", "tags": ["第一"]}),
        "group:700000001",
    )
    assert [item["sticker_id"] for item in and_filter["items"]] == [first_id]
    assert service.search(
        parse_sticker_search_request({"tags": ["不存在"]}), "group:700000001"
    ) == {
        "status": "no_match",
        "match_mode": "strict",
        "items": [],
    }


def test_id_send_is_exact_and_missing_file_is_classified(tmp_path: Path) -> None:
    sticker_id, _file_hash = _create_library(tmp_path)
    service = StickerSendService(data_dir=tmp_path)
    sender = _Sender()
    result = asyncio.run(service.send_id(sticker_id, "dm:800000001", sender))
    assert result == {"status": "sent", "message_id": "synthetic-message"}
    assert sender.calls and sender.calls[0][0] == "dm:800000001"

    library_file = next(
        path for path in (tmp_path / "stickers" / "library").rglob("*") if path.is_file()
    )
    library_file.unlink()
    failed = asyncio.run(service.send_id(sticker_id, "dm:800000001", sender))
    assert failed == {"status": "missing_file"}
    assert len(sender.calls) == 1


def test_search_handler_returns_only_bounded_items(monkeypatch, tmp_path: Path) -> None:
    _create_library(tmp_path)

    class Context:
        """提供合成 plugin-data 和 Tool 注册接口。"""

        def __init__(self) -> None:
            self.registered: list[dict[str, object]] = []

        def plugin_data_dir(self, _name: str) -> Path:
            return tmp_path

        def register_tool(self, **kwargs: object) -> None:
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
    handler = next(
        item["handler"] for item in context.registered if item["name"] == "sticker_search"
    )
    bind_sender(MilkyOutboundSender(object()))
    try:
        result = json.loads(asyncio.run(handler({"tags": ["开心"]})))
        invalid = json.loads(asyncio.run(handler({"limit": True})))
    finally:
        unbind_sender()
    assert result["status"] == "ok"
    assert set(result["items"][0]) == {"sticker_id", "emotion", "tags", "description"}
    assert invalid == {"status": "invalid_input"}
