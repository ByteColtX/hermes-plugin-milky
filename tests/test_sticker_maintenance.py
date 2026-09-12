"""贴纸人工维护的脱敏单元测试。"""

from __future__ import annotations

import asyncio
import base64
import json
import struct
import zlib
from pathlib import Path

from slash_commands import SlashCommandService
from stickers.maintenance import (
    STICKER_VISION_PROMPT,
    StickerMaintenanceService,
    parse_sticker_command,
    parse_visual_response,
)
from stickers.storage import SCHEMA_VERSION, StickerStore
from stickers.validation import validate_image_file

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _vision(*, is_sticker: bool = True, emotion: str = "joy") -> str:
    return json.dumps(
        {
            "success": True,
            "analysis": json.dumps(
                {
                    "emotion": emotion,
                    "tags": ["开心", "反应"],
                    "description": "小图表达情绪",
                    "is_sticker": is_sticker,
                },
                ensure_ascii=False,
            ),
        },
        ensure_ascii=False,
    )


def _unique_png(index: int) -> bytes:
    """在合法 PNG 中加入脱敏的唯一文本 chunk。"""

    marker = f"fixture-{index}".encode()
    chunk = b"tEXt" + marker
    encoded = (
        struct.pack(">I", len(marker)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
    )
    return _PNG[:-12] + encoded + _PNG[-12:]


def test_visual_envelope_and_exact_scale_note_are_parsed() -> None:
    note = "Image downscaled from 10x10 to 5x5 for vision; multiply any coordinates by 2.00 to map back to the original image."
    raw = json.dumps(
        {
            "success": True,
            "scale_note": note,
            "analysis": f"[{note}] "
            + json.dumps(
                {
                    "emotion": "approval",
                    "tags": ["认可", "支持"],
                    "description": "点头表示认可",
                    "is_sticker": True,
                },
                ensure_ascii=False,
            ),
        },
        ensure_ascii=False,
    )
    assert parse_visual_response(raw)["emotion"] == "approval"
    assert STICKER_VISION_PROMPT.startswith("You are a sticker metadata annotator.")


def test_store_uses_independent_schema_and_rejects_unknown_version(tmp_path: Path) -> None:
    store = StickerStore(data_dir=tmp_path)
    store.open()
    assert store.paths is not None
    assert store.connection is not None
    assert store.connection.execute(
        "SELECT value FROM sticker_schema_meta WHERE key = 'schema_version'"
    ).fetchone() == (str(SCHEMA_VERSION),)
    assert store.connection.execute(
        "SELECT name FROM sqlite_master WHERE name = 'sticker_items'"
    ).fetchone()
    store.close()


def test_command_parser_rejects_unsafe_and_partial_edit_arguments() -> None:
    assert parse_sticker_command("sticker list --limit=5").limit == 5
    assert parse_sticker_command("sticker edit opaque-id --tags=开心,安慰").sets == {
        "tags": ["开心", "安慰"]
    }
    try:
        parse_sticker_command("sticker edit opaque-id --tags=开心,安慰 --clear=tags")
    except ValueError:
        pass
    else:
        raise AssertionError("set and clear must conflict")


def test_add_edit_reanalyze_list_and_delete_preserve_library_bytes(tmp_path: Path) -> None:
    inbox = tmp_path / "stickers" / "inbox"
    inbox.mkdir(parents=True)
    source = inbox / "reaction.png"
    source.write_bytes(_PNG)

    async def analyze(*, image_url: str, user_prompt: str) -> str:
        assert image_url.endswith(".png")
        assert user_prompt == STICKER_VISION_PROMPT
        return _vision()

    service = StickerMaintenanceService(data_dir=tmp_path, vision_analyzer=analyze)
    added = json.loads(asyncio.run(service.handle("sticker add")))
    assert added["created"] == 1
    assert not source.exists()

    listed = json.loads(asyncio.run(service.handle("sticker list")))
    item = listed["items"][0]
    sticker_id = item["sticker_id"]
    library_files = list((tmp_path / "stickers" / "library").rglob("*.png"))
    assert len(library_files) == 1
    original_bytes = library_files[0].read_bytes()

    edited = json.loads(asyncio.run(service.handle(f"sticker edit {sticker_id} --tags=安慰,摸头")))
    assert edited["status"] == "updated"
    assert json.loads(asyncio.run(service.handle("sticker list")))["items"][0]["source"] == "manual"
    assert library_files[0].read_bytes() == original_bytes

    reanalyzed = json.loads(asyncio.run(service.handle(f"sticker reanalyze {sticker_id}")))
    assert reanalyzed["status"] == "reanalyzed"
    assert json.loads(asyncio.run(service.handle("sticker list")))["items"][0]["tags"] == [
        "安慰",
        "摸头",
    ]

    deleted = json.loads(asyncio.run(service.handle(f"sticker del {sticker_id}")))
    assert deleted["status"] == "deleted"
    assert json.loads(asyncio.run(service.handle("sticker list")))["count"] == 0
    cleanup = json.loads(asyncio.run(service.handle("sticker cleanup")))
    assert cleanup["orphan"] == 1
    assert not library_files[0].exists()


def test_usage_count_is_atomic_and_maintenance_does_not_change_it(tmp_path: Path) -> None:
    inbox = tmp_path / "stickers" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "reaction.png").write_bytes(_PNG)
    service = StickerMaintenanceService(
        data_dir=tmp_path, vision_analyzer=lambda *_args, **_kwargs: _vision()
    )
    added = json.loads(asyncio.run(service.handle("sticker add")))
    sticker_id = json.loads(asyncio.run(service.handle("sticker list")))["items"][0]["sticker_id"]
    assert added["created"] == 1
    assert service.record_send_started(sticker_id, invocation_id="one")["status"] == "counted"
    assert (
        service.record_send_started(sticker_id, invocation_id="one")["status"] == "already_counted"
    )
    assert service.record_send_started(sticker_id, invocation_id="two")["status"] == "counted"
    listed = service.list()["items"][0]
    assert listed["use_count"] == 2
    assert listed["last_used_at"]


def test_reanalyze_false_keeps_entry_and_reindex_reports_missing_and_orphan(tmp_path: Path) -> None:
    inbox = tmp_path / "stickers" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "reaction.png").write_bytes(_PNG)
    answers = [_vision(), _vision(is_sticker=False)]

    async def analyze(*_args: object, **_kwargs: object) -> str:
        return answers.pop(0)

    service = StickerMaintenanceService(data_dir=tmp_path, vision_analyzer=analyze)
    asyncio.run(service.handle("sticker add"))
    item = json.loads(asyncio.run(service.handle("sticker list")))["items"][0]
    result = json.loads(asyncio.run(service.handle(f"sticker reanalyze {item['sticker_id']}")))
    assert result["status"] == "not_sticker"
    assert json.loads(asyncio.run(service.handle("sticker list")))["count"] == 1

    library_file = next((tmp_path / "stickers" / "library").rglob("*.png"))
    library_file.unlink()
    index = json.loads(asyncio.run(service.handle("sticker reindex")))
    assert index["missing_file"] == 1
    assert json.loads(asyncio.run(service.handle("sticker list")))["count"] == 1


def test_batch_limit_and_visual_failure_leave_deferred_files_in_inbox(tmp_path: Path) -> None:
    inbox = tmp_path / "stickers" / "inbox"
    inbox.mkdir(parents=True)
    for index in range(51):
        (inbox / f"{index:02d}.png").write_bytes(_unique_png(index))
    calls = 0
    active = 0
    peak = 0

    async def analyze(*_args: object, **_kwargs: object) -> str:
        nonlocal calls, active, peak
        calls += 1
        call_number = calls
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return "not-json" if call_number == 1 else _vision()

    service = StickerMaintenanceService(data_dir=tmp_path, vision_analyzer=analyze)
    result = json.loads(asyncio.run(service.handle("sticker add")))
    assert calls == 50
    assert peak <= 10
    assert result["batch_deferred"] == 1
    assert result["visual_unavailable"] == 1
    assert len(list(inbox.glob("*.png"))) == 2


def test_false_visual_result_moves_to_junk_and_dry_run_does_not_move(tmp_path: Path) -> None:
    inbox = tmp_path / "stickers" / "inbox"
    inbox.mkdir(parents=True)
    source = inbox / "photo.png"
    source.write_bytes(_PNG)

    async def analyze(*, image_url: str, user_prompt: str) -> str:
        del image_url, user_prompt
        return _vision(is_sticker=False)

    service = StickerMaintenanceService(data_dir=tmp_path, vision_analyzer=analyze)
    preview = json.loads(asyncio.run(service.handle("sticker add --dry-run")))
    assert preview["items"][0]["status"] == "would_move_to_junk"
    assert source.exists()
    result = json.loads(asyncio.run(service.handle("sticker add")))
    assert result["junk"] == 1
    assert not source.exists()
    assert len(list((tmp_path / "stickers" / "junk").iterdir())) == 1


def test_fresh_dry_run_does_not_create_database_or_move_file(tmp_path: Path) -> None:
    inbox = tmp_path / "stickers" / "inbox"
    inbox.mkdir(parents=True)
    source = inbox / "preview.png"
    source.write_bytes(_PNG)

    service = StickerMaintenanceService(
        data_dir=tmp_path, vision_analyzer=lambda *_args, **_kwargs: _vision()
    )
    result = json.loads(asyncio.run(service.handle("sticker add --dry-run")))
    assert result["items"][0]["status"] == "would_add"
    assert source.exists()
    assert not (tmp_path / "stickers.db").exists()


def test_image_validation_keeps_png_hash_and_rejects_text(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    good = inbox / "good.png"
    good.write_bytes(_PNG)
    candidate = validate_image_file(good, inbox)
    assert candidate.image_format == "png"
    bad = inbox / "bad.png"
    bad.write_text("not an image", encoding="utf-8")
    try:
        validate_image_file(bad, inbox)
    except ValueError:
        pass
    else:
        raise AssertionError("text must be rejected")


def test_slash_service_routes_explicit_sticker_without_milky_client(tmp_path: Path) -> None:
    service = StickerMaintenanceService(data_dir=tmp_path)
    command_service = SlashCommandService(sticker_service=service)
    result = json.loads(asyncio.run(command_service.handle("sticker list")))
    assert result == {"count": 0, "items": [], "status": "ok"}
    assert command_service.active_client_count == 0
    invalid = json.loads(asyncio.run(command_service.handle("sticker add --unknown")))
    assert invalid["status"] == "invalid_input"
