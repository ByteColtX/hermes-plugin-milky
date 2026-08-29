"""有界、线程安全的 TTL message dedup。"""

from __future__ import annotations

import math
import time
from collections import OrderedDict
from collections.abc import Callable
from threading import Lock


class TtlDeduplicator:
    """在进程内以固定 TTL 和容量抑制重复 message ID。"""

    def __init__(
        self,
        ttl_seconds: float = 300.0,
        max_entries: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
        *,
        ttl: float | None = None,
        max_size: int | None = None,
    ) -> None:
        if ttl is not None:
            ttl_seconds = ttl
        if max_size is not None:
            max_entries = max_size
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)):
            raise TypeError("ttl_seconds must be a finite non-negative number")
        if not math.isfinite(ttl_seconds) or ttl_seconds < 0:
            raise ValueError("ttl_seconds must be a finite non-negative number")
        if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries < 0:
            raise ValueError("max_entries must be a non-negative integer")
        self._ttl_seconds = float(ttl_seconds)
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, float] = OrderedDict()
        self._lock = Lock()

    @property
    def size(self) -> int:
        """返回当前未过期条目数量。"""

        with self._lock:
            self._purge(self._clock())
            return len(self._entries)

    def check_and_mark(self, key: str | None) -> bool:
        """原子检查并记录 key，返回是否已在 TTL 窗口内见过。"""

        if key is None:
            return False
        if not isinstance(key, str) or not key:
            raise ValueError("dedup key must be a non-empty string")
        now = self._clock()
        with self._lock:
            self._purge(now)
            seen_at = self._entries.get(key)
            if seen_at is not None:
                if now < seen_at or now - seen_at < self._ttl_seconds:
                    return True
                del self._entries[key]
            if self._max_entries == 0:
                return False
            while len(self._entries) >= self._max_entries:
                self._entries.popitem(last=False)
            self._entries[key] = now
            return False

    def is_duplicate(self, key: str | None) -> bool:
        """只读检查 key 是否仍在 TTL 窗口内，不插入新 key。"""

        if key is None:
            return False
        if not isinstance(key, str) or not key:
            raise ValueError("dedup key must be a non-empty string")
        now = self._clock()
        with self._lock:
            self._purge(now)
            seen_at = self._entries.get(key)
            if seen_at is None:
                return False
            return now < seen_at or now - seen_at < self._ttl_seconds

    def clear(self) -> None:
        """清空进程内去重状态。"""

        with self._lock:
            self._entries.clear()

    def _purge(self, now: float) -> None:
        expired = [
            key
            for key, seen_at in self._entries.items()
            if now >= seen_at and now - seen_at >= self._ttl_seconds
        ]
        for key in expired:
            self._entries.pop(key, None)


__all__ = ["TtlDeduplicator"]
