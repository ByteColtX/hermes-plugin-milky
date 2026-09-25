"""显式 `/milky sticker` 维护命令的存储、视觉和回执逻辑。"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import re
import secrets
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .coordination import library_guard
from .errors import StickerError, StickerStorageError, StickerUnsupportedError
from .presentation import HELP, render, usage_for
from .storage import PLUGIN_NAME, StickerPaths, StickerStore
from .validation import ImageCandidate, validate_image_file, validate_library_name

MAX_BATCH = 50
MAX_CONCURRENCY = 10
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
EMOTIONS = frozenset(
    {
        "joy",
        "sadness",
        "anger",
        "surprise",
        "fear",
        "disgust",
        "love",
        "approval",
        "confusion",
        "neutral",
        "mixed",
        "unknown",
    }
)
EDIT_FIELDS = frozenset({"emotion", "tags", "description"})
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_CJK_RE = re.compile(r"[\u3400-\u9fff]")

STICKER_VISION_PROMPT = """You are a sticker metadata annotator.

Analyze the input sticker/meme image and extract metadata that best captures its expressive content.

Return only one valid JSON object. Do not output Markdown, explanations, comments, or any additional content.

Field requirements:

- `emotion`: Select exactly one primary emotion:
  `joy`, `sadness`, `anger`, `surprise`, `fear`, `disgust`, `love`, `approval`, `confusion`, `neutral`, `mixed`, `unknown`

  - Select the most prominent and clearly expressed emotion in the image.
  - If multiple emotions are equally prominent, select `mixed`.
  - If the emotion cannot be determined reliably, select `unknown`.

- `tags`: Return 2–5 unique Chinese emotion/context tags.

  - Tags should directly describe the emotion, reaction, action, or typical conversational context expressed by the image.
  - Prefer short, natural words or phrases commonly used in chat.
  - Examples: 安慰、阴阳怪气、无语、得意、卖萌、自信、哭泣、嘲讽、难绷、嫌弃、攻击、吐槽、疑惑...
  - Do not add information that cannot be confirmed from the image.

- `description`: Return a brief description in no more than 20 Chinese characters.

  - Summarize the main subject and what the image is expressing.
  - If the image contains text, summarize its meaning rather than copying long text verbatim.

- `is_sticker`: A boolean indicating whether the input image is a sticker/meme intended for use in chat.

  - Return `true` if the image is a sticker, meme, reaction image, or similar chat-oriented expressive image.
  - Return `false` if it is a regular photo, illustration, screenshot, informational image, or other non-sticker image.

Output format:
{
  "emotion": "joy",
  "tags": ["开心", "鼓励", "摸头"],
  "description": "猫咪举爪安慰对方",
  "is_sticker": true
}"""

USAGE = (
    "usage: /milky sticker add [--dry-run] | list [--limit <1..100>] | "
    "edit <sticker_id> [--emotion=<enum>] [--tags=<tag1>,<tag2>,...] "
    "[--description=<text>] [--clear=<field>[,<field>...]] | "
    "reanalyze <sticker_id> | del <sticker_id> | cleanup [--dry-run] | reindex"
)


@dataclass(frozen=True, slots=True)
class StickerCommand:
    """严格解析后的贴纸命令。"""

    operation: str
    dry_run: bool = False
    limit: int = DEFAULT_LIMIT
    sticker_id: str | None = None
    sets: dict[str, object] | None = None
    clears: frozenset[str] = frozenset()


class StickerCommandError(ValueError):
    """贴纸命令语法错误。"""


def _parse_limit(value: str) -> int:
    if not value.isascii() or not value.isdecimal():
        raise StickerCommandError("invalid limit")
    limit = int(value)
    if not 1 <= limit <= MAX_LIMIT:
        raise StickerCommandError("limit is out of range")
    return limit


def _parse_id(value: str) -> str:
    if not _ID_RE.fullmatch(value) or value in {".", ".."}:
        raise StickerCommandError("invalid sticker id")
    return value


def _parse_tags(value: str) -> list[str]:
    tags = value.split(",")
    if not 2 <= len(tags) <= 5 or any(not tag for tag in tags):
        raise StickerCommandError("invalid tags")
    if len(set(tags)) != len(tags) or any(len(tag) > 16 or not _CJK_RE.search(tag) for tag in tags):
        raise StickerCommandError("invalid tags")
    return tags


def _parse_edit_options(tokens: list[str]) -> tuple[dict[str, object], frozenset[str]]:
    sets: dict[str, object] = {}
    clears: set[str] = set()
    seen: set[str] = set()
    for token in tokens:
        if not token.startswith("--") or "=" not in token:
            raise StickerCommandError("invalid edit option")
        name, value = token[2:].split("=", 1)
        if name in seen:
            raise StickerCommandError("duplicate edit option")
        seen.add(name)
        if name == "emotion":
            if value not in EMOTIONS or not value:
                raise StickerCommandError("invalid emotion")
            sets[name] = value
        elif name == "tags":
            sets[name] = _parse_tags(value)
        elif name == "description":
            if not value or len(value) > 20 or not _CJK_RE.search(value):
                raise StickerCommandError("invalid description")
            sets[name] = value
        elif name == "clear":
            values = value.split(",")
            if not values or any(field not in EDIT_FIELDS for field in values):
                raise StickerCommandError("invalid clear field")
            if len(set(values)) != len(values):
                raise StickerCommandError("duplicate clear field")
            clears.update(values)
        else:
            raise StickerCommandError("unknown edit option")
    if not sets and not clears:
        raise StickerCommandError("edit requires a field")
    if set(sets).intersection(clears):
        raise StickerCommandError("field cannot be set and cleared")
    return sets, frozenset(clears)


def parse_sticker_command(raw_args: str) -> StickerCommand:
    """解析 `/milky` 后的贴纸参数，不读取路径或外部状态。"""

    if not isinstance(raw_args, str):
        raise StickerCommandError("arguments are not text")
    tokens = raw_args.strip().split()
    if not tokens or tokens[0].lower() != "sticker":
        raise StickerCommandError("unknown sticker command")
    if len(tokens) < 2:
        return StickerCommand("help")
    operation = tokens[1].lower()
    if operation == "remove":
        operation = "del"
    rest = tokens[2:]
    if operation == "help":
        if rest:
            raise StickerCommandError("invalid help arguments")
        return StickerCommand("help")
    if operation == "add":
        if rest not in ([], ["--dry-run"]):
            raise StickerCommandError("invalid add arguments")
        return StickerCommand(operation, dry_run=bool(rest))
    if operation == "list":
        if not rest:
            return StickerCommand(operation)
        if len(rest) == 1 and rest[0].startswith("--limit="):
            return StickerCommand(operation, limit=_parse_limit(rest[0][8:]))
        if len(rest) == 2 and rest[0] == "--limit":
            return StickerCommand(operation, limit=_parse_limit(rest[1]))
        raise StickerCommandError("invalid list arguments")
    if operation in {"reanalyze", "del"}:
        if len(rest) != 1:
            raise StickerCommandError("missing sticker id")
        return StickerCommand(operation, sticker_id=_parse_id(rest[0]))
    if operation == "cleanup":
        if rest not in ([], ["--dry-run"]):
            raise StickerCommandError("invalid cleanup arguments")
        return StickerCommand(operation, dry_run=bool(rest))
    if operation == "reindex":
        if rest:
            raise StickerCommandError("invalid reindex arguments")
        return StickerCommand(operation)
    if operation == "edit":
        if not rest:
            raise StickerCommandError("missing sticker id")
        sticker_id = _parse_id(rest[0])
        sets, clears = _parse_edit_options(rest[1:])
        return StickerCommand(operation, sticker_id=sticker_id, sets=sets, clears=clears)
    raise StickerCommandError("unknown sticker operation")


def _strip_scale_note(analysis: str, scale_note: object) -> str:
    """只移除 core 返回的精确缩放前缀。"""

    if isinstance(scale_note, str) and scale_note:
        prefix = f"[{scale_note}] "
        if analysis.startswith(prefix):
            return analysis[len(prefix) :]
    return analysis


def _validate_visual_object(value: object) -> dict[str, object]:
    """验证视觉模型内层 JSON 的固定 schema。"""

    expected = {"emotion", "tags", "description", "is_sticker"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("visual object schema is invalid")
    emotion = value["emotion"]
    tags = value["tags"]
    description = value["description"]
    is_sticker = value["is_sticker"]
    if not isinstance(emotion, str) or emotion not in EMOTIONS:
        raise ValueError("visual emotion is invalid")
    if (
        not isinstance(tags, list)
        or not 2 <= len(tags) <= 5
        or any(
            not isinstance(tag, str) or not tag or len(tag) > 16 or not _CJK_RE.search(tag)
            for tag in tags
        )
        or len(set(tags)) != len(tags)
    ):
        raise ValueError("visual tags are invalid")
    if (
        not isinstance(description, str)
        or not 0 < len(description) <= 20
        or not _CJK_RE.search(description)
    ):
        raise ValueError("visual description is invalid")
    if type(is_sticker) is not bool:
        raise ValueError("visual is_sticker is invalid")
    return {"emotion": emotion, "tags": tags, "description": description, "is_sticker": is_sticker}


def parse_visual_response(raw: object) -> dict[str, object]:
    """解析 vision helper 的外层 envelope 和内层 metadata。"""

    if not isinstance(raw, str):
        raise TypeError("visual response is not text")
    try:
        envelope = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("visual envelope is invalid") from error
    if not isinstance(envelope, dict) or envelope.get("success") is not True:
        raise ValueError("visual envelope failed")
    analysis = envelope.get("analysis")
    if not isinstance(analysis, str) or not analysis:
        raise ValueError("visual analysis is empty")
    analysis = _strip_scale_note(analysis, envelope.get("scale_note"))
    try:
        inner = json.loads(analysis)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("visual analysis is invalid") from error
    return _validate_visual_object(inner)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _json_tags(tags: object) -> str:
    return json.dumps(tags, ensure_ascii=False, separators=(",", ":"))


def _decode_tags(value: object) -> list[str]:
    try:
        result = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError:
        return []
    return list(result) if isinstance(result, list) else []


class StickerMaintenanceService:
    """以单条命令为生命周期边界的贴纸维护 service。"""

    def __init__(
        self,
        *,
        plugin_context: object | None = None,
        data_dir: Path | None = None,
        data_dir_factory: Callable[[], Path] | None = None,
        db_factory: Callable[[], sqlite3.Connection] | None = None,
        store_factory: Callable[[], StickerStore] | None = None,
        vision_analyzer: Callable[..., object] | None = None,
    ) -> None:
        """只保存依赖工厂，不访问 Hermes storage 或视觉能力。"""

        self._plugin_context = plugin_context
        self._data_dir = data_dir
        self._data_dir_factory = data_dir_factory
        self._db_factory = db_factory
        self._store_factory = store_factory
        self._vision_analyzer = vision_analyzer
        self._active_stores: set[StickerStore] = set()
        self._counted_invocations: set[str] = set()
        self._lock = threading.RLock()

    async def handle(self, raw_args: str) -> str:
        """处理一个已确认到达插件 handler 的贴纸命令。"""

        try:
            command = parse_sticker_command(raw_args)
        except StickerCommandError:
            return usage_for(raw_args)
        if command.operation == "help":
            return HELP
        try:
            result = await self._run(command)
        except StickerUnsupportedError:
            result = {"status": "unsupported"}
        except StickerStorageError:
            result = {"status": "storage_error"}
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - handler 不泄漏路径、参数或异常正文
            result = {"status": "storage_error"}
        return render(command.operation, result, dry_run=command.dry_run)

    async def add(self, *, dry_run: bool = False) -> dict[str, object]:
        """执行一次 add，供集成测试和宿主 adapter 使用。"""

        return await self._run(StickerCommand("add", dry_run=dry_run))

    def list(self, *, limit: int = DEFAULT_LIMIT) -> dict[str, object]:
        """读取有界的贴纸摘要。"""

        if not 1 <= limit <= MAX_LIMIT:
            return {"status": "invalid_input"}
        return self._run_sync(StickerCommand("list", limit=limit))

    def edit(
        self,
        sticker_id: str,
        *,
        sets: dict[str, object] | None = None,
        clears: frozenset[str] = frozenset(),
    ) -> dict[str, object]:
        """按字段更新一个贴纸条目。"""

        return self._run_sync(
            StickerCommand("edit", sticker_id=sticker_id, sets=sets or {}, clears=clears)
        )

    async def reanalyze(self, sticker_id: str) -> dict[str, object]:
        """重新生成一个条目的视觉基线。"""

        return await self._run(StickerCommand("reanalyze", sticker_id=sticker_id))

    def delete(self, sticker_id: str) -> dict[str, object]:
        """删除一个可见条目并保留待 cleanup 的库文件。"""

        return self._run_sync(StickerCommand("del", sticker_id=sticker_id))

    def cleanup(self, *, dry_run: bool = False) -> dict[str, object]:
        """诊断并清理 orphan 与临时库文件。"""

        return self._run_sync(StickerCommand("cleanup", dry_run=dry_run))

    def reindex(self) -> dict[str, object]:
        """只重建 library 技术索引。"""

        return self._run_sync(StickerCommand("reindex"))

    def _run_sync(self, command: StickerCommand) -> dict[str, object]:
        store = self._new_store()
        with self._lock:
            self._active_stores.add(store)
        try:
            read_only = command.dry_run and command.operation in {"add", "cleanup"}
            store.open(read_only=read_only, create_dirs=not read_only)
            if command.operation == "list":
                return self._list(store, command.limit)
            if command.operation == "edit":
                return self._edit(
                    store, command.sticker_id or "", command.sets or {}, command.clears
                )
            if command.operation == "del":
                return self._delete(store, command.sticker_id or "")
            if command.operation == "cleanup":
                return self._cleanup(store, command.dry_run)
            if command.operation == "reindex":
                return self._reindex(store)
            return {"status": "invalid_input"}
        finally:
            store.close()
            with self._lock:
                self._active_stores.discard(store)

    async def _run(self, command: StickerCommand) -> dict[str, object]:
        store = self._new_store()
        with self._lock:
            self._active_stores.add(store)
        try:
            read_only = command.dry_run and command.operation in {"add", "cleanup"}
            store.open(read_only=read_only, create_dirs=not read_only)
            if command.operation == "add":
                return await self._add(store, command.dry_run)
            if command.operation == "list":
                return self._list(store, command.limit)
            if command.operation == "edit":
                return self._edit(
                    store, command.sticker_id or "", command.sets or {}, command.clears
                )
            if command.operation == "reanalyze":
                return await self._reanalyze(store, command.sticker_id or "")
            if command.operation == "del":
                return self._delete(store, command.sticker_id or "")
            if command.operation == "cleanup":
                return self._cleanup(store, command.dry_run)
            if command.operation == "reindex":
                return self._reindex(store)
            return {"status": "invalid_input", "usage": USAGE}
        finally:
            store.close()
            with self._lock:
                self._active_stores.discard(store)

    def close(self) -> None:
        """关闭当前 service 仍持有的命令 store。"""

        with self._lock:
            stores = tuple(self._active_stores)
        for store in stores:
            store.close()

    def _new_store(self) -> StickerStore:
        if self._store_factory is not None:
            return self._store_factory()
        data_factory = self._data_dir_factory
        db_factory = self._db_factory
        if self._plugin_context is not None:
            context_data = getattr(self._plugin_context, "plugin_data_dir", None)
            context_db = getattr(self._plugin_context, "plugin_db", None)
            if data_factory is None and callable(context_data):
                data_factory = lambda: _call_storage_factory(context_data, PLUGIN_NAME)
            if db_factory is None and callable(context_db):
                db_factory = lambda: _call_storage_factory(
                    context_db, PLUGIN_NAME, filename="stickers.db"
                )
        return StickerStore(
            data_dir=self._data_dir,
            data_dir_factory=data_factory,
            db_factory=db_factory,
        )

    @staticmethod
    def _connection(store: StickerStore) -> sqlite3.Connection:
        if store.connection is None:
            raise StickerStorageError("store is closed")
        return store.connection

    @staticmethod
    def _paths(store: StickerStore) -> StickerPaths:
        if store.paths is None:
            raise StickerStorageError("paths are unavailable")
        return store.paths

    async def _add(self, store: StickerStore, dry_run: bool) -> dict[str, object]:
        paths = self._paths(store)
        conn = store.connection
        result: dict[str, object] = {
            "status": "ok",
            "created": 0,
            "duplicate": 0,
            "junk": 0,
            "rejected": 0,
            "visual_unavailable": 0,
            "storage_error": 0,
            "batch_deferred": 0,
            "items": [],
        }
        candidates: list[ImageCandidate] = []
        invalid_entries = 0
        for path in self._scan_inbox(paths.inbox):
            try:
                candidate = validate_image_file(path, paths.inbox)
            except (OSError, ValueError):
                invalid_entries += 1
                continue
            existing = (
                conn.execute(
                    "SELECT relative_path FROM sticker_files WHERE sha256 = ?",
                    (candidate.file_sha256,),
                ).fetchone()
                if conn is not None
                else None
            )
            item_existing = (
                conn.execute(
                    "SELECT sticker_id FROM sticker_items WHERE file_sha256 = ?",
                    (candidate.file_sha256,),
                ).fetchone()
                if conn is not None
                else None
            )
            if existing is not None or item_existing is not None:
                existing_path = self._existing_library_path(
                    paths, existing[0] if existing else None, candidate
                )
                if (
                    existing_path is not None
                    and existing_path.is_file()
                    and not existing_path.is_symlink()
                ):
                    result["duplicate"] = int(result["duplicate"]) + 1
                    if not dry_run:
                        self._unlink_inbox(candidate.path, paths.inbox)
                    continue
                result["status"] = "missing_file"
                continue
            candidates.append(candidate)
        result["rejected"] = invalid_entries

        grouped: dict[str, list[ImageCandidate]] = {}
        for candidate in candidates:
            grouped.setdefault(candidate.file_sha256, []).append(candidate)
        unique_candidates: list[ImageCandidate] = []
        for same_hash in grouped.values():
            unique_candidates.append(same_hash[0])
            if len(same_hash) > 1:
                result["duplicate"] = int(result["duplicate"]) + len(same_hash) - 1

        selected = unique_candidates[:MAX_BATCH]
        deferred = unique_candidates[MAX_BATCH:]
        result["batch_deferred"] = len(deferred)
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

        async def process(candidate: ImageCandidate) -> dict[str, object]:
            async with semaphore:
                try:
                    raw = await self._call_vision(candidate.path)
                    metadata = parse_visual_response(raw)
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001 - only fixed category reaches user
                    return {"status": "visual_unavailable"}
            if dry_run:
                status = "would_add" if metadata["is_sticker"] is True else "would_move_to_junk"
                return {"status": status, **self._public_visual(metadata)}
            if metadata["is_sticker"] is True:
                return self._commit_sticker(
                    store, candidate, metadata, grouped[candidate.file_sha256][1:]
                )
            return self._move_to_junk(paths, candidate, grouped[candidate.file_sha256][1:])

        outcomes = await asyncio.gather(*(process(candidate) for candidate in selected))
        for candidate, outcome in zip(selected, outcomes, strict=True):
            status = outcome.get("status")
            if status == "created":
                result["created"] = int(result["created"]) + 1
            elif status == "duplicate":
                result["duplicate"] = int(result["duplicate"]) + 1
            elif status == "junk":
                result["junk"] = int(result["junk"]) + int(outcome.get("count", 1))
            elif status == "visual_unavailable":
                result["visual_unavailable"] = int(result["visual_unavailable"]) + 1
            elif status == "storage_error":
                result["storage_error"] = int(result["storage_error"]) + 1
                result["status"] = "storage_error"
            if dry_run or status in {"created", "junk", "visual_unavailable"}:
                cast_items = result["items"]
                if isinstance(cast_items, list):
                    cast_items.append({"file_sha256": candidate.file_sha256[:12], **outcome})
        return result

    @staticmethod
    def _scan_inbox(inbox: Path) -> list[Path]:
        """稳定扫描 inbox，目录本身不作为图片候选。"""

        paths: list[Path] = []
        if not inbox.exists() or inbox.is_symlink():
            return paths
        for path in sorted(inbox.rglob("*"), key=lambda item: item.as_posix()):
            if path.is_dir() and not path.is_symlink():
                continue
            paths.append(path)
        return paths

    @staticmethod
    def _existing_library_path(
        paths: StickerPaths, relative_path: object, candidate: ImageCandidate
    ) -> Path | None:
        if isinstance(relative_path, str):
            path = (paths.root / relative_path).resolve(strict=False)
            if paths.contains(path) and path.is_file():
                return path
        path = paths.library_path(candidate.file_sha256, candidate.suffix)
        return path if paths.contains(path) else None

    @staticmethod
    def _unlink_inbox(path: Path, inbox: Path) -> None:
        if path.is_symlink() or not path.is_file():
            return
        try:
            path.resolve(strict=False).relative_to(inbox.resolve())
            path.unlink()
        except (OSError, ValueError):
            raise StickerStorageError("inbox cleanup failed") from None

    async def _call_vision(self, path: Path) -> object:
        analyzer = self._vision_analyzer
        if analyzer is None:
            try:
                from tools.vision_tools import vision_analyze_tool
            except ImportError as error:
                raise StickerError("visual_unavailable") from error
            analyzer = vision_analyze_tool
        try:
            signature = inspect.signature(analyzer)
        except (TypeError, ValueError):
            signature = None
        if signature is not None and not {
            "image_url",
            "user_prompt",
        }.issubset(signature.parameters):
            result = analyzer(str(path), STICKER_VISION_PROMPT)
        else:
            result = analyzer(image_url=str(path), user_prompt=STICKER_VISION_PROMPT)
        if inspect.isawaitable(result):
            return await result
        return result

    @staticmethod
    def _public_visual(metadata: dict[str, object]) -> dict[str, object]:
        return {
            "emotion": metadata["emotion"],
            "tags": metadata["tags"],
            "description": metadata["description"],
            "is_sticker": metadata["is_sticker"],
        }

    def _commit_sticker(
        self,
        store: StickerStore,
        candidate: ImageCandidate,
        metadata: dict[str, object],
        duplicates: list[ImageCandidate],
        *,
        input_root: Path | None = None,
    ) -> dict[str, object]:
        paths = self._paths(store)
        conn = store.connection
        with self._lock, library_guard(paths.root):
            existing = conn.execute(
                "SELECT sticker_id FROM sticker_items WHERE file_sha256 = ?",
                (candidate.file_sha256,),
            ).fetchone()
            dest = paths.library_path(candidate.file_sha256, candidate.suffix)
            if existing is not None and dest.is_file():
                self._unlink_inbox(candidate.path, (input_root or paths.inbox))
                return {"status": "duplicate"}
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists() or dest.is_symlink():
                    raise StickerStorageError("library destination exists")
                os.replace(candidate.path, dest)
                now = _utc_now()
                sticker_id = secrets.token_urlsafe(18)
                tags_json = _json_tags(metadata["tags"])
                conn.execute("BEGIN")
                conn.execute(
                    "INSERT INTO sticker_files(sha256, relative_path, mime_type, size_bytes, verified_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        candidate.file_sha256,
                        paths.relative(dest),
                        candidate.mime_type,
                        candidate.size_bytes,
                        now,
                    ),
                )
                conn.execute(
                    "INSERT INTO sticker_items(sticker_id, file_sha256, format, mime_type, size_bytes, "
                    "detected_emotion, detected_tags_json, detected_description, emotion, tags_json, "
                    "description, emotion_source, tags_source, description_source, created_at, updated_at, "
                    "detected_at, use_count, last_used_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)",
                    (
                        sticker_id,
                        candidate.file_sha256,
                        candidate.image_format,
                        candidate.mime_type,
                        candidate.size_bytes,
                        metadata["emotion"],
                        tags_json,
                        metadata["description"],
                        metadata["emotion"],
                        tags_json,
                        metadata["description"],
                        "vision",
                        "vision",
                        "vision",
                        now,
                        now,
                        now,
                    ),
                )
                conn.commit()
            except StickerStorageError:
                conn.rollback()
                raise
            except Exception as error:
                conn.rollback()
                raise StickerStorageError("sticker commit failed") from error
        for duplicate in duplicates:
            try:
                self._unlink_inbox(duplicate.path, (input_root or paths.inbox))
            except StickerStorageError:
                return {"status": "storage_error"}
        return {"status": "created", "sticker_id": sticker_id}

    @staticmethod
    def _move_to_junk(
        paths: StickerPaths, candidate: ImageCandidate, duplicates: list[ImageCandidate]
    ) -> dict[str, object]:
        moved = 0
        for source in [candidate, *duplicates]:
            try:
                target = paths.junk / source.path.name
                if target.exists() or target.is_symlink():
                    target = (
                        paths.junk
                        / f"{source.path.stem}-{source.file_sha256[:12]}{source.path.suffix.lower()}"
                    )
                if not paths.contains(target) or target.is_dir():
                    raise OSError
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source.path, target)
                moved += 1
            except OSError:
                return {"status": "storage_error", "count": moved}
        return {"status": "junk", "count": moved}

    def _list(self, store: StickerStore, limit: int) -> dict[str, object]:
        conn = self._connection(store)
        rows = conn.execute(
            "SELECT sticker_id, file_sha256, format, mime_type, size_bytes, emotion, tags_json, "
            "description, emotion_source, tags_source, description_source, created_at, updated_at, "
            "detected_at, use_count, last_used_at FROM sticker_items "
            "ORDER BY created_at ASC, sticker_id ASC LIMIT ?",
            (limit,),
        ).fetchall()
        items = [self._row_to_public(row) for row in rows]
        return {"status": "ok", "count": len(items), "items": items}

    @staticmethod
    def _row_to_public(row: tuple[object, ...]) -> dict[str, object]:
        (
            sticker_id,
            file_sha256,
            image_format,
            mime_type,
            size_bytes,
            emotion,
            tags_json,
            description,
            emotion_source,
            tags_source,
            description_source,
            created_at,
            updated_at,
            detected_at,
            use_count,
            last_used_at,
        ) = row
        field_sources = {
            "emotion": emotion_source,
            "tags": tags_source,
            "description": description_source,
        }
        return {
            "sticker_id": sticker_id,
            "file_sha256": str(file_sha256)[:12],
            "format": image_format,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "emotion": emotion,
            "tags": _decode_tags(tags_json),
            "description": description,
            "source": "manual" if "manual" in field_sources.values() else "vision",
            "field_sources": field_sources,
            "created_at": created_at,
            "updated_at": updated_at,
            "detected_at": detected_at,
            "use_count": use_count,
            "last_used_at": last_used_at,
        }

    @staticmethod
    def item_version(store: StickerStore, sticker_id: str) -> str | None:
        """以持久化业务字段生成版本，发送统计不改变编辑版本。"""
        conn = StickerMaintenanceService._connection(store)
        row = conn.execute(
            "SELECT file_sha256, detected_emotion, detected_tags_json, detected_description, "
            "emotion, tags_json, description, emotion_source, tags_source, description_source, "
            "updated_at, detected_at FROM sticker_items WHERE sticker_id = ?",
            (sticker_id,),
        ).fetchone()
        if row is None:
            return None
        return hashlib.sha256(json.dumps(row, ensure_ascii=False).encode()).hexdigest()

    def _edit(
        self,
        store: StickerStore,
        sticker_id: str,
        sets: dict[str, object],
        clears: frozenset[str],
    ) -> dict[str, object]:
        conn = self._connection(store)
        with self._lock, library_guard(self._paths(store).root):
            row = conn.execute(
                "SELECT detected_emotion, detected_tags_json, detected_description, emotion_source, "
                "tags_source, description_source, emotion, tags_json, description "
                "FROM sticker_items WHERE sticker_id = ?",
                (sticker_id,),
            ).fetchone()
            if row is None:
                return {"status": "sticker_not_found"}
            values: dict[str, object] = {
                "emotion": sets.get("emotion", row[6]),
                "tags_json": _json_tags(sets["tags"]) if "tags" in sets else row[7],
                "description": sets.get("description", row[8]),
                "emotion_source": "manual" if "emotion" in sets else row[3],
                "tags_source": "manual" if "tags" in sets else row[4],
                "description_source": "manual" if "description" in sets else row[5],
            }
            for field in clears:
                if field == "emotion":
                    values["emotion"] = row[0]
                    values["emotion_source"] = "vision"
                elif field == "tags":
                    values["tags_json"] = row[1]
                    values["tags_source"] = "vision"
                else:
                    values["description"] = row[2]
                    values["description_source"] = "vision"
            try:
                conn.execute("BEGIN")
                conn.execute(
                    "UPDATE sticker_items SET emotion = ?, tags_json = ?, description = ?, "
                    "emotion_source = ?, tags_source = ?, description_source = ?, updated_at = ? "
                    "WHERE sticker_id = ?",
                    (
                        values["emotion"],
                        values["tags_json"],
                        values["description"],
                        values["emotion_source"],
                        values["tags_source"],
                        values["description_source"],
                        _utc_now(),
                        sticker_id,
                    ),
                )
                conn.commit()
            except Exception as error:
                conn.rollback()
                raise StickerStorageError("edit failed") from error
        return {"status": "updated", "sticker_id": sticker_id}

    async def _reanalyze(
        self, store: StickerStore, sticker_id: str, *, guard=lambda: None, expected_version=None
    ) -> dict[str, object]:
        conn = self._connection(store)
        paths = self._paths(store)
        with library_guard(paths.root):
            original_version = self.item_version(store, sticker_id)
            if expected_version is not None and original_version != expected_version:
                return {"status": "conflict", "sticker_id": sticker_id}
            row = conn.execute(
                "SELECT file_sha256, format, detected_emotion, detected_tags_json, detected_description, "
                "emotion, tags_json, description, emotion_source, tags_source, description_source "
                "FROM sticker_items WHERE sticker_id = ?",
                (sticker_id,),
            ).fetchone()
        if row is None:
            return {"status": "sticker_not_found"}
        file_sha256, image_format = row[0], row[1]
        suffix = {"png": ".png", "jpeg": ".jpg", "gif": ".gif", "webp": ".webp"}.get(image_format)
        if not isinstance(file_sha256, str) or suffix is None:
            return {"status": "missing_file"}
        image_path = paths.library_path(file_sha256, suffix)
        if not image_path.is_file() or image_path.is_symlink() or not paths.contains(image_path):
            return {"status": "missing_file"}
        try:
            verified = validate_image_file(image_path, paths.library)
        except (OSError, ValueError):
            return {"status": "visual_unavailable"}
        if verified.file_sha256 != file_sha256 or verified.image_format != image_format:
            return {"status": "visual_unavailable"}
        try:
            metadata = parse_visual_response(await self._call_vision(image_path))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            return {"status": "visual_unavailable"}
        if metadata["is_sticker"] is not True:
            return {"status": "not_sticker"}
        with self._lock, library_guard(paths.root):
            guard()
            if self.item_version(store, sticker_id) != original_version:
                return {"status": "conflict", "sticker_id": sticker_id}
            try:
                now = _utc_now()
                detected_tags = _json_tags(metadata["tags"])
                emotion = metadata["emotion"] if row[8] == "vision" else row[5]
                tags_json = detected_tags if row[9] == "vision" else row[6]
                description = metadata["description"] if row[10] == "vision" else row[7]
                conn.execute("BEGIN")
                conn.execute(
                    "UPDATE sticker_items SET detected_emotion = ?, detected_tags_json = ?, "
                    "detected_description = ?, emotion = ?, tags_json = ?, description = ?, "
                    "detected_at = ?, updated_at = ? WHERE sticker_id = ?",
                    (
                        metadata["emotion"],
                        detected_tags,
                        metadata["description"],
                        emotion,
                        tags_json,
                        description,
                        now,
                        now,
                        sticker_id,
                    ),
                )
                conn.commit()
            except Exception as error:
                conn.rollback()
                raise StickerStorageError("reanalyze failed") from error
        return {"status": "reanalyzed", "sticker_id": sticker_id}

    def _delete(self, store: StickerStore, sticker_id: str) -> dict[str, object]:
        conn = self._connection(store)
        with self._lock, library_guard(self._paths(store).root):
            row = conn.execute(
                "SELECT file_sha256 FROM sticker_items WHERE sticker_id = ?", (sticker_id,)
            ).fetchone()
            if row is None:
                return {"status": "sticker_not_found"}
            references = conn.execute(
                "SELECT COUNT(*) FROM sticker_items WHERE file_sha256 = ?", (row[0],)
            ).fetchone()
            if not references or int(references[0]) != 1:
                return {"status": "storage_error"}
            try:
                conn.execute("BEGIN")
                conn.execute("DELETE FROM sticker_items WHERE sticker_id = ?", (sticker_id,))
                conn.commit()
            except Exception as error:
                conn.rollback()
                raise StickerStorageError("delete failed") from error
        return {"status": "deleted", "sticker_id": sticker_id}

    def _cleanup(self, store: StickerStore, dry_run: bool) -> dict[str, object]:
        with library_guard(self._paths(store).root):
            paths = self._paths(store)
            conn = self._connection(store)
            orphan = 0
            missing = 0
            temporary = 0
            skipped = 0
            item_rows = (
                conn.execute(
                    "SELECT i.file_sha256, f.relative_path FROM sticker_items AS i "
                    "LEFT JOIN sticker_files AS f ON f.sha256 = i.file_sha256"
                )
                if conn is not None
                else ()
            )
            for row in item_rows:
                path = self._safe_relative_path(paths, row[1])
                if path is None or not path.is_file():
                    missing += 1
            valid_refs = (
                {
                    row[0]
                    for row in conn.execute("SELECT file_sha256 FROM sticker_items")
                    if isinstance(row[0], str)
                }
                if conn is not None
                else set()
            )
            for path in sorted(paths.library.rglob("*"), key=lambda item: item.as_posix()):
                if path.is_dir() or path.is_symlink():
                    continue
                if path.name.endswith((".tmp", ".part", ".staging")):
                    temporary += 1
                    if not dry_run:
                        self._safe_unlink(path, paths.library)
                    continue
                parsed = validate_library_name(path, paths.library)
                if parsed is None:
                    skipped += 1
                    continue
                file_sha256, _image_format = parsed
                if file_sha256 not in valid_refs:
                    orphan += 1
                    if not dry_run:
                        self._safe_unlink(path, paths.library)
            return {
                "status": "ok",
                "orphan": orphan,
                "missing_file": missing,
                "temporary": temporary,
                "reindex_skipped": skipped,
                "dry_run": dry_run,
            }

    def _reindex(self, store: StickerStore) -> dict[str, object]:
        with self._lock, library_guard(self._paths(store).root):
            return self._reindex_locked(store)

    def _reindex_locked(self, store: StickerStore) -> dict[str, object]:
        """在共享保护内扫描和替换索引，避免覆盖并发提交。"""
        paths = self._paths(store)
        conn = self._connection(store)
        records: list[tuple[str, str, str, int, str]] = []
        skipped = 0
        for path in sorted(paths.library.rglob("*"), key=lambda item: item.as_posix()):
            if path.is_dir() or path.is_symlink():
                continue
            parsed = validate_library_name(path, paths.library)
            if parsed is None:
                skipped += 1
                continue
            expected_hash, expected_format = parsed
            try:
                candidate = validate_image_file(path, paths.library)
            except (OSError, ValueError):
                skipped += 1
                continue
            if candidate.file_sha256 != expected_hash or candidate.image_format != expected_format:
                skipped += 1
                continue
            records.append(
                (
                    candidate.file_sha256,
                    paths.relative(path),
                    candidate.mime_type,
                    candidate.size_bytes,
                    _utc_now(),
                )
            )
        with self._lock, library_guard(paths.root):
            try:
                conn.execute("BEGIN")
                conn.execute("DELETE FROM sticker_files")
                conn.executemany(
                    "INSERT INTO sticker_files(sha256, relative_path, mime_type, size_bytes, verified_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    records,
                )
                conn.commit()
            except Exception as error:
                conn.rollback()
                raise StickerStorageError("reindex failed") from error
        item_hashes = {
            row[0]
            for row in conn.execute("SELECT file_sha256 FROM sticker_items")
            if isinstance(row[0], str)
        }
        orphan = sum(1 for record in records if record[0] not in item_hashes)
        missing = sum(
            1 for file_sha256 in item_hashes if file_sha256 not in {r[0] for r in records}
        )
        return {
            "status": "ok",
            "indexed": len(records),
            "orphan": orphan,
            "missing_file": missing,
            "reindex_skipped": skipped,
        }

    def record_send_started(
        self, sticker_id: str, *, invocation_id: str | None = None
    ) -> dict[str, object]:
        """为后续 sticker_send 提供“已发起调用后计数一次”的原子接口。"""

        if not _ID_RE.fullmatch(sticker_id):
            return {"status": "invalid_input"}
        if invocation_id is not None:
            if not _ID_RE.fullmatch(invocation_id):
                return {"status": "invalid_input"}
            with self._lock:
                if invocation_id in self._counted_invocations:
                    return {"status": "already_counted", "sticker_id": sticker_id}
                self._counted_invocations.add(invocation_id)
        store = self._new_store()
        with self._lock:
            self._active_stores.add(store)
        try:
            store.open()
            conn = self._connection(store)
            now = _utc_now()
            cursor = conn.execute(
                "UPDATE sticker_items SET use_count = use_count + 1, last_used_at = ? "
                "WHERE sticker_id = ?",
                (now, sticker_id),
            )
            if cursor.rowcount != 1:
                conn.rollback()
                if invocation_id is not None:
                    with self._lock:
                        self._counted_invocations.discard(invocation_id)
                return {"status": "sticker_not_found"}
            conn.commit()
            return {"status": "counted", "sticker_id": sticker_id}
        except Exception as error:
            if invocation_id is not None:
                with self._lock:
                    self._counted_invocations.discard(invocation_id)
            try:
                self._connection(store).rollback()
            except Exception as rollback_error:
                raise StickerStorageError("usage update failed") from rollback_error
            raise StickerStorageError("usage update failed") from error
        finally:
            store.close()
            with self._lock:
                self._active_stores.discard(store)

    def increment_use_count(
        self, sticker_id: str, *, invocation_id: str | None = None
    ) -> dict[str, object]:
        """提供与发送调用绑定的统计递增别名。"""

        return self.record_send_started(sticker_id, invocation_id=invocation_id)

    @staticmethod
    def _safe_relative_path(paths: StickerPaths, relative_path: object) -> Path | None:
        if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
            return None
        path = (paths.root / relative_path).resolve(strict=False)
        return path if paths.contains(path) else None

    @staticmethod
    def _safe_unlink(path: Path, root: Path) -> None:
        try:
            path.resolve(strict=False).relative_to(root.resolve())
            if path.is_file() and not path.is_symlink():
                path.unlink()
        except (OSError, ValueError) as error:
            raise StickerStorageError("file cleanup failed") from error

    @staticmethod
    def _format_result(result: dict[str, object]) -> str:
        """将结果限制为固定分类、计数和受限元数据。"""

        safe: dict[str, object] = {}
        for key, value in result.items():
            if key in {"path", "url", "error", "exception", "raw", "bytes"}:
                continue
            safe[key] = value
        return json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _call_storage_factory(factory: Callable[..., object], name: str, **kwargs: object) -> object:
    """兼容宿主把 storage helper 暴露为带 name 或无参方法的 fake。"""

    try:
        return factory(name, **kwargs)
    except TypeError:
        return factory(**kwargs)


__all__ = [
    "DEFAULT_LIMIT",
    "EMOTIONS",
    "MAX_BATCH",
    "MAX_CONCURRENCY",
    "STICKER_VISION_PROMPT",
    "StickerCommand",
    "StickerCommandError",
    "StickerMaintenanceService",
    "parse_sticker_command",
    "parse_visual_response",
]
