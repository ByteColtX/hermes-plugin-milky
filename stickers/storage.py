"""QQ 贴纸的懒加载 SQLite store 和受控文件目录。"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from .errors import StickerStorageError, StickerUnsupportedError

PLUGIN_NAME = "hermes-plugin-milky"
STICKER_DB_FILENAME = "stickers.db"
SCHEMA_VERSION = 3


@dataclass(frozen=True, slots=True)
class StickerPaths:
    """贴纸存储的固定目录。"""

    root: Path
    stickers: Path
    inbox: Path
    library: Path
    junk: Path

    @classmethod
    def from_root(cls, root: Path, *, create: bool = True) -> StickerPaths:
        """从 Hermes plugin-data 根目录解析固定子目录。"""

        root = Path(root).resolve()
        stickers = root / "stickers"
        paths = cls(root, stickers, stickers / "inbox", stickers / "library", stickers / "junk")
        if create:
            for path in (paths.inbox, paths.library, paths.junk):
                path.mkdir(parents=True, exist_ok=True)
        return paths

    def contains(self, path: Path) -> bool:
        """判断路径是否位于插件持久化根目录。"""

        try:
            Path(path).resolve(strict=False).relative_to(self.root)
        except (OSError, ValueError):
            return False
        return True

    def library_path(self, file_sha256: str, suffix: str) -> Path:
        """生成受控 content-addressed library 路径。"""

        if len(file_sha256) != 64 or any(char not in "0123456789abcdef" for char in file_sha256):
            raise ValueError("invalid file hash")
        if suffix not in {".png", ".jpg", ".gif", ".webp"}:
            raise ValueError("invalid image suffix")
        return self.library / file_sha256[:2] / f"{file_sha256}{suffix}"

    def relative(self, path: Path) -> str:
        """返回相对插件持久根目录的 POSIX 路径。"""

        path = Path(path).resolve(strict=False)
        if not self.contains(path):
            raise ValueError("path is outside plugin storage")
        return path.relative_to(self.root).as_posix()


class StickerStore:
    """一次命令范围内打开的独立贴纸数据库。"""

    def __init__(
        self,
        *,
        data_dir_factory: Callable[[], Path] | None = None,
        db_factory: Callable[[], sqlite3.Connection] | None = None,
        data_dir: Path | None = None,
    ) -> None:
        """创建懒加载 store；构造阶段不访问文件系统。"""

        self._data_dir_factory = data_dir_factory
        self._db_factory = db_factory
        self._data_dir = Path(data_dir) if data_dir is not None else None
        self.paths: StickerPaths | None = None
        self.connection: sqlite3.Connection | None = None

    def open(self, *, read_only: bool = False, create_dirs: bool = True) -> StickerStore:
        """在第一次命令操作时创建固定目录并初始化 schema。"""

        if self.connection is not None:
            return self
        try:
            root = self._data_dir
            if root is None:
                if self._data_dir_factory is None:
                    if read_only:
                        from hermes_constants import get_hermes_home

                        root = get_hermes_home() / "plugin-data" / PLUGIN_NAME
                    else:
                        from plugins.plugin_storage import plugin_data_dir

                        root = plugin_data_dir(PLUGIN_NAME)
                else:
                    root = self._data_dir_factory()
            self.paths = StickerPaths.from_root(Path(root), create=create_dirs)
            if read_only and not (self.paths.root / STICKER_DB_FILENAME).is_file():
                return self
            if read_only:
                self.connection = sqlite3.connect(
                    (self.paths.root / STICKER_DB_FILENAME).as_uri() + "?mode=ro",
                    uri=True,
                    check_same_thread=False,
                )
            elif self._db_factory is None:
                if self._data_dir is not None or self._data_dir_factory is not None:
                    self.connection = sqlite3.connect(
                        self.paths.root / STICKER_DB_FILENAME, check_same_thread=False
                    )
                else:
                    from plugins.plugin_storage import plugin_db

                    self.connection = plugin_db(PLUGIN_NAME, filename=STICKER_DB_FILENAME)
            else:
                self.connection = self._db_factory()
            self.connection.execute("PRAGMA foreign_keys=ON")
            if not read_only:
                self._initialize_schema(self.connection)
            return self
        except StickerUnsupportedError:
            self.close()
            raise
        except StickerStorageError:
            self.close()
            raise
        except Exception as error:
            self.close()
            raise StickerStorageError("database initialization failed") from error

    def close(self) -> None:
        """关闭当前命令拥有的数据库连接。"""

        connection = self.connection
        self.connection = None
        if connection is not None:
            try:
                connection.close()
            except Exception:  # noqa: BLE001 - close must not leak storage details
                return

    def __enter__(self) -> Self:
        return self.open()

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()

    @staticmethod
    def _initialize_schema(connection: sqlite3.Connection) -> None:
        """创建 schema 或执行受限的已知迁移。"""

        connection.execute(
            "CREATE TABLE IF NOT EXISTS sticker_schema_meta "
            "(key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)"
        )
        row = connection.execute(
            "SELECT value FROM sticker_schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sticker_items (
                    sticker_id TEXT PRIMARY KEY NOT NULL,
                    file_sha256 TEXT NOT NULL UNIQUE,
                    format TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    detected_emotion TEXT NOT NULL,
                    detected_tags_json TEXT NOT NULL,
                    detected_description TEXT NOT NULL,
                    emotion TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    description TEXT NOT NULL,
                    emotion_source TEXT NOT NULL,
                    tags_source TEXT NOT NULL,
                    description_source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    detected_at TEXT NOT NULL,
                    use_count INTEGER NOT NULL DEFAULT 0,
                    last_used_at TEXT NULL
                );
                CREATE TABLE IF NOT EXISTS sticker_files (
                    sha256 TEXT PRIMARY KEY NOT NULL,
                    relative_path TEXT NOT NULL UNIQUE,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    verified_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sticker_send_usage (
                    chat_key TEXT NOT NULL,
                    sticker_id TEXT NOT NULL,
                    last_used_at TEXT NOT NULL,
                    use_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (chat_key, sticker_id),
                    FOREIGN KEY (sticker_id) REFERENCES sticker_items(sticker_id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_sticker_send_usage_chat_last_used
                    ON sticker_send_usage(chat_key, last_used_at);
                """
            )
            connection.execute(
                "INSERT INTO sticker_schema_meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            connection.commit()
            return
        try:
            version = int(row[0])
        except (TypeError, ValueError) as error:
            raise StickerUnsupportedError("invalid schema version") from error
        if version not in {1, 2, SCHEMA_VERSION}:
            raise StickerUnsupportedError("unsupported schema version")

        try:
            connection.execute("BEGIN")
            if version == 1:
                connection.execute(
                    "ALTER TABLE sticker_items ADD COLUMN use_count INTEGER NOT NULL DEFAULT 0"
                )
                connection.execute("ALTER TABLE sticker_items ADD COLUMN last_used_at TEXT NULL")
                version = 2
            if version == 2:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sticker_send_usage (
                        chat_key TEXT NOT NULL,
                        sticker_id TEXT NOT NULL,
                        last_used_at TEXT NOT NULL,
                        use_count INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (chat_key, sticker_id),
                        FOREIGN KEY (sticker_id) REFERENCES sticker_items(sticker_id)
                            ON DELETE CASCADE
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_sticker_send_usage_chat_last_used "
                    "ON sticker_send_usage(chat_key, last_used_at)"
                )
                version = SCHEMA_VERSION
            connection.execute(
                "UPDATE sticker_schema_meta SET value = ? WHERE key = 'schema_version'",
                (str(version),),
            )
            connection.commit()
        except Exception as error:
            connection.rollback()
            raise StickerStorageError("schema migration failed") from error

        if version != SCHEMA_VERSION:
            raise StickerUnsupportedError("unsupported schema version")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sticker_send_usage (
                chat_key TEXT NOT NULL,
                sticker_id TEXT NOT NULL,
                last_used_at TEXT NOT NULL,
                use_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (chat_key, sticker_id),
                FOREIGN KEY (sticker_id) REFERENCES sticker_items(sticker_id)
                    ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_sticker_send_usage_chat_last_used "
            "ON sticker_send_usage(chat_key, last_used_at)"
        )
        connection.commit()
        required = {
            "sticker_items": {
                "sticker_id",
                "file_sha256",
                "format",
                "mime_type",
                "size_bytes",
                "detected_emotion",
                "detected_tags_json",
                "detected_description",
                "emotion",
                "tags_json",
                "description",
                "emotion_source",
                "tags_source",
                "description_source",
                "created_at",
                "updated_at",
                "detected_at",
                "use_count",
                "last_used_at",
            },
            "sticker_files": {"sha256", "relative_path", "mime_type", "size_bytes", "verified_at"},
            "sticker_send_usage": {"chat_key", "sticker_id", "last_used_at", "use_count"},
        }
        for table, columns in required.items():
            actual = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            if not columns.issubset(actual):
                raise StickerUnsupportedError("incompatible schema")


__all__ = ["PLUGIN_NAME", "SCHEMA_VERSION", "STICKER_DB_FILENAME", "StickerPaths", "StickerStore"]
