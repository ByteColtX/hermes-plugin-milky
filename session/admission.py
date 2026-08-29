"""实现按 chat 隔离的短暂异步 admission 边界。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from itertools import count
from threading import Lock

from .identity import validate_chat_key


@dataclass(frozen=True, slots=True)
class AdmissionTicket:
    """表示一次进入 admission 的 chat 和 ingress 顺序。"""

    chat_key: str
    ingress_sequence: int


class _AdmissionLease:
    """持有单个 chat 的短暂异步锁，不包含 Agent 执行。"""

    def __init__(self, lock: asyncio.Lock, ticket: AdmissionTicket) -> None:
        self._lock = lock
        self.ticket = ticket
        self._entered = False

    async def __aenter__(self) -> AdmissionTicket:
        """等待当前 chat 的前序临界区结束并返回 ticket。"""

        if self._entered:
            raise RuntimeError("admission lease cannot be entered twice")
        await self._lock.acquire()
        self._entered = True
        return self.ticket

    async def __aexit__(self, _exc_type, _exc_value, _traceback) -> None:
        """无论临界区是否异常都释放当前 chat 的锁。"""

        if self._entered:
            self._entered = False
            self._lock.release()


class ChatAdmissionCoordinator:
    """为每个 canonical chat 提供按 ingress 顺序的短暂锁。"""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._sequence = count(1)
        self._state_lock = Lock()

    def admit(self, chat_key: str) -> _AdmissionLease:
        """登记一次 ingress，并返回可异步进入的 admission lease。"""

        normalized_key = validate_chat_key(chat_key)
        with self._state_lock:
            lock = self._locks.get(normalized_key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[normalized_key] = lock
            sequence = next(self._sequence)
        return _AdmissionLease(lock, AdmissionTicket(normalized_key, sequence))

    def acquire(self, chat_key: str) -> _AdmissionLease:
        """提供与 ``admit`` 等价的语义化入口。"""

        return self.admit(chat_key)


__all__ = ["AdmissionTicket", "ChatAdmissionCoordinator"]
