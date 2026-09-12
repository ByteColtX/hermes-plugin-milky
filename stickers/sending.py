"""QQ 贴纸发送 Tool 的本地检索、选择和统计边界。"""

from __future__ import annotations

import base64
import json
import random
import sqlite3
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jieba

from session.identity import CanonicalError, normalize_chat_key

from .errors import StickerStorageError, StickerUnsupportedError
from .storage import PLUGIN_NAME, StickerPaths, StickerStore
from .validation import read_validated_image_file, validate_library_name

_MIN_QQ_ID = 10001
_MAX_QQ_ID = 4294967295
_ALLOWED_EMOTIONS = frozenset(
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


class StickerSendStorageFailure(RuntimeError):
    """表示发送前的贴纸库或图片边界不可用。"""

    def __init__(self, status: str = "storage_error") -> None:
        super().__init__(status)
        self.status = status


@dataclass(frozen=True, slots=True)
class StickerQuery:
    """经过严格校验的贴纸查询。"""

    intent: str | None = None
    emotion: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _StickerCandidate:
    """当前生效元数据和受控文件索引的最小投影。"""

    sticker_id: str
    file_sha256: str
    image_format: str
    mime_type: str
    size_bytes: int
    emotion: str
    tags: tuple[str, ...]
    description: str
    relative_path: str


@dataclass(frozen=True, slots=True)
class _Match:
    """不暴露给 Tool 的固定词法比较结果。"""

    candidate: _StickerCandidate
    layer: str
    intent_token_hits: int
    tag_hits: int


def normalize_sticker_text(value: str) -> str:
    """使用统一的 Unicode、大小写、空白和标点边界归一化文本。"""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    characters = [
        " " if unicodedata.category(character).startswith(("P", "S", "Z")) else character
        for character in normalized
    ]
    return " ".join("".join(characters).split())


def parse_sticker_query(args: object) -> StickerQuery:
    """校验 Tool 查询参数，不读取文件、数据库或网络。"""

    if not isinstance(args, Mapping):
        raise TypeError("query is not an object")
    allowed = {"intent", "emotion", "tags"}
    if set(args) - allowed:
        raise ValueError("query contains unknown fields")

    intent: str | None = None
    if "intent" in args:
        value = args["intent"]
        if not isinstance(value, str) or not value.strip() or len(value) > 64:
            raise ValueError("intent is invalid")
        intent = value.strip()

    emotion: str | None = None
    if "emotion" in args:
        value = args["emotion"]
        if not isinstance(value, str) or value not in _ALLOWED_EMOTIONS:
            raise ValueError("emotion is invalid")
        emotion = value

    tags: tuple[str, ...] = ()
    if "tags" in args:
        value = args["tags"]
        if not isinstance(value, list) or not 1 <= len(value) <= 5:
            raise ValueError("tags are invalid")
        normalized_tags: list[str] = []
        for tag in value:
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError("tags are invalid")
            normalized = normalize_sticker_text(tag)
            if not normalized or len(normalized) > 16 or normalized in normalized_tags:
                raise ValueError("tags are invalid")
            normalized_tags.append(normalized)
        tags = tuple(normalized_tags)

    if intent is None and emotion is None and not tags:
        raise ValueError("query is empty")
    return StickerQuery(intent=intent, emotion=emotion, tags=tags)


def tokenize_sticker_text(value: str, tokenizer: Any | None = None) -> tuple[str, ...]:
    """使用给定或插件运行时的 jieba 生成稳定、非空 token。"""

    module = tokenizer or jieba
    tokens = module.lcut(value, cut_all=False)
    normalized_tokens: list[str] = []
    for token in tokens:
        if not isinstance(token, str):
            continue
        normalized = normalize_sticker_text(token)
        if normalized:
            normalized_tokens.append(normalized)
    return tuple(normalized_tokens)


def _decode_tags(value: object) -> tuple[str, ...]:
    """解码当前生效的 tags；非法库字段不作为匹配输入。"""

    if not isinstance(value, str):
        return ()
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return ()
    if not isinstance(decoded, list):
        return ()
    result: list[str] = []
    for tag in decoded:
        if isinstance(tag, str):
            normalized = normalize_sticker_text(tag)
            if normalized:
                result.append(normalized)
    return tuple(result)


class StickerSendService:
    """在一次 Tool 调用内完成贴纸读取、claim 和单次发送。"""

    def __init__(
        self,
        *,
        plugin_context: object | None = None,
        data_dir: Path | None = None,
        data_dir_factory: Callable[[], Path] | None = None,
    ) -> None:
        """只保存生命周期配置，不在构造阶段访问 storage。"""

        self._plugin_context = plugin_context
        self._data_dir = data_dir
        self._data_dir_factory = data_dir_factory

    def is_available(self) -> bool:
        """只读探测当前是否存在可发送条目。"""

        store = self._new_store()
        try:
            store.open(read_only=True, create_dirs=False)
            if store.connection is None or store.paths is None:
                return False
            candidates = self._read_candidates(store.connection, store.paths, require_file=True)
            return bool(candidates)
        except (StickerStorageError, StickerUnsupportedError, OSError, sqlite3.Error):
            return False
        finally:
            store.close()

    async def send(self, query: StickerQuery, chat_key: str, sender: object) -> dict[str, object]:
        """选择一张受控贴纸、claim 统计并执行一次 Milky send Action。"""

        store = self._new_store()
        try:
            if not self._open_existing_for_write(store):
                return {"status": "unsupported"}
            if store.connection is None or store.paths is None:
                return {"status": "unsupported"}
            candidates = self._read_candidates(store.connection, store.paths, require_file=False)
            matches = self._match_candidates(candidates, query, jieba)
            selected = self._select_candidate(store.connection, matches, chat_key)
            if selected is None:
                return {"status": "no_match"}

            send_sticker = getattr(sender, "send_sticker", None)
            if not callable(send_sticker):
                return {"status": "unsupported"}
            uri = self._materialize_selected(store.paths, selected)
            self._claim_use(store.connection, store.paths, selected, chat_key)
            result = await send_sticker(chat_key, uri)
            if bool(getattr(result, "success", False)):
                message_id = getattr(result, "message_id", None)
                if not isinstance(message_id, str) or not message_id:
                    return {"status": "malformed"}
                return {"status": "sent", "message_id": message_id}
            classification = getattr(result, "error_kind", None)
            if classification == "timeout":
                classification = "transport_unknown"
            if classification in {
                "rejected",
                "http_error",
                "malformed",
                "transport_unknown",
                "unsupported",
            }:
                return {"status": classification}
            return {"status": "malformed"}
        except StickerSendStorageFailure as error:
            return {"status": error.status}
        except (StickerUnsupportedError, StickerStorageError, sqlite3.Error):
            return {"status": "storage_error"}
        except OSError:
            return {"status": "storage_error"}
        finally:
            store.close()

    def _new_store(self) -> StickerStore:
        data_factory = self._data_dir_factory
        db_factory = None
        if data_factory is None and self._plugin_context is not None:
            context_data = getattr(self._plugin_context, "plugin_data_dir", None)
            if callable(context_data):
                data_factory = lambda: _call_storage_factory(context_data, PLUGIN_NAME)
            context_db = getattr(self._plugin_context, "plugin_db", None)
            if callable(context_db):
                db_factory = lambda: _call_storage_factory(
                    context_db, PLUGIN_NAME, filename="stickers.db"
                )
        return StickerStore(
            data_dir=self._data_dir,
            data_dir_factory=data_factory,
            db_factory=db_factory,
        )

    @staticmethod
    def _open_existing_for_write(store: StickerStore) -> bool:
        """只为已存在的数据库打开可写 schema，避免发送探测创建空库。"""

        store.open(read_only=True, create_dirs=False)
        if store.connection is None or store.paths is None:
            return False
        try:
            schema_row = store.connection.execute(
                "SELECT value FROM sticker_schema_meta WHERE key = 'schema_version'"
            ).fetchone()
        except sqlite3.Error:
            schema_row = None
        if schema_row is None:
            store.close()
            return False
        store.close()
        store.open(read_only=False, create_dirs=False)
        return store.connection is not None

    @staticmethod
    def _read_candidates(
        connection: sqlite3.Connection, paths: StickerPaths, *, require_file: bool = True
    ) -> list[_StickerCandidate]:
        """只读取当前字段和有效 library 索引，不读取路径外文件。"""

        try:
            rows = connection.execute(
                """
                SELECT i.sticker_id, i.file_sha256, i.format, i.mime_type, i.size_bytes,
                       i.emotion, i.tags_json, i.description,
                       f.sha256, f.relative_path, f.mime_type, f.size_bytes
                FROM sticker_items AS i
                JOIN sticker_files AS f ON f.sha256 = i.file_sha256
                ORDER BY i.created_at ASC, i.sticker_id ASC
                """
            ).fetchall()
        except sqlite3.Error as error:
            raise StickerStorageError("sticker candidate query failed") from error

        result: list[_StickerCandidate] = []
        for row in rows:
            if not _valid_candidate_index(row, paths, require_file=require_file):
                continue
            tags = _decode_tags(row[6])
            if not isinstance(row[0], str) or not isinstance(row[1], str):
                continue
            if (
                not isinstance(row[5], str)
                or not isinstance(row[7], str)
                or isinstance(row[4], bool)
                or not isinstance(row[4], int)
            ):
                continue
            result.append(
                _StickerCandidate(
                    sticker_id=row[0],
                    file_sha256=row[1],
                    image_format=str(row[2]),
                    mime_type=str(row[3]),
                    size_bytes=int(row[4]),
                    emotion=row[5],
                    tags=tags,
                    description=row[7],
                    relative_path=row[9],
                )
            )
        return result

    @staticmethod
    def _match_candidates(
        candidates: Sequence[_StickerCandidate],
        query: StickerQuery,
        tokenizer: Any,
    ) -> list[_Match]:
        """执行情绪/标签硬筛选和固定词法证据分层。"""

        intent = normalize_sticker_text(query.intent) if query.intent is not None else None
        intent_tokens = (
            tuple(dict.fromkeys(tokenize_sticker_text(intent, tokenizer))) if intent else ()
        )
        matches: list[_Match] = []
        for candidate in candidates:
            if query.emotion is not None and candidate.emotion != query.emotion:
                continue
            candidate_tags = set(candidate.tags)
            tag_hits = len(candidate_tags.intersection(query.tags))
            if query.tags and tag_hits == 0:
                continue

            if intent:
                searchable = normalize_sticker_text(
                    " ".join((*candidate.tags, candidate.description))
                )
                candidate_tokens = set(tokenize_sticker_text(searchable, tokenizer))
                hit_tokens = len(candidate_tokens.intersection(intent_tokens))
                if intent in searchable:
                    layer = "phrase"
                elif intent_tokens and hit_tokens == len(intent_tokens):
                    layer = "all_tokens"
                elif hit_tokens:
                    layer = "partial_tokens"
                else:
                    continue
            elif query.tags:
                layer = "tags"
                hit_tokens = 0
            else:
                layer = "emotion"
                hit_tokens = 0

            if query.emotion is None and not query.tags and not intent:
                continue
            matches.append(_Match(candidate, layer, hit_tokens, tag_hits))
        return matches

    @staticmethod
    def _select_candidate(
        connection: sqlite3.Connection, matches: Sequence[_Match], chat_key: str
    ) -> _StickerCandidate | None:
        """先取最佳固定层级，再在完全并列池内做软轮换。"""

        if not matches:
            return None
        layer_order = {"emotion": 0, "tags": 1, "partial_tokens": 2, "all_tokens": 3, "phrase": 4}

        def rank(match: _Match) -> tuple[int, int, int]:
            return layer_order[match.layer], match.intent_token_hits, match.tag_hits

        best_rank = max(rank(match) for match in matches)
        pool = [match.candidate for match in matches if rank(match) == best_rank]
        if len(pool) == 1:
            return pool[0]
        usage: dict[str, str] = {}
        try:
            rows = connection.execute(
                "SELECT sticker_id, last_used_at FROM sticker_send_usage WHERE chat_key = ?",
                (chat_key,),
            ).fetchall()
            usage = {
                str(row[0]): str(row[1])
                for row in rows
                if isinstance(row[0], str) and isinstance(row[1], str)
            }
        except sqlite3.Error as error:
            raise StickerStorageError("sticker usage query failed") from error

        oldest_first = sorted(pool, key=lambda item: _usage_time(usage.get(item.sticker_id)))
        weights = [len(oldest_first) - index for index in range(len(oldest_first))]
        return random.choices(oldest_first, weights=weights, k=1)[0]

    @staticmethod
    def _materialize_selected(paths: StickerPaths, candidate: _StickerCandidate) -> str:
        """在单次受控读取中完成 containment、格式和双索引 hash 校验。"""

        path = _safe_library_path(paths, candidate.relative_path)
        if path is None:
            raise StickerSendStorageFailure("missing_file")
        try:
            verified, data = read_validated_image_file(path, paths.library)
        except FileNotFoundError:
            raise StickerSendStorageFailure("missing_file") from None
        except (OSError, ValueError):
            raise StickerSendStorageFailure("storage_error") from None
        if (
            verified.file_sha256 != candidate.file_sha256
            or verified.image_format != candidate.image_format
            or verified.mime_type != candidate.mime_type
            or verified.size_bytes != candidate.size_bytes
        ):
            raise StickerSendStorageFailure("storage_error")
        return "base64://" + base64.b64encode(data).decode("ascii")

    @staticmethod
    def _claim_use(
        connection: sqlite3.Connection,
        paths: StickerPaths,
        candidate: _StickerCandidate,
        chat_key: str,
    ) -> None:
        """短事务更新全局和当前 chat 的发送统计，不跨网络等待。"""

        now = datetime.now(UTC).isoformat(timespec="seconds")
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT i.sticker_id, i.file_sha256, i.format, i.mime_type, i.size_bytes,
                       i.emotion, i.tags_json, i.description,
                       f.sha256, f.relative_path, f.mime_type, f.size_bytes
                FROM sticker_items AS i
                JOIN sticker_files AS f ON f.sha256 = i.file_sha256
                WHERE i.sticker_id = ?
                """,
                (candidate.sticker_id,),
            ).fetchone()
            if row is None or not _valid_candidate_index(row, paths):
                connection.rollback()
                raise StickerSendStorageFailure("storage_error")
            if (
                row[1] != candidate.file_sha256
                or row[2] != candidate.image_format
                or row[3] != candidate.mime_type
                or row[4] != candidate.size_bytes
                or row[9] != candidate.relative_path
            ):
                connection.rollback()
                raise StickerSendStorageFailure("storage_error")
            updated = connection.execute(
                "UPDATE sticker_items SET use_count = use_count + 1, last_used_at = ? "
                "WHERE sticker_id = ?",
                (now, candidate.sticker_id),
            )
            if updated.rowcount != 1:
                connection.rollback()
                raise StickerSendStorageFailure("storage_error")
            connection.execute(
                """
                INSERT INTO sticker_send_usage(chat_key, sticker_id, last_used_at, use_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(chat_key, sticker_id) DO UPDATE SET
                    last_used_at = excluded.last_used_at,
                    use_count = sticker_send_usage.use_count + 1
                """,
                (chat_key, candidate.sticker_id, now),
            )
            connection.commit()
        except StickerSendStorageFailure:
            raise
        except (sqlite3.Error, TypeError, ValueError) as error:
            connection.rollback()
            raise StickerStorageError("sticker usage claim failed") from error


def _valid_candidate_index(
    row: Sequence[object], paths: StickerPaths, *, require_file: bool = True
) -> bool:
    """检查查询行的双索引和文件路径，不读取图片内容。"""

    if len(row) < 12:
        return False
    item_hash, image_format, item_mime, item_size = row[1], row[2], row[3], row[4]
    file_hash, relative_path, file_mime, file_size = row[8], row[9], row[10], row[11]
    if not all(isinstance(value, str) for value in (item_hash, image_format, item_mime, file_hash)):
        return False
    if item_hash != file_hash or item_mime != file_mime or item_size != file_size:
        return False
    path = _safe_library_path(paths, relative_path, require_file=require_file)
    if path is None:
        return False
    if path.is_file():
        parsed = validate_library_name(path, paths.library)
        return parsed is not None and parsed[0] == item_hash and parsed[1] == image_format
    stem = path.stem.lower()
    suffix_to_format = {".png": "png", ".jpg": "jpeg", ".gif": "gif", ".webp": "webp"}
    return (
        len(stem) == 64
        and all(character in "0123456789abcdef" for character in stem)
        and path.parent.name.lower() == stem[:2]
        and suffix_to_format.get(path.suffix.lower()) == image_format
        and stem == item_hash
    )


def _safe_library_path(
    paths: StickerPaths, relative_path: object, *, require_file: bool = True
) -> Path | None:
    """将数据库相对路径限制在 library 内且拒绝符号链接。"""

    if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
        return None
    raw_path = paths.root / relative_path
    if raw_path.is_symlink():
        return None
    path = raw_path.resolve(strict=False)
    try:
        path.relative_to(paths.library.resolve(strict=False))
    except (OSError, ValueError):
        return None
    if path.is_symlink() or not paths.contains(path):
        return None
    if require_file and not path.is_file():
        return None
    return path


def _usage_time(value: str | None) -> datetime:
    """把历史时间解析成排序值，非法历史按未使用处理。"""

    if not value:
        return datetime.min.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _call_storage_factory(factory: Callable[..., object], name: str, **kwargs: object) -> object:
    """兼容宿主把 storage helper 暴露为带 name 或无参方法的 fake。"""

    try:
        return factory(name, **kwargs)
    except TypeError:
        return factory(**kwargs)


def validate_sticker_chat_key(value: object) -> str:
    """验证当前 Tool 目标并限制到可发送的 QQ ID 范围。"""

    try:
        normalized = normalize_chat_key(value)
    except CanonicalError as error:
        raise ValueError("chat key is invalid") from error
    scene, raw_id = normalized.split(":", 1)
    peer_id = int(raw_id)
    if scene not in {"dm", "group"} or not _MIN_QQ_ID <= peer_id <= _MAX_QQ_ID:
        raise ValueError("chat key is invalid")
    return normalized


__all__ = [
    "StickerQuery",
    "StickerSendService",
    "StickerSendStorageFailure",
    "normalize_sticker_text",
    "parse_sticker_query",
    "tokenize_sticker_text",
    "validate_sticker_chat_key",
]
