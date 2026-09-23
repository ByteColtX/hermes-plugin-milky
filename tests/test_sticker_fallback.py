"""验证贴纸显式兜底、浏览和无副作用备选回执。"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import pytest

from outbound import tools
from outbound.sender import MilkyOutboundSender, OutboundSendResult
from stickers.sending import StickerSendService, parse_sticker_search_request
from stickers.storage import StickerStore
from tests.test_sticker_search import _create_library, _create_two_item_library


@pytest.mark.parametrize(
    "args,mode",
    [
        ({}, "browse"),
        ({"limit": 2}, "browse"),
        ({"tags": ["开心"]}, "strict"),
        ({"mode": "strict", "emotion": "joy"}, "strict"),
        ({"mode": "fallback", "intent": "缺失", "tags": ["开心"]}, "fallback"),
        ({"mode": "fallback", "intent": "缺失", "emotion": "joy"}, "fallback"),
        ({"mode": "browse"}, "browse"),
    ],
)
def test_search_mode_defaults(args, mode) -> None:
    assert parse_sticker_search_request(args).mode == mode


@pytest.mark.parametrize(
    "args",
    [
        None,
        [],
        {"mode": None},
        {"mode": []},
        {"mode": "other"},
        {"mode": "strict"},
        {"mode": "fallback"},
        {"mode": "fallback", "intent": "缺失"},
        {"mode": "fallback", "emotion": "joy"},
        {"mode": "browse", "intent": "x"},
        {"intent": None},
        {"emotion": None},
        {"tags": None},
        {"tags": []},
        {"tags": ["Ａ", "a"]},
        {"tags": ["x" * 17]},
        {"tags": ["!"]},
        {"intent": "x" * 65},
        {"intent": "https://invalid.test"},
        {"emotion": "invalid"},
        {"limit": True},
        {"limit": 0},
        {"limit": 11},
        {"limit": 1.0},
        {"limit": None},
        {"sticker_id": "a"},
        {"chat_id": "group:700000001"},
        {"path": "/synthetic"},
        {"url": "https://invalid.test"},
        {"category": "x"},
        {"keyword": "x"},
        {"index": 1},
        {"page": 1},
    ],
)
def test_invalid_search_fails_before_service(monkeypatch, args) -> None:
    def fail(*_args, **_kwargs):
        pytest.fail("非法请求不得访问会话或存储")

    monkeypatch.setattr(tools, "_sticker_session_chat_key", fail)
    assert json.loads(asyncio.run(tools._handle_sticker_search(args))) == {
        "status": "invalid_input"
    }


def test_schema_declares_modes_and_bounded_metadata() -> None:
    schema = tools.STICKER_SEARCH_SCHEMA["parameters"]
    assert set(schema["properties"]) == {"mode", "intent", "emotion", "tags", "limit"}
    assert schema["properties"]["mode"]["enum"] == ["strict", "fallback", "browse"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["tags"]["uniqueItems"] is True
    assert len(schema["oneOf"]) == 3


def _snapshot(root: Path) -> tuple:
    with sqlite3.connect(root / "stickers.db") as connection:
        return tuple(connection.iterdump())


def test_modes_keep_filters_and_stable_order_without_writes(tmp_path: Path) -> None:
    first, second = _create_two_item_library(tmp_path)
    with sqlite3.connect(tmp_path / "stickers.db") as connection:
        connection.execute(
            "UPDATE sticker_items SET tags_json=? WHERE sticker_id=?", (json.dumps(["共同"]), first)
        )
    service = StickerSendService(data_dir=tmp_path)
    before = _snapshot(tmp_path)
    query = {"intent": "unmatchedsynthetic", "emotion": "joy", "tags": ["共同", "标签"]}
    strict = service.search(parse_sticker_search_request(query), "group:700000001")
    assert strict == {"status": "no_match", "match_mode": "strict", "items": []}
    fallback = service.search(
        parse_sticker_search_request({**query, "mode": "fallback"}), "group:700000001"
    )
    assert fallback["match_mode"] == "fallback"
    assert [item["sticker_id"] for item in fallback["items"]] == [second, first]
    assert (
        service.search(
            parse_sticker_search_request({**query, "mode": "fallback"}), "group:700000001"
        )
        == fallback
    )
    for filters in ({"emotion": "anger"}, {"tags": ["不存在"]}):
        result = service.search(
            parse_sticker_search_request({**query, **filters, "mode": "fallback"}),
            "group:700000001",
        )
        assert result == {"status": "no_match", "match_mode": "fallback", "items": []}
    browse = service.search(parse_sticker_search_request({"limit": 1}), "group:700000001")
    assert browse["match_mode"] == "browse"
    assert [item["sticker_id"] for item in browse["items"]] == [first]
    assert _snapshot(tmp_path) == before


def test_empty_missing_and_readonly_store(tmp_path: Path, monkeypatch) -> None:
    service = StickerSendService(data_dir=tmp_path / "absent")
    assert service.search(parse_sticker_search_request({}), "group:700000001") == {
        "status": "unsupported"
    }
    assert not (tmp_path / "absent").exists()
    store = StickerStore(data_dir=tmp_path)
    store.open()
    store.close()
    service = StickerSendService(data_dir=tmp_path)
    for args in ({}, {"emotion": "joy"}, {"mode": "fallback", "intent": "x", "emotion": "joy"}):
        request = parse_sticker_search_request(args)
        assert service.search(request, "group:700000001") == {
            "status": "no_match",
            "match_mode": request.mode,
            "items": [],
        }

    def fail(*_args, **_kwargs):
        pytest.fail("只读打开不得调用写入 factory 或迁移")

    monkeypatch.setattr(StickerStore, "_initialize_schema", fail)
    store = StickerStore(data_dir=tmp_path, db_factory=fail)
    store.open(read_only=True, create_dirs=False)
    with pytest.raises(sqlite3.OperationalError):
        store.connection.execute("DELETE FROM sticker_items")
    store.close()


def test_readonly_default_host_path_does_not_create_directory(tmp_path: Path, monkeypatch) -> None:
    constants = ModuleType("hermes_constants")
    constants.get_hermes_home = lambda: tmp_path
    monkeypatch.setitem(sys.modules, "hermes_constants", constants)
    assert StickerSendService().is_available() is False
    assert not (tmp_path / "plugin-data").exists()


@pytest.mark.parametrize("mutation", ["missing", "index", "description", "tags", "emotion", "url"])
def test_all_modes_filter_invalid_candidates(tmp_path: Path, mutation: str) -> None:
    _create_library(tmp_path)
    with sqlite3.connect(tmp_path / "stickers.db") as connection:
        if mutation == "missing":
            next(
                path for path in (tmp_path / "stickers/library").rglob("*") if path.is_file()
            ).unlink()
        elif mutation == "index":
            connection.execute("UPDATE sticker_files SET size_bytes=size_bytes+1")
        elif mutation == "description":
            connection.execute("UPDATE sticker_items SET description=?", ("x" * 21,))
        elif mutation == "tags":
            connection.execute("UPDATE sticker_items SET tags_json=?", (json.dumps(["Ａ", "a"]),))
        elif mutation == "emotion":
            connection.execute("UPDATE sticker_items SET emotion='invalid'")
        else:
            connection.execute("UPDATE sticker_items SET description='https://invalid.test'")
    service = StickerSendService(data_dir=tmp_path)
    for args in ({}, {"emotion": "joy"}, {"mode": "fallback", "intent": "x", "emotion": "joy"}):
        result = service.search(parse_sticker_search_request(args), "group:700000001")
        assert result["status"] == "no_match" and result["items"] == []


def _bind_context(monkeypatch, root: Path, platform="milky", chat="group:700000001") -> None:
    context = ModuleType("gateway.session_context")
    context.get_session_env = lambda key, default="": {
        "HERMES_SESSION_PLATFORM": platform,
        "HERMES_SESSION_CHAT_ID": chat,
    }.get(key, default)
    monkeypatch.setitem(sys.modules, "gateway.session_context", context)
    monkeypatch.setattr(tools, "_ACTIVE_STICKER_SERVICE", StickerSendService(data_dir=root))


class _Client:
    """记录合成 Action 调用次数。"""

    def __init__(self, outcome="sent") -> None:
        self.calls = []
        self.outcome = outcome

    async def send_sticker(self, chat_key, uri):
        self.calls.append((chat_key, uri))
        return OutboundSendResult(
            success=self.outcome == "sent",
            message_id="synthetic" if self.outcome == "sent" else None,
            error_kind=None if self.outcome == "sent" else self.outcome,
        )


def test_no_match_alternatives_require_explicit_id_and_do_not_write(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    sticker_id, _ = _create_library(tmp_path)
    _bind_context(monkeypatch, tmp_path)
    sender = _Client()
    monkeypatch.setattr(tools, "_ACTIVE_SENDER", sender)
    query = {"intent": "unmatchedsynthetic", "emotion": "joy"}
    before = _snapshot(tmp_path)
    caplog.set_level("INFO", logger=tools.logger.name)
    result = json.loads(asyncio.run(tools._handle_sticker_send(query)))
    fallback = json.loads(asyncio.run(tools._handle_sticker_search({**query, "mode": "fallback"})))
    assert result == {"status": "no_match", "alternatives": fallback["items"]}
    assert result["alternatives"][0]["sticker_id"] == sticker_id
    assert set(result["alternatives"][0]) == {"sticker_id", "emotion", "tags", "description"}
    assert json.loads(
        asyncio.run(tools._handle_sticker_send({"intent": "unmatchedsynthetic"}))
    ) == {"status": "no_match", "alternatives": []}
    assert sender.calls == [] and _snapshot(tmp_path) == before
    assert "unmatchedsynthetic" not in caplog.text and "表达开心" not in caplog.text
    assert str(tmp_path) not in caplog.text and sticker_id not in caplog.text
    assert json.loads(asyncio.run(tools._handle_sticker_send({"sticker_id": sticker_id}))) == {
        "status": "sent",
        "message_id": "synthetic",
    }
    assert len(sender.calls) == 1


@pytest.mark.parametrize("status", ["http_error", "malformed", "transport_unknown"])
def test_explicit_id_uncertain_action_is_not_retried(tmp_path, monkeypatch, status) -> None:
    sticker_id, _ = _create_library(tmp_path)
    _bind_context(monkeypatch, tmp_path)
    sender = _Client(status)
    monkeypatch.setattr(tools, "_ACTIVE_SENDER", sender)
    assert json.loads(asyncio.run(tools._handle_sticker_send({"sticker_id": sticker_id}))) == {
        "status": status
    }
    assert len(sender.calls) == 1


@pytest.mark.parametrize(
    "platform,chat,status",
    [
        ("", "", "missing_session_context"),
        ("other", "group:700000001", "unsupported"),
        ("milky", "temp:700000001", "unsupported"),
        ("milky", "bad", "unsupported"),
    ],
)
def test_invalid_context_search_never_opens_storage(
    tmp_path, monkeypatch, platform, chat, status
) -> None:
    _bind_context(monkeypatch, tmp_path, platform, chat)
    monkeypatch.setattr(tools, "_ACTIVE_SENDER", object())

    def fail(*_args):
        pytest.fail("非法上下文不得读库")

    monkeypatch.setattr(StickerSendService, "_new_store", fail)
    assert json.loads(asyncio.run(tools._handle_sticker_search({}))) == {"status": status}


def test_unbound_service_and_sender_fail_closed(tmp_path, monkeypatch) -> None:
    _bind_context(monkeypatch, tmp_path)
    monkeypatch.setattr(tools, "_ACTIVE_SENDER", MilkyOutboundSender(object()))
    monkeypatch.setattr(tools, "_ACTIVE_STICKER_SERVICE", None)
    assert json.loads(asyncio.run(tools._handle_sticker_search({}))) == {"status": "unsupported"}
    monkeypatch.setattr(tools, "_ACTIVE_STICKER_SERVICE", StickerSendService(data_dir=tmp_path))
    tools.unbind_sender()
    assert json.loads(asyncio.run(tools._handle_sticker_search({}))) == {"status": "unsupported"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("sticker_id", "bad id"),
        ("emotion", "bad"),
        ("tags", ["a", "Ａ"]),
        ("description", "x" * 21),
        ("path", "/synthetic"),
    ],
)
def test_serializer_rejects_invalid_metadata(field, value) -> None:
    item = {"sticker_id": "id", "emotion": "joy", "tags": ["a"], "description": "test"}
    item[field] = value
    for result, name in [
        ({"status": "ok", "match_mode": "browse", "items": [item]}, "sticker_search"),
        ({"status": "no_match", "alternatives": [item]}, "sticker_send"),
    ]:
        assert json.loads(tools._sticker_result(result, name)) == {"status": "malformed"}


def test_limits_and_alternatives_are_consistent(tmp_path, monkeypatch) -> None:
    """超过上限的合成库仍只交付稳定、有界且去重的元数据。"""
    import hashlib
    import io

    from PIL import Image

    _create_library(tmp_path)
    with sqlite3.connect(tmp_path / "stickers.db") as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(sticker_items)")]
        original = dict(
            zip(columns, connection.execute("SELECT * FROM sticker_items").fetchone(), strict=True)
        )
        connection.execute("DELETE FROM sticker_items")
        connection.execute("DELETE FROM sticker_files")
        for index in range(12):
            image = Image.new("RGB", (2, 2), (index, 10, 20))
            stream = io.BytesIO()
            image.save(stream, format="PNG")
            data = stream.getvalue()
            digest = hashlib.sha256(data).hexdigest()
            path = tmp_path / "stickers" / "library" / digest[:2] / (digest + ".png")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            row = {
                **original,
                "sticker_id": f"id-{index:02}",
                "file_sha256": digest,
                "format": "png",
                "mime_type": "image/png",
                "size_bytes": len(data),
            }
            connection.execute(
                "INSERT INTO sticker_items VALUES (" + ",".join("?" for _ in columns) + ")",
                [row[column] for column in columns],
            )
            connection.execute(
                "INSERT INTO sticker_files VALUES (?,?,?,?,?)",
                (
                    digest,
                    path.relative_to(tmp_path).as_posix(),
                    "image/png",
                    len(data),
                    "synthetic",
                ),
            )
    service = StickerSendService(data_dir=tmp_path)
    query = {"intent": "unmatchedsynthetic", "emotion": "joy"}
    before = _snapshot(tmp_path)
    for args in ({"emotion": "joy"}, {"mode": "fallback", **query}, {}):
        for limit in (1, 5, 10):
            request = parse_sticker_search_request({**args, "limit": limit})
            result = service.search(request, "group:700000001")
            assert [item["sticker_id"] for item in result["items"]] == [
                f"id-{i:02}" for i in range(limit)
            ]
            assert service.search(request, "group:700000001") == result
    sender = _Client()
    _bind_context(monkeypatch, tmp_path)
    monkeypatch.setattr(tools, "_ACTIVE_SENDER", sender)
    result = json.loads(asyncio.run(tools._handle_sticker_send(query)))
    assert [item["sticker_id"] for item in result["alternatives"]] == [
        f"id-{i:02}" for i in range(5)
    ]
    assert sender.calls == [] and _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "tool_name,field,limit", [("sticker_search", "items", 10), ("sticker_send", "alternatives", 5)]
)
def test_serializer_rejects_oversized_and_duplicate_lists(tool_name, field, limit) -> None:
    item = {"sticker_id": "id", "emotion": "joy", "tags": [], "description": ""}
    base = (
        {"status": "ok", "match_mode": "browse"}
        if tool_name == "sticker_search"
        else {"status": "no_match"}
    )
    for items in ([item, item], [{**item, "sticker_id": f"id-{i}"} for i in range(limit + 1)]):
        assert json.loads(tools._sticker_result({**base, field: items}, tool_name)) == {
            "status": "malformed"
        }


def test_search_and_no_match_do_not_migrate_older_schema(tmp_path, monkeypatch) -> None:
    _create_library(tmp_path)
    with sqlite3.connect(tmp_path / "stickers.db") as connection:
        connection.execute("DROP TABLE sticker_send_usage")
        connection.execute("UPDATE sticker_schema_meta SET value='2'")
    before = _snapshot(tmp_path)
    service = StickerSendService(data_dir=tmp_path)

    def fail(*_args, **_kwargs):
        pytest.fail("只读搜索和无匹配不得迁移或读取媒体")

    monkeypatch.setattr(StickerStore, "_initialize_schema", fail)
    monkeypatch.setattr("stickers.sending.read_validated_image_file", fail)
    assert service.search(parse_sticker_search_request({}), "group:700000001")["status"] == "ok"
    from stickers.sending import parse_sticker_send_request

    result = asyncio.run(
        service.send(
            parse_sticker_send_request({"intent": "unmatchedsynthetic", "emotion": "joy"}),
            "group:700000001",
            _Client(),
        )
    )
    assert result["status"] == "no_match" and len(result["alternatives"]) == 1
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("failure,status", [("schema", "unsupported"), ("access", "storage_error")])
def test_search_storage_failures_are_fixed(tmp_path, monkeypatch, failure, status) -> None:
    _create_library(tmp_path)
    if failure == "schema":
        with sqlite3.connect(tmp_path / "stickers.db") as connection:
            connection.execute("UPDATE sticker_schema_meta SET value='99'")
    else:

        def fail(*_args, **_kwargs):
            raise OSError("synthetic private detail")

        monkeypatch.setattr(StickerSendService, "_open_existing_for_read", fail)
    assert StickerSendService(data_dir=tmp_path).search(
        parse_sticker_search_request({}), "group:700000001"
    ) == {"status": status}


def test_legacy_tied_candidates_send_after_readonly_selection(tmp_path) -> None:
    """旧 schema 尚无会话统计时仍能选择并迁移后 claim 一次。"""
    from stickers.sending import parse_sticker_send_request

    _create_two_item_library(tmp_path)
    with sqlite3.connect(tmp_path / "stickers.db") as connection:
        connection.execute("DROP TABLE sticker_send_usage")
        connection.execute("UPDATE sticker_schema_meta SET value='2'")
    sender = _Client()
    result = asyncio.run(
        StickerSendService(data_dir=tmp_path).send(
            parse_sticker_send_request({"emotion": "joy"}), "group:700000001", sender
        )
    )
    assert result == {"status": "sent", "message_id": "synthetic"}
    assert len(sender.calls) == 1
    with sqlite3.connect(tmp_path / "stickers.db") as connection:
        assert connection.execute("SELECT sum(use_count) FROM sticker_items").fetchone() == (1,)
        assert connection.execute("SELECT sum(use_count) FROM sticker_send_usage").fetchone() == (
            1,
        )
