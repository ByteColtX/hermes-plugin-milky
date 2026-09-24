"""独立 Web 上传批次、实际字节配额和显式候选归属。"""

from __future__ import annotations

import contextlib
import json
import secrets
import shutil
import sqlite3
import time
from pathlib import Path

from stickers.coordination import library_guard
from stickers.validation import MAX_IMAGE_BYTES, validate_image_file

from .host import ManagementError

BATCH_BYTES = 100 * 1024 * 1024
QUOTA = 500 * 1024 * 1024
RETENTION = 7 * 86400


class UploadStore:
    """输入仅通过创建的文件标识解析，不接受客户端路径或 URL。"""

    def __init__(self, root: Path, *, clock=time.time):
        self.root = Path(root) / "web-uploads"
        self.clock = clock

    def _batch(self, batch_id):
        if (
            not isinstance(batch_id, str)
            or len(batch_id) != 48
            or any(c not in "0123456789abcdef" for c in batch_id)
        ):
            raise ManagementError("invalid_input")
        path = self.root / batch_id
        if path.is_symlink() or not path.is_dir():
            raise ManagementError("not_found")
        return path

    def begin(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with library_guard(self.root):
            if len(list(self.root.iterdir())) >= 1000:
                raise ManagementError("busy")
            batch_id = secrets.token_hex(24)
            path = self.root / batch_id
            path.mkdir(mode=0o700)
            self._save(
                path,
                {
                    "batch_id": batch_id,
                    "created": self.clock(),
                    "files": [],
                    "complete": False,
                    "active": False,
                },
            )
        return batch_id

    @staticmethod
    def _save(path, metadata):
        temporary = path / "metadata.tmp"
        temporary.write_text(json.dumps(metadata), encoding="utf-8")
        temporary.replace(path / "metadata.json")

    def _read(self, path):
        try:
            return json.loads((path / "metadata.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ManagementError("storage_error") from None

    async def receive(self, files):
        """逐块接收上传对象，断线或超限立即删除不完整批次。"""
        if not 1 <= len(files) <= 50:
            raise ManagementError("invalid_input")
        batch_id = self.begin()
        path = self._batch(batch_id)
        metadata = self._read(path)
        total = 0
        try:
            for upload in files:
                suffix = Path(upload.filename or "").suffix.lower()
                if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                    raise ManagementError("invalid_input")
                file_id = secrets.token_hex(24)
                filename = file_id + suffix
                size = 0
                with (path / filename).open("xb") as target:
                    while chunk := await upload.read(64 * 1024):
                        size += len(chunk)
                        total += len(chunk)
                        if size > MAX_IMAGE_BYTES or total > BATCH_BYTES:
                            raise ManagementError("too_large")
                        with library_guard(self.root):
                            current = sum(
                                p.stat().st_size
                                for p in self.root.glob("*/*")
                                if p.is_file() and p.suffix != ".json" and not p.is_symlink()
                            )
                            if current + len(chunk) > QUOTA:
                                raise ManagementError("quota_exceeded")
                            target.write(chunk)
                            target.flush()
                try:
                    candidate = validate_image_file(path / filename, path)
                    status = "ready"
                except (ValueError, OSError):
                    candidate = None
                    status = "rejected"
                metadata["files"].append(
                    {
                        "file_id": file_id,
                        "name": filename,
                        "size": size,
                        "status": status,
                        "sha256": candidate.file_sha256 if candidate else None,
                    }
                )
            metadata["complete"] = True
            with library_guard(self.root):
                self._save(path, metadata)
            return {
                "batch_id": batch_id,
                "file_ids": [x["file_id"] for x in metadata["files"] if x["status"] == "ready"],
                "items": [
                    {"file_id": x["file_id"], "status": x["status"]} for x in metadata["files"]
                ],
            }
        except BaseException:
            with library_guard(self.root):
                shutil.rmtree(path)
            raise
        finally:
            for upload in files:
                await upload.close()

    def candidates(self, batch_id, file_ids):
        """只解析完整批次中明确提交的去重对象，不扫描 inbox。"""
        if (
            not isinstance(file_ids, list)
            or not 1 <= len(file_ids) <= 50
            or not all(isinstance(x, str) for x in file_ids)
            or len(set(file_ids)) != len(file_ids)
        ):
            raise ManagementError("invalid_input")
        path = self._batch(batch_id)
        metadata = self._read(path)
        if not metadata["complete"]:
            raise ManagementError("invalid_input")
        selected = []
        by_id = {x["file_id"]: x for x in metadata["files"]}
        for file_id in file_ids:
            entry = by_id.get(file_id)
            if entry is None or entry["status"] != "ready":
                raise ManagementError("not_found")
            selected.append((file_id, path / entry["name"]))
        return path, selected

    def list_batches(self):
        """只读列出有限的完整批次及仍保留的候选，刷新后可明确重试。"""
        if not self.root.exists():
            return {"items": []}
        items = []
        with library_guard(self.root.parent), library_guard(self.root):
            for path in sorted(self.root.iterdir(), key=lambda value: value.name):
                if path.is_symlink() or not path.is_dir():
                    continue
                metadata = self._read(path)
                if not metadata.get("complete"):
                    continue
                remaining = [
                    {"file_id": entry["file_id"], "status": entry["status"]}
                    for entry in metadata["files"]
                    if (path / entry["name"]).is_file()
                ]
                items.append(
                    {
                        "batch_id": metadata["batch_id"],
                        "created_at": metadata["created"],
                        "active": self._active(path.name),
                        "items": remaining,
                        "file_ids": [
                            entry["file_id"] for entry in remaining if entry["status"] == "ready"
                        ],
                    }
                )
        return {"items": sorted(items, key=lambda value: value["created_at"], reverse=True)[:100]}

    def reference(self, batch_id, active):
        """活动任务引用冻结输入，避免删除或期限回收。"""
        with library_guard(self.root):
            path = self._batch(batch_id)
            metadata = self._read(path)
            if active and metadata["active"]:
                raise ManagementError("busy")
            metadata["active"] = active
            self._save(path, metadata)

    def discard(self, batch_id):
        with library_guard(self.root.parent), library_guard(self.root):
            path = self._batch(batch_id)
            metadata = self._read(path)
            if metadata["active"] or self._active(batch_id):
                raise ManagementError("busy")
            shutil.rmtree(path)
        return {"status": "discarded"}

    def reclaim(self):
        if not self.root.exists():
            return {"removed": 0}
        removed = 0
        with library_guard(self.root.parent), library_guard(self.root):
            for path in self.root.iterdir():
                if path.is_symlink() or not path.is_dir():
                    continue
                metadata = self._read(path)
                if (
                    not metadata["active"]
                    and not self._active(path.name)
                    and metadata["created"] < self.clock() - RETENTION
                ):
                    shutil.rmtree(path)
                    removed += 1
        return {"removed": removed}

    def _active(self, batch_id):
        """持久排队或运行任务也是活动引用，重启后保持同一归属。"""
        # 取消或超时可先结束任务，但同步视觉仍可能读取输入；其内核锁随线程结束释放。
        import fcntl

        visual_lock = self.root.parent / ".dashboard-visual.lock"
        try:
            descriptor = visual_lock.open("rb")
        except FileNotFoundError:
            descriptor = None
        if descriptor is not None:
            with descriptor:
                try:
                    fcntl.flock(descriptor.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return True
                finally:
                    fcntl.flock(descriptor.fileno(), fcntl.LOCK_UN)
        database = self.root.parent / "dashboard-jobs.db"
        if not database.exists():
            return False
        with contextlib.closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM jobs WHERE operation='import' AND status IN ('queued','running') AND json_extract(payload,'$.batch_id')=? LIMIT 1",
                    (batch_id,),
                ).fetchone()
                is not None
            )

    async def receive_stream(self, request):
        """直接解析流到受控批次，避免 multipart 在全局临时目录先落盘。"""
        try:
            from python_multipart.multipart import MultipartParser, parse_options_header
        except ImportError:
            raise ManagementError("unsupported") from None

        media_type, options = parse_options_header(request.headers.get("content-type", ""))
        boundary = options.get(b"boundary")
        if media_type != b"multipart/form-data" or not boundary or len(boundary) > 200:
            raise ManagementError("invalid_input")
        batch_id = self.begin()
        path = self._batch(batch_id)
        metadata = self._read(path)
        state = {"target": None, "total": 0, "received": 0, "ended": False}

        def begin_part():
            if len(metadata["files"]) >= 50:
                raise ManagementError("too_large")
            state.update(headers={}, header=bytearray(), value=bytearray(), size=0)

        def header_field(data, start, end):
            state["header"].extend(data[start:end])
            if len(state["header"]) > 1024:
                raise ManagementError("invalid_input")

        def header_value(data, start, end):
            state["value"].extend(data[start:end])
            if len(state["value"]) > 8192:
                raise ManagementError("invalid_input")

        def header_end():
            if len(state["headers"]) >= 10:
                raise ManagementError("invalid_input")
            state["headers"][bytes(state["header"]).lower()] = bytes(state["value"])
            state["header"].clear()
            state["value"].clear()

        def headers_finished():
            _, fields = parse_options_header(state["headers"].get(b"content-disposition", b""))
            if fields.get(b"name") != b"files" or b"filename" not in fields:
                raise ManagementError("invalid_input")
            suffix = Path(fields[b"filename"].decode("utf-8", errors="replace")).suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                raise ManagementError("invalid_input")
            file_id = secrets.token_hex(24)
            state["entry"] = {"file_id": file_id, "name": file_id + suffix}
            state["target"] = (path / state["entry"]["name"]).open("xb")

        def part_data(data, start, end):
            count = end - start
            state["size"] += count
            state["total"] += count
            if state["size"] > MAX_IMAGE_BYTES or state["total"] > BATCH_BYTES:
                raise ManagementError("too_large")
            if state["target"] is None:
                raise ManagementError("invalid_input")
            with library_guard(self.root):
                current = sum(
                    p.stat().st_size
                    for p in self.root.glob("*/*")
                    if p.is_file() and p.suffix != ".json" and not p.is_symlink()
                )
                if current + count > QUOTA:
                    raise ManagementError("quota_exceeded")
                state["target"].write(data[start:end])
                state["target"].flush()

        def end_part():
            target = state["target"]
            if target is None:
                raise ManagementError("invalid_input")
            target.close()
            state["target"] = None
            entry = state["entry"]
            try:
                candidate = validate_image_file(path / entry["name"], path)
                status = "ready"
            except (ValueError, OSError):
                candidate, status = None, "rejected"
            metadata["files"].append(
                {
                    **entry,
                    "size": state["size"],
                    "status": status,
                    "sha256": candidate.file_sha256 if candidate else None,
                }
            )

        parser = MultipartParser(
            boundary,
            {
                "on_part_begin": begin_part,
                "on_header_field": header_field,
                "on_header_value": header_value,
                "on_header_end": header_end,
                "on_headers_finished": headers_finished,
                "on_part_data": part_data,
                "on_part_end": end_part,
                "on_end": lambda: state.update(ended=True),
            },
        )
        try:
            async for chunk in request.stream():
                state["received"] += len(chunk)
                if state["received"] > BATCH_BYTES + 1024 * 1024:
                    raise ManagementError("too_large")
                # 解析和本地写入离开请求循环，每次只派发一个有界块。
                import asyncio

                for start in range(0, len(chunk), 64 * 1024):
                    pending = asyncio.create_task(
                        asyncio.to_thread(parser.write, chunk[start : start + 64 * 1024])
                    )
                    try:
                        await asyncio.shield(pending)
                    except asyncio.CancelledError:
                        # 当前块结束后再回收文件，避免后台写入与关闭交错。
                        try:
                            await pending
                        finally:
                            raise
            parser.finalize()
            if not state["ended"] or not metadata["files"]:
                raise ManagementError("invalid_input")
            metadata["complete"] = True
            with library_guard(self.root):
                self._save(path, metadata)
            return {
                "batch_id": batch_id,
                "file_ids": [x["file_id"] for x in metadata["files"] if x["status"] == "ready"],
                "items": [
                    {"file_id": x["file_id"], "status": x["status"]} for x in metadata["files"]
                ],
            }
        except BaseException:
            if state["target"] is not None:
                state["target"].close()
            with library_guard(self.root):
                shutil.rmtree(path)
            raise
