"""Milky Tool 调用观察历史的本地存储与查询边界。"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PLUGIN_ID = "hermes-plugin-milky"
HISTORY_FILENAME = "tool-call-history.db"
RETENTION_DAYS = 30
MAX_RECORDS = 10_000
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MAX_PAGE = 100_000
MAX_SUMMARY_BYTES = 4096

_UTC = UTC
_STICKER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_FIELD_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")

# Hermes 会把 post_tool_call 的状态交给插件；这里只保留固定、低基数的观察分类。
OBSERVED_STATUSES = frozenset({"ok", "error", "blocked", "cancelled", "unknown"})
ERROR_TYPES = frozenset(
    {
        "tool_error",
        "invalid_input",
        "unsupported",
        "transport_unknown",
        "malformed",
        "blocked",
        "cancelled",
        "timeout",
        "unknown",
    }
)

_SAFE_INTEGER_FIELDS = frozenset(
    {
        "user_id",
        "group_id",
        "message_seq",
        "count",
        "duration",
        "limit",
        "notification_seq",
        "invitation_seq",
    }
)
_SAFE_BOOLEAN_FIELDS = frozenset(
    {
        "is_self",
        "no_cache",
        "is_self_send",
        "reject_add_request",
        "is_filtered",
        "is_mute",
    }
)
_SAFE_STRING_FIELDS = frozenset({"sticker_id"})


class HistoryInputError(ValueError):
    """表示 Dashboard 历史查询参数不满足有界查询合同。"""


def _declared_tool_metadata() -> tuple[frozenset[str], dict[str, frozenset[str]]]:
    """从本插件实际注册的 ToolSpec 取得名称和已知参数名。"""

    try:
        from outbound.tools import TOOL_SPECS
    except Exception:  # noqa: BLE001 - 导入阶段缺少可选宿主时保持空集合
        return frozenset(), {}
    names: set[str] = set()
    fields: dict[str, frozenset[str]] = {}
    for spec in TOOL_SPECS:
        if not isinstance(spec, Mapping):
            continue
        name = spec.get("name")
        if not isinstance(name, str) or not name:
            continue
        names.add(name)
        parameters = spec.get("parameters")
        properties = parameters.get("properties") if isinstance(parameters, Mapping) else None
        fields[name] = (
            frozenset(
                key for key in properties if isinstance(key, str) and _FIELD_RE.fullmatch(key)
            )
            if isinstance(properties, Mapping)
            else frozenset()
        )
    return frozenset(names), fields


def declared_tool_names() -> frozenset[str]:
    """返回当前 manifest/ToolSpec 对应的固定工具名称。"""

    return _declared_tool_metadata()[0]


def normalize_status(value: object) -> str:
    """将宿主观察状态归一化为固定集合。"""

    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().lower()
    aliases = {"success": "ok", "failed": "error", "failure": "error", "canceled": "cancelled"}
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in OBSERVED_STATUSES else "unknown"


def normalize_error_type(value: object) -> str | None:
    """只保留固定错误类型，不保存宿主自由文本。"""

    if value is None:
        return None
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().lower()
    return normalized if normalized in ERROR_TYPES else "unknown"


def normalize_duration(value: object) -> int:
    """将宿主耗时转换成非负、有界整数。"""

    if isinstance(value, bool):
        return 0
    try:
        duration = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return min(max(duration, 0), 2**63 - 1)


def _safe_integer(value: object) -> bool:
    """确认可保存的整数仍在 JSON/QQ 常用安全范围内。"""

    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 2**53 - 1


def _safe_value(field: str, value: object) -> object:
    """只投影确认过的数值、布尔值和贴纸 ID。"""

    if field in _SAFE_INTEGER_FIELDS and (_safe_integer(value) or value is None):
        return value
    if field in _SAFE_BOOLEAN_FIELDS and (isinstance(value, bool) or value is None):
        return value
    if field in _SAFE_STRING_FIELDS and isinstance(value, str) and _STICKER_ID_RE.fullmatch(value):
        return value
    return {"provided": True}


def summarize_args(tool_name: str, args: object) -> str:
    """按工具 schema 白名单生成不含原始参数值的 JSON 摘要。"""

    _names, fields_by_tool = _declared_tool_metadata()
    known_fields = fields_by_tool.get(tool_name, frozenset())
    if not isinstance(args, Mapping):
        return json.dumps(
            {"args": {"provided": args is not None}},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    summary: dict[str, object] = {}
    unknown_present = False
    for raw_key, value in args.items():
        if not isinstance(raw_key, str) or not _FIELD_RE.fullmatch(raw_key):
            unknown_present = True
            continue
        if raw_key not in known_fields:
            unknown_present = True
            continue
        summary[raw_key] = _safe_value(raw_key, value)
    if unknown_present:
        summary["unknown_fields"] = {"provided": True}
    serialized = json.dumps(
        summary,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(serialized.encode("utf-8")) <= MAX_SUMMARY_BYTES:
        return serialized
    return '{"summary":"truncated","fields_provided":true}'


def _coerce_utc(value: object) -> datetime:
    """读取可控时钟或查询边界，并返回带 UTC 时区的时间。"""

    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            result = datetime.fromisoformat(text)
        except ValueError:
            raise HistoryInputError("invalid_input") from None
    else:
        raise HistoryInputError("invalid_input")
    if result.tzinfo is None:
        result = result.replace(tzinfo=_UTC)
    return result.astimezone(_UTC)


def _utc_text(value: object) -> str:
    """生成稳定的 UTC ISO 8601 文本。"""

    return _coerce_utc(value).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _default_clock() -> datetime:
    """取得当前 UTC 时间，供观察和保留清理使用。"""

    return datetime.now(_UTC)


def _profile_home() -> Path | None:
    """从 Hermes 当前 profile 取得 home；无法确认时拒绝写入。"""

    try:
        from hermes_constants import get_hermes_home

        home = get_hermes_home()
    except Exception:  # noqa: BLE001 - hook 观察必须 fail-open
        return None
    if not isinstance(home, Path):
        try:
            home = Path(home)
        except TypeError:
            return None
    try:
        return home.resolve()
    except OSError:
        return None


def history_root(profile_home: Path) -> Path:
    """计算 profile 的固定插件数据根，不创建目录。"""

    return Path(profile_home) / "plugin-data" / PLUGIN_ID


class ToolCallHistoryStore:
    """一个 profile 的调用历史；构造和只读查询都不会创建文件。"""

    def __init__(self, root: Path, *, clock: Callable[[], object] | None = None) -> None:
        self.root = Path(root)
        self.clock = clock or _default_clock
        self._write_lock = threading.Lock()

    @property
    def db_path(self) -> Path:
        """返回固定数据库路径。"""

        return self.root / HISTORY_FILENAME

    def _connect_write(self) -> sqlite3.Connection:
        """创建短事务连接并初始化 schema。"""

        if self.db_path.is_symlink():
            raise OSError("history database symlink is not writable")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        connection = sqlite3.connect(self.db_path, timeout=0.5)
        connection.execute("PRAGMA busy_timeout=500")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_calls (
                record_id TEXT PRIMARY KEY,
                observed_at_utc TEXT NOT NULL,
                duration_ms INTEGER NOT NULL CHECK(duration_ms >= 0),
                tool_name TEXT NOT NULL,
                status TEXT NOT NULL,
                error_type TEXT,
                args_summary_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_tool_calls_observed_at ON tool_calls(observed_at_utc)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_tool_calls_tool_name ON tool_calls(tool_name)"
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_tool_calls_status ON tool_calls(status)")
        return connection

    def record(
        self,
        tool_name: object,
        args: object,
        duration_ms: object,
        status: object,
        error_type: object = None,
        *,
        observed_at: object | None = None,
    ) -> bool:
        """追加一条观察记录；任何存储错误均按 fail-open 返回 False。"""

        names = declared_tool_names()
        if not isinstance(tool_name, str) or tool_name not in names:
            return False
        try:
            clock_now = _coerce_utc(self.clock())
            observed_time = clock_now if observed_at is None else _coerce_utc(observed_at)
            observed_text = _utc_text(observed_time)
            cutoff = _utc_text(clock_now - timedelta(days=RETENTION_DAYS))
            safe_status = normalize_status(status)
            safe_error_type = normalize_error_type(error_type)
            summary = summarize_args(tool_name, args)
            with self._write_lock:
                connection = self._connect_write()
                try:
                    connection.execute(
                        "INSERT INTO tool_calls "
                        "(record_id, observed_at_utc, duration_ms, tool_name, status, error_type, args_summary_json) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            secrets.token_hex(16),
                            observed_text,
                            normalize_duration(duration_ms),
                            tool_name,
                            safe_status,
                            safe_error_type,
                            summary,
                        ),
                    )
                    connection.execute(
                        "DELETE FROM tool_calls WHERE observed_at_utc < ?", (cutoff,)
                    )
                    connection.execute(
                        "DELETE FROM tool_calls WHERE record_id IN ("
                        "SELECT record_id FROM tool_calls "
                        "ORDER BY observed_at_utc ASC, record_id ASC "
                        "LIMIT -1 OFFSET ?)",
                        (MAX_RECORDS,),
                    )
                    connection.commit()
                finally:
                    connection.close()
            return True
        except Exception:  # noqa: BLE001 - 观察路径绝不改变原 Tool 结果
            return False

    def observe(self, **event: object) -> bool:
        """接收 Hermes post_tool_call 的关键字段并写入历史。"""

        return self.record(
            event.get("tool_name"),
            event.get("args"),
            event.get("duration_ms", 0),
            event.get("status"),
            event.get("error_type"),
        )

    @staticmethod
    def _validate_page(page: object, limit: object) -> tuple[int, int, int]:
        """验证有界页码和偏移量。"""

        if (
            isinstance(page, bool)
            or isinstance(limit, bool)
            or not isinstance(page, int)
            or not isinstance(limit, int)
            or page < 1
            or page > MAX_PAGE
            or limit < 1
            or limit > MAX_PAGE_SIZE
        ):
            raise HistoryInputError("invalid_input")
        return page, limit, (page - 1) * limit

    @staticmethod
    def _validate_filter(value: object, *, max_length: int = 128) -> str | None:
        """验证有限查询字符串，不把原始字段写入任何日志。"""

        if value is None or value == "":
            return None
        if not isinstance(value, str) or len(value) > max_length or "\x00" in value:
            raise HistoryInputError("invalid_input")
        return value

    def query(
        self,
        *,
        page: int = 1,
        limit: int = DEFAULT_PAGE_SIZE,
        start: object | None = None,
        end: object | None = None,
        tool_name: object | None = None,
        status: object | None = None,
        profile_name: str | None = None,
    ) -> dict[str, object]:
        """只读查询既有数据库，并对列表与统计使用同一过滤范围。"""

        page, limit, offset = self._validate_page(page, limit)
        start_text = _utc_text(start) if start not in (None, "") else None
        end_text = _utc_text(end) if end not in (None, "") else None
        tool_filter = self._validate_filter(tool_name)
        status_filter = self._validate_filter(status)
        if tool_filter is not None and tool_filter not in declared_tool_names():
            # 未知工具只产生空结果，不扩大查询范围。
            tool_filter = f"__unknown_tool__:{tool_filter}"
        if status_filter is not None:
            status_filter = normalize_status(status_filter)
            if status_filter == "unknown" and status not in {"unknown", ""}:
                status_filter = "__unknown_status__"
        if start_text and end_text and start_text > end_text:
            raise HistoryInputError("invalid_input")
        result = self._empty_result(profile_name, page, limit)
        if self.db_path.is_symlink() or not self.db_path.is_file():
            return result
        where = []
        values: list[object] = []
        if start_text:
            where.append("observed_at_utc >= ?")
            values.append(start_text)
        if end_text:
            where.append("observed_at_utc <= ?")
            values.append(end_text)
        if tool_filter:
            where.append("tool_name = ?")
            values.append(tool_filter)
        if status_filter:
            where.append("status = ?")
            values.append(status_filter)
        clause = " WHERE " + " AND ".join(where) if where else ""
        try:
            connection = sqlite3.connect(
                f"file:{self.db_path.as_posix()}?mode=ro", uri=True, timeout=0.5
            )
            try:
                summary_row = connection.execute(
                    "SELECT COUNT(*), COALESCE(SUM(duration_ms), 0), "
                    "COALESCE(AVG(duration_ms), 0), COALESCE(MIN(duration_ms), 0), "
                    "COALESCE(MAX(duration_ms), 0) FROM tool_calls" + clause,
                    values,
                ).fetchone()
                by_tool_rows = connection.execute(
                    "SELECT tool_name, COUNT(*) FROM tool_calls"
                    + clause
                    + " GROUP BY tool_name ORDER BY tool_name",
                    values,
                ).fetchall()
                by_status_rows = connection.execute(
                    "SELECT status, COUNT(*) FROM tool_calls"
                    + clause
                    + " GROUP BY status ORDER BY status",
                    values,
                ).fetchall()
                rows = connection.execute(
                    "SELECT record_id, observed_at_utc, duration_ms, tool_name, status, error_type, "
                    "args_summary_json FROM tool_calls"
                    + clause
                    + " ORDER BY observed_at_utc DESC, record_id DESC LIMIT ? OFFSET ?",
                    [*values, limit, offset],
                ).fetchall()
            finally:
                connection.close()
        except (sqlite3.Error, OSError):
            # 已有但不可读的库不应让 Dashboard 泄漏底层细节。
            raise RuntimeError("history storage unavailable") from None
        count, total_duration, average_duration, minimum_duration, maximum_duration = summary_row
        summary = {
            "count": int(count),
            "total_duration_ms": int(total_duration),
            "average_duration_ms": float(average_duration),
            "min_duration_ms": int(minimum_duration),
            "max_duration_ms": int(maximum_duration),
            "by_tool": {str(name): int(value) for name, value in by_tool_rows},
            "by_status": {str(name): int(value) for name, value in by_status_rows},
        }
        result.update(
            total=int(count),
            items=[self._row_to_item(row) for row in rows],
            summary=summary,
        )
        return result

    @staticmethod
    def _row_to_item(row: tuple[object, ...]) -> dict[str, object]:
        """将数据库行转换成固定 JSON 记录。"""

        try:
            summary = json.loads(row[6])
        except (TypeError, ValueError):
            summary = {"summary": "unavailable"}
        if not isinstance(summary, dict):
            summary = {"summary": "unavailable"}
        return {
            "record_id": str(row[0]),
            "observed_at_utc": str(row[1]),
            "duration_ms": int(row[2]),
            "tool_name": str(row[3]),
            "status": str(row[4]),
            "error_type": row[5] if isinstance(row[5], str) else None,
            "args_summary": summary,
        }

    @staticmethod
    def _empty_result(profile_name: str | None, page: int, limit: int) -> dict[str, object]:
        """构造缺少数据库或无匹配记录时的稳定响应。"""

        return {
            "profile": profile_name,
            "page": page,
            "limit": limit,
            "total": 0,
            "items": [],
            "summary": {
                "count": 0,
                "total_duration_ms": 0,
                "average_duration_ms": 0.0,
                "min_duration_ms": 0,
                "max_duration_ms": 0,
                "by_tool": {},
                "by_status": {},
            },
        }


# 每个 profile 一个观察 store；对象本身不创建文件，且不保存原始事件。
_OBSERVER = None
_OBSERVER_LOCK = threading.Lock()


class ToolCallHistoryObserver:
    """Hermes post_tool_call 的只读、容错观察回调。"""

    def __init__(
        self,
        *,
        profile_home_provider: Callable[[], Path | None] = _profile_home,
        clock: Callable[[], object] | None = None,
    ) -> None:
        self.profile_home_provider = profile_home_provider
        self.clock = clock
        self._stores: dict[Path, ToolCallHistoryStore] = {}
        self._lock = threading.Lock()

    def _store(self, home: Path) -> ToolCallHistoryStore:
        key = home.resolve()
        with self._lock:
            store = self._stores.get(key)
            if store is None:
                store = ToolCallHistoryStore(history_root(key), clock=self.clock)
                self._stores[key] = store
            return store

    def observe(self, **event: object) -> bool:
        """筛选固定工具并尽力写入；任何失败均不向 Tool 调用抛出异常。"""

        try:
            tool_name = event.get("tool_name")
            if not isinstance(tool_name, str) or tool_name not in declared_tool_names():
                return False
            home = self.profile_home_provider()
            if home is None:
                return False
            return self._store(Path(home)).observe(**event)
        except Exception:  # noqa: BLE001 - Hermes hook 必须 fail-open
            return False


def _global_observer() -> ToolCallHistoryObserver:
    """取得进程内观察器，不在注册阶段解析 profile 或创建存储。"""

    global _OBSERVER
    with _OBSERVER_LOCK:
        if _OBSERVER is None:
            _OBSERVER = ToolCallHistoryObserver()
        return _OBSERVER


def _post_tool_call(**event: object) -> None:
    """Hermes hook 回调；不读取 result、error_message 或 middleware_trace。"""

    _global_observer().observe(**event)


def register_tool_call_history(ctx: Any) -> None:
    """登记 post_tool_call 观察 hook，不启动任务、网络或持久化。"""

    register_hook = getattr(ctx, "register_hook", None)
    if callable(register_hook):
        register_hook("post_tool_call", _post_tool_call)


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "ERROR_TYPES",
    "HISTORY_FILENAME",
    "MAX_PAGE_SIZE",
    "MAX_RECORDS",
    "OBSERVED_STATUSES",
    "RETENTION_DAYS",
    "HistoryInputError",
    "ToolCallHistoryObserver",
    "ToolCallHistoryStore",
    "declared_tool_names",
    "history_root",
    "normalize_duration",
    "normalize_error_type",
    "normalize_status",
    "register_tool_call_history",
    "summarize_args",
]
