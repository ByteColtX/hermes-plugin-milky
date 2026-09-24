"""Dashboard 使用的只读图库查询与受控媒体读取。"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .coordination import library_guard
from .errors import StickerError, StickerStorageError
from .maintenance import EMOTIONS, StickerMaintenanceService, _parse_id
from .sending import _validate_read_schema
from .storage import STICKER_DB_FILENAME, StickerPaths, StickerStore
from .validation import read_validated_image_file


@contextmanager
def existing_store(root: Path):
    """只读打开已有数据库，不创建目录、数据库或迁移。"""
    root = Path(root).resolve()
    database = root / STICKER_DB_FILENAME
    store = StickerStore(data_dir=root)
    store.paths = StickerPaths.from_root(root, create=False)
    try:
        if database.exists():
            if database.is_symlink() or not database.is_file():
                raise StickerStorageError("invalid database")
            store.connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
            store.connection.execute("PRAGMA query_only = ON")
            _validate_read_schema(store.connection)
        yield store
    except sqlite3.Error:
        raise StickerStorageError("read failed") from None
    finally:
        store.close()


class StickerManagementService:
    """以宿主已确认的图库根提供有界只读操作。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def browse(
        self,
        *,
        page: int = 1,
        limit: int = 20,
        emotion: str | None = None,
        tag: str | None = None,
        description: str | None = None,
    ) -> dict[str, object]:
        """按创建时间及 ID 稳定分页，过滤值只作为 SQL 参数。"""
        if type(page) is not int or not 1 <= page <= 1_000_000:
            raise StickerError("invalid_input")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise StickerError("invalid_input")
        if emotion is not None and emotion not in EMOTIONS:
            raise StickerError("invalid_input")
        for value, maximum in ((tag, 16), (description, 100)):
            if value is not None and (
                not isinstance(value, str) or not value.strip() or len(value) > maximum
            ):
                raise StickerError("invalid_input")
        with existing_store(self.root) as store:
            conn = store.connection
            if conn is None:
                return {"status": "ok", "items": [], "total": 0, "page": page, "limit": limit}
            clauses, parameters = [], []
            if emotion is not None:
                clauses.append("i.emotion = ?")
                parameters.append(emotion)
            if tag is not None:
                clauses.append("EXISTS (SELECT 1 FROM json_each(i.tags_json) WHERE value = ?)")
                parameters.append(tag)
            if description is not None:
                clauses.append("instr(i.description, ?) > 0")
                parameters.append(description)
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            total = conn.execute(
                "SELECT count(*) FROM sticker_items i" + where, parameters
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT i.sticker_id, i.file_sha256, i.format, i.mime_type, i.size_bytes, "
                "i.emotion, i.tags_json, i.description, i.emotion_source, i.tags_source, "
                "i.description_source, i.created_at, i.updated_at, i.detected_at, "
                "i.use_count, i.last_used_at FROM sticker_items i"
                + where
                + " ORDER BY i.created_at, i.sticker_id LIMIT ? OFFSET ?",
                [*parameters, limit, (page - 1) * limit],
            ).fetchall()
            items = []
            for row in rows:
                item = StickerMaintenanceService._row_to_public(row)
                item["version"] = StickerMaintenanceService.item_version(store, row[0])
                file_row = conn.execute(
                    "SELECT relative_path FROM sticker_files WHERE sha256 = ?", (row[1],)
                ).fetchone()
                item["file_status"] = "missing_file"
                if file_row and store.paths:
                    path = self._library_path(store.paths, file_row[0])
                    if path is not None and path.is_file():
                        item["file_status"] = "available"
                items.append(item)
            return {"status": "ok", "items": items, "total": total, "page": page, "limit": limit}

    def preview(self, sticker_id: str) -> tuple[bytes, str]:
        """复核条目、索引和图片完整性后返回一次读取的媒体。"""
        try:
            _parse_id(sticker_id)
        except (TypeError, ValueError):
            raise StickerError("invalid_input") from None
        if not self.root.is_dir():
            raise StickerError("not_found")
        with library_guard(self.root), existing_store(self.root) as store:
            if store.connection is None or store.paths is None:
                raise StickerError("not_found")
            row = store.connection.execute(
                "SELECT i.file_sha256, i.format, i.mime_type, i.size_bytes, "
                "f.relative_path, f.mime_type, f.size_bytes FROM sticker_items i "
                "LEFT JOIN sticker_files f ON f.sha256 = i.file_sha256 WHERE i.sticker_id = ?",
                (sticker_id,),
            ).fetchone()
            if row is None:
                raise StickerError("not_found")
            path = self._library_path(store.paths, row[4])
            if path is None:
                raise StickerError("integrity_error")
            if not path.is_file():
                raise StickerError("missing_file")
            try:
                candidate, data = read_validated_image_file(path, store.paths.library)
            except (ValueError, OSError):
                raise StickerError("integrity_error") from None
            if (
                candidate.file_sha256,
                candidate.image_format,
                candidate.mime_type,
                candidate.size_bytes,
            ) != row[:4] or (candidate.mime_type, candidate.size_bytes) != row[5:]:
                raise StickerError("integrity_error")
            return data, candidate.mime_type

    @staticmethod
    def _library_path(paths: StickerPaths, relative: object) -> Path | None:
        """拒绝非受控路径及任一层符号链接。"""
        if not isinstance(relative, str) or Path(relative).is_absolute():
            return None
        path = paths.root / relative
        if ".." in Path(relative).parts:
            return None
        try:
            path.relative_to(paths.library)
            path.resolve().relative_to(paths.library.resolve())
        except (ValueError, OSError):
            return None
        if any(part.is_symlink() for part in (path, *path.parents) if part != paths.root.parent):
            return None
        return path

    def mutate(
        self,
        operation: str,
        targets: list,
        *,
        sets=None,
        clears=None,
        guard=lambda: None,
        progress=lambda items: None,
    ):
        """明确 ID 和版本的逐项提交；字段校验先于任一写入。"""
        from .maintenance import _parse_edit_options

        if (
            operation not in {"edit", "delete"}
            or not isinstance(targets, list)
            or not 1 <= len(targets) <= 50
        ):
            raise StickerError("invalid_input")
        seen = set()
        for target in targets:
            if not isinstance(target, dict) or set(target) != {"sticker_id", "version"}:
                raise StickerError("invalid_input")
            _parse_id(target["sticker_id"])
            if target["sticker_id"] in seen or not isinstance(target["version"], str):
                raise StickerError("invalid_input")
            seen.add(target["sticker_id"])
        sets, clears = sets or {}, clears or []
        if operation == "edit":
            if not isinstance(sets, dict) or not isinstance(clears, list):
                raise StickerError("invalid_input")
            options = []
            for key, value in sets.items():
                if (
                    key == "tags"
                    and isinstance(value, list)
                    and all(isinstance(v, str) for v in value)
                ):
                    value = ",".join(value)
                if not isinstance(value, str):
                    raise StickerError("invalid_input")
                options.append(f"--{key}={value}")
            if clears:
                if not all(isinstance(v, str) for v in clears):
                    raise StickerError("invalid_input")
                options.append("--clear=" + ",".join(clears))
            try:
                sets, clears = _parse_edit_options(options)
            except ValueError:
                raise StickerError("invalid_input") from None
        items = _ProgressItems(progress, [{"sticker_id": x["sticker_id"]} for x in targets])
        for target in targets:
            guard()
            items.begin("sticker_id", target["sticker_id"])
            if not (self.root / STICKER_DB_FILENAME).exists():
                items.append({"sticker_id": target["sticker_id"], "status": "not_found"})
                continue
            with library_guard(self.root), StickerStore(data_dir=self.root) as store:
                guard()
                current = StickerMaintenanceService.item_version(store, target["sticker_id"])
                if current is None:
                    result = {"status": "not_found"}
                elif current != target["version"]:
                    result = {"status": "conflict"}
                else:
                    service = StickerMaintenanceService(data_dir=self.root)
                    result = (
                        service._edit(store, target["sticker_id"], sets, frozenset(clears))
                        if operation == "edit"
                        else service._delete(store, target["sticker_id"])
                    )
                items.append({"sticker_id": target["sticker_id"], **result})
        return {
            "items": items,
            "task_status": "succeeded"
            if all(x["status"] in {"updated", "deleted"} for x in items)
            else "partial",
        }

    def cleanup_plan(self):
        """持久保存明确清理对象快照，执行时不纳入新文件。"""
        import hashlib
        import json
        import secrets
        import time

        from .validation import validate_library_name

        if not self.root.exists():
            return {"status": "empty", "count": 0}
        with library_guard(self.root), existing_store(self.root) as store:
            paths = store.paths
            refs = (
                set()
                if store.connection is None
                else {
                    x[0] for x in store.connection.execute("SELECT file_sha256 FROM sticker_items")
                }
            )
            candidates = []
            counts = {"orphan": 0, "temporary": 0}
            for path in sorted(paths.library.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                parsed = validate_library_name(path, paths.library)
                if path.name.endswith((".tmp", ".part", ".staging")) or (
                    parsed and parsed[0] not in refs
                ):
                    counts[
                        "temporary"
                        if path.name.endswith((".tmp", ".part", ".staging"))
                        else "orphan"
                    ] += 1
                    stat = path.stat()
                    candidates.append(
                        {
                            "relative": path.relative_to(paths.root).as_posix(),
                            "size": stat.st_size,
                            "mtime": stat.st_mtime_ns,
                            "inode": stat.st_ino,
                        }
                    )
            plan_id = secrets.token_hex(24)
            directory = self.root / "cleanup-plans"
            directory.mkdir(exist_ok=True)
            # 计划有界，旧文件可丢弃，因为过期不会作为新任务执行。
            plans = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime)
            for path in plans[:-99]:
                path.unlink()
            data = {
                "created": time.time(),
                "candidates": candidates,
                "refs": hashlib.sha256(json.dumps(sorted(refs)).encode()).hexdigest(),
            }
            (directory / (plan_id + ".json")).write_text(json.dumps(data), encoding="utf-8")
            return {
                "plan_id": plan_id,
                "count": len(candidates),
                "categories": counts,
                "expires_in": 600,
            }

    def cleanup_execute(self, plan_id, *, guard=lambda: None, progress=lambda items: None):
        """计划过期或引用变化拒绝执行；文件发生变化逐项跳过。"""
        import hashlib
        import json
        import time

        if (
            not isinstance(plan_id, str)
            or len(plan_id) != 48
            or any(c not in "0123456789abcdef" for c in plan_id)
        ):
            raise StickerError("invalid_input")
        with library_guard(self.root), existing_store(self.root) as store:
            guard()
            plan_file = self.root / "cleanup-plans" / (plan_id + ".json")
            try:
                data = json.loads(plan_file.read_text())
            except (OSError, ValueError):
                raise StickerError("expired") from None
            if time.time() - data["created"] > 600:
                raise StickerError("expired")
            refs = (
                set()
                if store.connection is None
                else {
                    x[0] for x in store.connection.execute("SELECT file_sha256 FROM sticker_items")
                }
            )
            if hashlib.sha256(json.dumps(sorted(refs)).encode()).hexdigest() != data["refs"]:
                raise StickerError("conflict")
            removed, skipped = 0, 0
            for item in data["candidates"]:
                guard()
                path = self._library_path(store.paths, item["relative"])
                if path is None or not path.is_file():
                    skipped += 1
                    continue
                stat = path.stat()
                if (stat.st_size, stat.st_mtime_ns, stat.st_ino) != (
                    item["size"],
                    item["mtime"],
                    item["inode"],
                ):
                    skipped += 1
                    continue
                path.unlink()
                removed += 1
            plan_file.unlink()
            return {
                "removed": removed,
                "skipped": skipped,
                "task_status": "partial" if skipped else "succeeded",
            }

    async def import_candidates(
        self, input_root, candidates, *, guard=lambda: None, progress=lambda items: None
    ):
        """Web 只处理明确候选，确定性校验与去重先于视觉调用。"""
        import asyncio

        from .maintenance import parse_visual_response
        from .validation import validate_image_file

        service = StickerMaintenanceService(data_dir=self.root)
        items = _ProgressItems(progress, [{"file_id": x[0]} for x in candidates])
        if not 1 <= len(candidates) <= 50:
            raise StickerError("invalid_input")
        hashes = set()
        for file_id, path in candidates:
            guard()
            items.begin("file_id", file_id)
            try:
                candidate = validate_image_file(path, input_root)
            except (ValueError, OSError):
                items.append({"file_id": file_id, "status": "rejected"})
                continue
            with StickerStore(data_dir=self.root) as store, library_guard(self.root):
                guard()
                duplicate = store.connection.execute(
                    "SELECT 1 FROM sticker_items WHERE file_sha256=?", (candidate.file_sha256,)
                ).fetchone()
                if duplicate:
                    destination = store.paths.library_path(candidate.file_sha256, candidate.suffix)
                    try:
                        verified = validate_image_file(destination, store.paths.library)
                    except (ValueError, OSError):
                        items.append({"file_id": file_id, "status": "missing_file"})
                        continue
                    if verified.file_sha256 != candidate.file_sha256:
                        items.append({"file_id": file_id, "status": "integrity_error"})
                        continue
                    service._unlink_inbox(path, input_root)
                    items.append({"file_id": file_id, "status": "duplicate"})
                    continue
            if candidate.file_sha256 in hashes:
                items.append({"file_id": file_id, "status": "visual_unavailable"})
                continue
            hashes.add(candidate.file_sha256)
            try:
                # 同步宿主视觉在受限的当前串行任务之外运行；迟到仅返回数据。
                from .visual_worker import run_visual

                raw = await run_visual(
                    self.root, lambda path=path: asyncio.run(service._call_vision(path))
                )
                metadata = parse_visual_response(raw)
            except (asyncio.CancelledError, TimeoutError):
                raise
            except Exception:  # noqa: BLE001 - 视觉结果和异常不能出现在任务摘要
                items.append({"file_id": file_id, "status": "visual_unavailable"})
                continue
            with library_guard(self.root), StickerStore(data_dir=self.root) as store:
                guard()
                try:
                    fresh = validate_image_file(path, input_root)
                except (ValueError, OSError):
                    items.append({"file_id": file_id, "status": "rejected"})
                    continue
                if fresh != candidate:
                    items.append({"file_id": file_id, "status": "conflict"})
                    continue
                if metadata["is_sticker"]:
                    result = service._commit_sticker(
                        store, candidate, metadata, [], input_root=input_root
                    )
                else:
                    result = service._move_to_junk(store.paths, candidate, [])
                items.append({"file_id": file_id, **result})
        return {
            "items": items,
            "task_status": "succeeded"
            if all(x["status"] in {"created", "duplicate", "junk"} for x in items)
            else "partial",
        }

    async def reanalyze_targets(self, targets, *, guard=lambda: None, progress=lambda items: None):
        """后台重新分析提交前复核版本，保留期间人工编辑。"""
        import asyncio

        if not isinstance(targets, list) or not 1 <= len(targets) <= 50:
            raise StickerError("invalid_input")
        seen = set()
        for target in targets:
            if not isinstance(target, dict) or set(target) != {"sticker_id", "version"}:
                raise StickerError("invalid_input")
            _parse_id(target["sticker_id"])
            if target["sticker_id"] in seen:
                raise StickerError("invalid_input")
            seen.add(target["sticker_id"])
        items = _ProgressItems(progress, [{"sticker_id": x["sticker_id"]} for x in targets])
        for target in targets:
            guard()
            items.begin("sticker_id", target["sticker_id"])

            def execute(target=target):
                with StickerStore(data_dir=self.root) as store:
                    current = StickerMaintenanceService.item_version(store, target["sticker_id"])
                    if current is None:
                        return {"status": "not_found"}
                    if current != target["version"]:
                        return {"status": "conflict"}
                    service = StickerMaintenanceService(data_dir=self.root)
                    return asyncio.run(
                        service._reanalyze(
                            store,
                            target["sticker_id"],
                            guard=checked_guard,
                            expected_version=target["version"],
                        )
                    )

            import threading

            stopped = threading.Event()
            outer_guard = guard

            def checked_guard(stopped=stopped, outer_guard=outer_guard):
                if stopped.is_set():
                    raise StickerError("interrupted")
                outer_guard()

            try:
                from .visual_worker import run_visual

                result = await run_visual(self.root, execute)
            except (TimeoutError, asyncio.CancelledError):
                stopped.set()
                raise

            items.append({"sticker_id": target["sticker_id"], **result})
        return {
            "items": items,
            "task_status": "succeeded"
            if all(x["status"] == "reanalyzed" for x in items)
            else "partial",
        }


class _ProgressItems(list):
    """派发前记录不确定状态，每项确认后更新，异常退出不冒充未执行。"""

    def __init__(self, progress, targets):
        super().__init__({**target, "status": "not_started"} for target in targets)
        self.progress = progress
        self.progress(list(self))

    def begin(self, key, value):
        self.append({key: value, "status": "in_flight"})

    def append(self, item):
        key = "file_id" if "file_id" in item else "sticker_id"
        for index, previous in enumerate(self):
            if previous[key] == item[key]:
                self[index] = item
                break
        else:
            super().append(item)
        self.progress(list(self))
