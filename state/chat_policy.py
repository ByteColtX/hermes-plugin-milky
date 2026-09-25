"""保存活动实例的完整入站策略及逐会话撤销代次。"""

from collections.abc import Iterable

from session.identity import validate_chat_key, validate_chat_rule


def matches(rules: frozenset[str], chat_key: str) -> bool:
    """按完整命名空间判断授权，空集合拒绝全部。"""
    try:
        key = validate_chat_key(chat_key)
    except (TypeError, ValueError):
        return False
    return key in rules or key.split(":", 1)[0] + ":*" in rules


class ChatPolicy:
    """由单个事件循环发布策略；不持有正文或宿主任务。"""

    def __init__(self, rules: Iterable[str] = ()) -> None:
        self.rules = frozenset(validate_chat_rule(rule) for rule in rules)
        self.version = 0
        self._generations: dict[str, int] = {}

    def allows(self, chat_key: str) -> bool:
        """返回当前授权结果。"""
        return matches(self.rules, chat_key)

    def generation(self, chat_key: str) -> int:
        """登记需要撤销保护的会话，返回当前代次。"""
        key = validate_chat_key(chat_key)
        return self._generations.setdefault(key, 0)

    def publish(self, rules: Iterable[str]) -> tuple[str, ...]:
        """无等待地替换完整快照，仅实际失去授权时更新代次。"""
        candidate = frozenset(validate_chat_rule(rule) for rule in rules)
        if candidate == self.rules:
            return ()
        revoked = tuple(
            key
            for key in self._generations
            if matches(self.rules, key) and not matches(candidate, key)
        )
        for key in revoked:
            self._generations[key] += 1
        self.rules = candidate
        self.version += 1
        return revoked
