"""为不可立即取消的同步视觉保留有界执行名额。"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import os
import threading
from pathlib import Path

from .errors import StickerError
from .maintenance import MAX_CONCURRENCY

_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENCY)


async def run_visual(root: Path, operation, *, timeout: float = 120):
    """取消等待不会释放实际仍在执行的名额，跨进程锁限制同库并发。"""
    import fcntl

    if not _SLOTS.acquire(blocking=False):
        raise StickerError("busy")
    descriptor = None
    try:
        root.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(root / ".dashboard-visual.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise StickerError("busy") from None
        future = concurrent.futures.Future()
        owned_descriptor = descriptor
        context = contextvars.copy_context()

        def execute():
            try:
                future.set_result(context.run(operation))
            except BaseException as error:  # noqa: BLE001 - 在线程边界转交异常给等待者
                future.set_exception(error)
            finally:
                os.close(owned_descriptor)
                _SLOTS.release()

        # 宿主同步调用可能不响应取消；固定名额和守护线程避免无限积累或阻塞关闭。
        thread = threading.Thread(target=execute, daemon=True, name="milky-dashboard-vision")
        thread.start()
        descriptor = None
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        _SLOTS.release()
        raise
    wrapped = asyncio.wrap_future(future)
    # 等待取消只取消包装任务，实际线程仍保留名额直到释放。
    wrapped.add_done_callback(lambda result: result.exception() if not result.cancelled() else None)
    return await asyncio.wait_for(asyncio.shield(wrapped), timeout)
