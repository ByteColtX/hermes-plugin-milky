"""按图库协调不同进程的短提交和本地文件读取。"""

from __future__ import annotations

import os
import threading
import time
import weakref
from contextlib import contextmanager
from pathlib import Path

from .errors import StickerStorageError

_LOCKS = weakref.WeakValueDictionary()
_REGISTRY_LOCK = threading.Lock()
_LOCAL = threading.local()


@contextmanager
def library_guard(root: Path, *, timeout: float = 5.0):
    """获得有界跨进程保护；调用者不得在保护内等待视觉或网络。"""
    try:
        import fcntl
    except ImportError:
        raise StickerStorageError("coordination unsupported") from None
    root = Path(root).resolve()
    key = str(root)
    with _REGISTRY_LOCK:
        local_lock = _LOCKS.setdefault(key, threading.RLock())
    if not local_lock.acquire(timeout=timeout):
        raise StickerStorageError("coordination busy")
    held = getattr(_LOCAL, "held", None)
    if held is None:
        held = _LOCAL.held = set()
    descriptor = None
    try:
        if key in held:
            yield
            return
        # 对目录本身加锁，使只读浏览不会创建锁文件或缺失目录。
        descriptor = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise StickerStorageError("coordination busy") from None
                time.sleep(0.01)
        held.add(key)
        try:
            yield
        finally:
            held.remove(key)
    except OSError:
        raise StickerStorageError("coordination unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        local_lock.release()
