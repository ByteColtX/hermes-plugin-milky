"""每 profile 有界持久任务、重复提交保护和独立执行所有权。"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from stickers.errors import StickerError

from .host import ManagementError
from .payloads import validate

RETENTION = 7 * 86400
OPERATIONS = {"import", "edit", "delete", "reanalyze", "cleanup", "reindex", "reclaim_uploads"}
TERMINAL = {"succeeded", "partial", "failed", "cancelled", "interrupted"}


class JobManager:
    """按 profile 持久化目标；工作只由显式提交启动。"""

    def __init__(self, root: Path, *, clock=time.time):
        self.root = Path(root)
        self.clock = clock
        self.owner = secrets.token_hex(16)
        self.worker = None
        self.closed = False
        self.cancelled = set()

    @contextmanager
    def connect(self):
        """只在显式任务/请求标识写入时建立存储。"""
        self.root.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.root / "dashboard-jobs.db", timeout=5)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY, operation TEXT NOT NULL, expires REAL NOT NULL,
                fingerprint TEXT, task_id TEXT);
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, operation TEXT NOT NULL, payload TEXT NOT NULL,
                status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                owner TEXT, pid INTEGER, cancel_requested INTEGER NOT NULL DEFAULT 0, result TEXT NOT NULL DEFAULT '{}');
        """)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _prune(self, conn):
        """活动记录不淘汰；旧标识的时间戳确保删除后仍返回 expired。"""
        now = self.clock()
        conn.execute("DELETE FROM requests WHERE expires < ?", (now,))
        placeholders = ",".join("?" for _ in TERMINAL)
        conn.execute(
            f"DELETE FROM jobs WHERE status IN ({placeholders}) AND updated < ?",
            (*sorted(TERMINAL), now - RETENTION),
        )
        conn.execute(
            f"DELETE FROM jobs WHERE id IN (SELECT id FROM jobs WHERE status IN ({placeholders}) ORDER BY updated DESC, id DESC LIMIT -1 OFFSET 1000)",
            tuple(sorted(TERMINAL)),
        )
        conn.execute(
            "DELETE FROM requests WHERE task_id IS NOT NULL AND task_id NOT IN (SELECT id FROM jobs)"
        )

    def issue(self, operation):
        """有界签发；标识仅用于去重，不能代替宿主认证。"""
        if self.closed or not isinstance(operation, str) or operation not in OPERATIONS:
            raise ManagementError("unsupported")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._prune(conn)
            if conn.execute("SELECT count(*) FROM requests").fetchone()[0] >= 2000:
                raise ManagementError("busy")
            expires = self.clock() + RETENTION
            request_id = f"{int(expires)}.{secrets.token_hex(24)}"
            conn.execute(
                "INSERT INTO requests(id, operation, expires) VALUES (?, ?, ?)",
                (request_id, operation, expires),
            )
        return {"request_id": request_id, "expires_at": expires}

    def submit(self, request_id, operation, payload):
        """同一标识和内容只接受一次，未知标识不会成为新请求。"""
        if self.closed:
            raise ManagementError("interrupted")
        validate(operation, payload)
        if not isinstance(request_id, str) or len(request_id) > 100:
            raise ManagementError("invalid_input")
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode()) > 100_000:
            raise ManagementError("invalid_input")
        fingerprint = hashlib.sha256((operation + encoded).encode()).hexdigest()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._prune(conn)
            record = conn.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if record is None or record["expires"] < self.clock():
                raise ManagementError("expired")
            if record["operation"] != operation or (
                record["fingerprint"] and record["fingerprint"] != fingerprint
            ):
                raise ManagementError("conflict")
            if record["task_id"]:
                task_id = record["task_id"]
            else:
                if (
                    conn.execute("SELECT count(*) FROM jobs WHERE status='queued'").fetchone()[0]
                    >= 10
                ):
                    raise ManagementError("busy")
                task_id = secrets.token_urlsafe(24)
                now = self.clock()
                conn.execute(
                    "INSERT INTO jobs(id,operation,payload,status,created,updated,owner,pid) VALUES (?,?,?,'queued',?,?,?,?)",
                    (task_id, operation, encoded, now, now, self.owner, os.getpid()),
                )
                conn.execute(
                    "UPDATE requests SET task_id=?,fingerprint=? WHERE id=?",
                    (task_id, fingerprint, request_id),
                )
        return {"task_id": task_id}

    def list(self):
        """只读查询不创建数据库；限制响应记录数量。"""
        database = self.root / "dashboard-jobs.db"
        if not database.exists():
            return {"items": []}
        with contextlib.closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id,operation,status,created,updated,result FROM jobs ORDER BY created DESC,id DESC LIMIT 100"
            ).fetchall()
        return {
            "items": [
                {
                    "task_id": row["id"],
                    "operation": row["operation"],
                    "status": row["status"],
                    "created_at": row["created"],
                    "updated_at": row["updated"],
                    **{
                        key: value
                        for key, value in json.loads(row["result"]).items()
                        if key != "status"
                    },
                    "operation_status": json.loads(row["result"]).get("status"),
                }
                for row in rows
            ]
        }

    def cancel(self, task_id):
        """保留已完成项，只阻止之后派发和提交。"""
        from stickers.coordination import library_guard

        if not self.root.exists():
            raise ManagementError("not_found")
        with library_guard(self.root):
            return self._cancel_locked(task_id)

    def _cancel_locked(self, task_id):
        """在提交保护内确认取消，已完成提交由任务继续保留。"""
        with self.connect() as conn:
            row = conn.execute("SELECT status FROM jobs WHERE id=?", (task_id,)).fetchone()
            if not row:
                raise ManagementError("not_found")
            if row["status"] == "queued":
                conn.execute(
                    "UPDATE jobs SET status='cancelled',updated=? WHERE id=?",
                    (self.clock(), task_id),
                )
            elif row["status"] == "running":
                # 在途执行仍占运行名额，直到执行层确认结束。
                conn.execute(
                    "UPDATE jobs SET cancel_requested=1,updated=? WHERE id=?",
                    (self.clock(), task_id),
                )
                self.cancelled.add(task_id)
        return {"status": "cancelled" if row["status"] not in TERMINAL else row["status"]}

    def guard(self, task_id, enabled):
        """每次提交前重新确认任务所有权、取消和插件启用状态。"""
        if self.closed or task_id in self.cancelled or not enabled():
            raise ManagementError("cancelled")
        with self.connect() as conn:
            row = conn.execute(
                "SELECT status,owner,cancel_requested FROM jobs WHERE id=?", (task_id,)
            ).fetchone()
        if (
            not row
            or row["status"] != "running"
            or row["owner"] != self.owner
            or row["cancel_requested"]
        ):
            raise ManagementError("cancelled")

    def recover(self):
        """仅将不存在执行进程的活动任务标为 interrupted，不自动重放。"""
        if not (self.root / "dashboard-jobs.db").exists():
            return
        with self.connect() as conn:
            self._prune(conn)
            for row in conn.execute(
                "SELECT id,pid,result FROM jobs WHERE status IN ('running','queued')"
            ).fetchall():
                try:
                    os.kill(row["pid"], 0)
                except ProcessLookupError:
                    conn.execute(
                        "UPDATE jobs SET status='interrupted',updated=?,result=? WHERE id=?",
                        (
                            self.clock(),
                            json.dumps(_interrupted_items(json.loads(row["result"]))),
                            row["id"],
                        ),
                    )
                except (PermissionError, TypeError):
                    pass

    def start(self, execute, enabled):
        """仅在显式提交之后启动一个宿主事件循环任务。"""
        if self.worker is None or self.worker.done():
            self.worker = asyncio.create_task(self._run(execute, enabled))

    async def _run(self, execute, enabled):
        while not self.closed:
            with self.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                occupied = conn.execute("SELECT 1 FROM jobs WHERE status='running'").fetchone()
                row = conn.execute(
                    "SELECT * FROM jobs WHERE status='queued' AND owner=? ORDER BY created,id LIMIT 1",
                    (self.owner,),
                ).fetchone()
                if not row:
                    return
                if occupied:
                    row = None
                else:
                    conn.execute(
                        "UPDATE jobs SET status='running',owner=?,pid=?,updated=? WHERE id=?",
                        (self.owner, os.getpid(), self.clock(), row["id"]),
                    )
                    task_id = row["id"]
            if row is None:
                await asyncio.sleep(0.2)
                self.recover()
                continue
            try:
                self.guard(task_id, enabled)

                def boundary(task_id=task_id):
                    self.guard(task_id, enabled)

                boundary.progress = lambda items, task_id=task_id: self.checkpoint(task_id, items)
                result = await execute(row["operation"], json.loads(row["payload"]), boundary)
                status = result.pop("task_status", "succeeded")
                if status not in TERMINAL:
                    status = "failed"
            except asyncio.CancelledError:
                result, status = {}, "interrupted"
            except TimeoutError:
                result, status = {"reason": "visual_unknown"}, "interrupted"
            except StickerError as error:
                result, status = {"reason": error.classification}, "failed"
            except ManagementError as error:
                result, status = (
                    {"reason": error.status},
                    "cancelled" if error.status == "cancelled" else "failed",
                )
            except Exception:  # noqa: BLE001 - 不持久化异常原文
                result, status = {"reason": "storage_error"}, "failed"
            with self.connect() as conn:
                previous = conn.execute("SELECT result FROM jobs WHERE id=?", (task_id,)).fetchone()
                result = {**json.loads(previous[0]), **result} if previous else result
                if status in {"cancelled", "interrupted", "failed"}:
                    result = _interrupted_items(result)
                conn.execute(
                    "UPDATE jobs SET status=CASE WHEN cancel_requested=1 THEN 'cancelled' ELSE ? END,result=?,updated=? WHERE id=? AND owner=?",
                    (
                        status,
                        json.dumps(result, ensure_ascii=False),
                        self.clock(),
                        task_id,
                        self.owner,
                    ),
                )
                self._prune(conn)
            self.cancelled.discard(task_id)
            if self.closed:
                return

    def checkpoint(self, task_id, items):
        """每项提交后保留有限结果；取消不会清空已经完成的项。"""
        with self.connect() as conn:
            conn.execute(
                "UPDATE jobs SET result=?,updated=? WHERE id=? AND owner=? AND status='running'",
                (
                    json.dumps({"items": items}, ensure_ascii=False),
                    self.clock(),
                    task_id,
                    self.owner,
                ),
            )

    async def close(self):
        """停止新派发，等待可取消任务，关闭后 guard 拒绝迟到提交。"""
        from stickers.coordination import library_guard

        def stop_commits():
            if self.root.exists():
                with library_guard(self.root):
                    self.closed = True
            else:
                self.closed = True

        await asyncio.to_thread(stop_commits)
        if self.worker and not self.worker.done():
            self.worker.cancel()
            try:
                await asyncio.wait_for(self.worker, timeout=2)
            except (TimeoutError, asyncio.CancelledError):
                pass
        if (self.root / "dashboard-jobs.db").exists():
            with self.connect() as conn:
                conn.execute(
                    "UPDATE jobs SET status='interrupted',updated=? WHERE owner=? AND status='queued'",
                    (self.clock(), self.owner),
                )


def _interrupted_items(result):
    """在途项只能标 unknown，未派发项保留明确未执行结果。"""
    if "items" in result:
        result["items"] = [
            {
                **item,
                "status": {"in_flight": "unknown", "not_started": "not_executed"}.get(
                    item.get("status"), item.get("status")
                ),
            }
            for item in result["items"]
        ]
    return result
