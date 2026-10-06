"""斜杠命令所需的活动实例归属与代次。"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class BindingHandle:
    """不透明的实例绑定关联；调用方不得依赖其内部字段。"""

    _instance: object
    _generation: int


@dataclass
class _Binding:
    instance: object
    generation: int
    status_provider: object | None = None
    client: object | None = None
    manager: object | None = None
    ready: bool = False


class CommandBindingRegistry:
    """集中管理命令依赖的实例归属，隐藏各用途记录。"""

    def __init__(self) -> None:
        self._bindings: list[_Binding] = []
        self._revision = 0
        self._lock = RLock()

    @property
    def revision(self) -> int:
        """返回可用于等待后复核的运行代次。"""

        with self._lock:
            return self._revision

    def register(self, instance: object, *, status_provider: object | None = None) -> BindingHandle:
        """登记一个实例并返回不透明关联。"""

        if instance is None:
            raise TypeError("instance is required")
        with self._lock:
            for binding in self._bindings:
                if binding.instance is instance:
                    if status_provider is not None:
                        binding.status_provider = status_provider
                    self._revision += 1
                    return BindingHandle(instance, binding.generation)
            generation = self._revision + 1
            self._bindings.append(_Binding(instance, generation, status_provider=status_provider))
            self._revision += 1
            return BindingHandle(instance, generation)

    def mark_ready(
        self,
        handle: BindingHandle,
        *,
        client: object | None = None,
        manager: object | None = None,
    ) -> bool:
        """发布同步完成后的协议与管理依赖。"""

        with self._lock:
            binding = self._find(handle)
            if binding is None:
                return False
            if client is not None:
                binding.client = client
            if manager is not None:
                binding.manager = manager
            binding.ready = True
            self._revision += 1
            return True

    def revoke(self, handle: BindingHandle) -> bool:
        """撤销一个实例及其所有依赖，不影响其他实例。"""

        with self._lock:
            for index, binding in enumerate(self._bindings):
                if (
                    binding.instance is handle._instance
                    and binding.generation == handle._generation
                ):
                    self._bindings.pop(index)
                    self._revision += 1
                    return True
            return False

    def select_client(self) -> object | None:
        """仅在唯一 ready 实例时返回协议 client。"""

        with self._lock:
            values = [
                binding.client
                for binding in self._bindings
                if binding.ready and binding.client is not None
            ]
            return values[0] if len(values) == 1 else None

    def select_manager(self) -> object | None:
        """仅在唯一 ready 实例时返回白名单管理者。"""

        with self._lock:
            values = [
                binding.manager
                for binding in self._bindings
                if binding.ready and binding.manager is not None
            ]
            return values[0] if len(values) == 1 else None

    def select_status_provider(self) -> tuple[object | None, int]:
        """返回唯一本地状态观察者及当前代次。"""

        with self._lock:
            values = [
                binding.status_provider
                for binding in self._bindings
                if binding.status_provider is not None
            ]
            return (values[0] if len(values) == 1 else None), self._revision

    def active_client_count(self) -> int:
        """返回已发布协议 client 的数量。"""

        with self._lock:
            return sum(
                1 for binding in self._bindings if binding.ready and binding.client is not None
            )

    def _find(self, handle: BindingHandle) -> _Binding | None:
        if not isinstance(handle, BindingHandle):
            return None
        for binding in self._bindings:
            if binding.instance is handle._instance and binding.generation == handle._generation:
                return binding
        return None
