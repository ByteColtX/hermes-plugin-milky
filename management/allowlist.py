"""执行经宿主命令分发的白名单管理，不实现任何命令权限策略。"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar, copy_context
from dataclasses import dataclass

from management.errors import ManagementError
from session.identity import validate_chat_key, validate_chat_rule

USAGE = (
    "usage: /milky allowlist list [--page <正整数>] | add [目标] | del [目标] "
    "(remove 等价于 del)；保存无法保证与 Web/人工修改完全原子"
)


@dataclass(frozen=True)
class Operation:
    """保存已完成语法校验的单次操作。"""

    verb: str
    target: str | None = None
    page: int = 1


def parse(raw_args: str) -> Operation:
    """接受固定纯文本参数；非法显式目标绝不回退当前来源。"""
    parts = raw_args.split()
    if len(parts) < 2 or parts[0].lower() != "allowlist":
        raise ValueError("invalid_input")
    verb = parts[1].lower()
    if verb == "remove":
        verb = "del"
    if verb in {"add", "del"} and len(parts) in {2, 3}:
        return Operation(verb, validate_chat_rule(parts[2]) if len(parts) == 3 else None)
    if verb == "list":
        if len(parts) == 2:
            return Operation(verb)
        if (
            len(parts) == 4
            and parts[2] == "--page"
            and parts[3].isascii()
            and parts[3].isdecimal()
            and 0 < len(parts[3]) <= 9
            and int(parts[3]) > 0
        ):
            return Operation(verb, page=int(parts[3]))
    raise ValueError("invalid_input")


def is_management_command(command) -> bool:
    """只按直接命令的完整语法决定白名单路由例外。"""
    if command is None or command.name != "milky" or command.text.split()[0].lower() != "/milky":
        return False
    try:
        parse(command.args)
    except (ValueError, TypeError):
        return False
    return True


@dataclass
class Invocation:
    """只关联操作来源和实例生命周期，不代表命令授权。"""

    owner: object
    chat_key: str
    epoch: int
    consumed: bool = False


current_invocation: ContextVar[Invocation | None] = ContextVar("milky_invocation", default=None)


class AllowlistManager:
    """由活动 adapter 拥有，串行准备、保存和发布完整规则。"""

    def __init__(self, policy, tracker, store, publish):
        self.policy = policy
        self.tracker = tracker
        self.store = store
        self._publish = publish
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()
        self.active = False
        self.epoch = 0

    def start(self):
        """开放当前生命周期的管理调用。"""
        self.epoch += 1
        self.active = True

    def stop(self):
        """立即失效调用关联，在任何后续等待之前关闭发布。"""
        self.active = False
        self.epoch += 1
        for task in self._tasks:
            if task is not asyncio.current_task():
                task.cancel()

    async def close(self):
        """等待已取消的所属管理操作。"""
        self.stop()
        tasks = tuple(task for task in self._tasks if task is not asyncio.current_task())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def invocation(self, chat_key):
        """为一次插件到宿主的命令交接建立来源关联。"""
        return Invocation(self, validate_chat_key(chat_key), self.epoch)

    def accepts(self, invocation):
        """拒绝已停止、过期或已消费的操作对象关联。"""
        if (
            not self.active
            or invocation is None
            or invocation.owner is not self
            or invocation.epoch != self.epoch
            or invocation.consumed
            or self.store is None
        ):
            return False
        is_current = getattr(self.store, "is_current", None)
        if callable(is_current) and not is_current():
            return False
        # 只读当前任务已经绑定的宿主会话变量，绝不调用带环境回退的读取器。
        bound = {var.name: value for var, value in copy_context().items()}
        return (
            bound.get("HERMES_SESSION_PLATFORM") == "milky"
            and bound.get("HERMES_SESSION_CHAT_ID") == invocation.chat_key
        )

    async def handle(self, operation, invocation):
        """宿主放行后先准备来源群，再读取名单及处理目标。"""
        if not self.accepts(invocation):
            return "unsupported: 无可信会话、profile 或活动实例"
        invocation.consumed = True
        task = asyncio.current_task()
        self._tasks.add(task)
        try:
            async with self._lock:
                if not self.active or invocation.epoch != self.epoch:
                    return "unsupported: 实例已停止"
                source = invocation.chat_key
                if source.startswith("group:"):
                    group_id = int(source.split(":")[1])
                    if not await self.tracker.prepare_group(group_id):
                        return "blocked: 来源群状态准备失败"
                    member, whole = self.tracker.gate_snapshot(group_id)
                    if member != "unmuted" or whole == "muted":
                        return "blocked: 来源群禁言"
                if not self.active:
                    return "unsupported: 实例已停止"
                snapshot = self.store.read()
                rules = snapshot["effective"].get("allowed_chats")
                if rules is None:
                    return "invalid_input: 持久白名单无效"
                rules = frozenset(validate_chat_rule(rule) for rule in rules)
                if operation.verb == "list":
                    return self._list(snapshot, rules, operation.page)
                target = operation.target or source
                candidate = rules | {target} if operation.verb == "add" else rules - {target}
                if candidate == rules:
                    suffix = (
                        "；持久与运行规则不同，需要重新加载" if rules != self.policy.rules else ""
                    )
                    return f"unchanged: 条目 {target} 未变化{suffix}"
                if not snapshot["writable"]["allowed_chats"]:
                    return "blocked: 白名单由宿主管理"
                version = self.policy.version
                if not await self.tracker.prepare_rules(candidate):
                    return "blocked: 目标群状态准备失败"
                if not self.active or invocation.epoch != self.epoch:
                    return "unsupported: 实例已停止"
                if version != self.policy.version:
                    return "conflict: 运行版本已变化"
                result = self.store.save(snapshot["version"], candidate)
                status = result["results"]["allowed_chats"]
                if status != "saved":
                    return f"{status if status != 'failed' else 'unknown'}: 持久化未确认，未应用"
                if not self.active or invocation.epoch != self.epoch:
                    return "saved: 运行未应用，需要重新加载"
                try:
                    self._publish(candidate)
                except Exception:  # noqa: BLE001 - 保存成功不得回滚或重试
                    return "saved: 运行未应用，需要重新加载"
                action = "已添加" if operation.verb == "add" else "已删除"
                suffix = ""
                if (
                    operation.verb == "add"
                    and target.startswith("group:")
                    and target != "group:*"
                    and self.tracker.is_muted(int(target.split(":")[1]))
                ):
                    suffix = "；目标仍受禁言限制"
                if (
                    operation.verb == "add"
                    and target == "group:*"
                    and any(
                        self.tracker.is_muted(group)
                        for group in getattr(self.tracker, "group_ids", ())
                    )
                ):
                    suffix = "；部分目标仍受禁言限制"
                return f"saved applied: 条目 {target} {action}{suffix}"
        except ManagementError as error:
            return f"{error.status}: 管理操作未应用"
        except Exception:  # noqa: BLE001 - 宿主异常不能泄漏原始配置或异常正文
            return "unknown: 配置或运行状态无法确认"
        finally:
            self._tasks.discard(task)

    def _list(self, snapshot, rules, page):
        """按两种规则的并集分页，每页至多展示五十个条目。"""
        entries = sorted(rules | self.policy.rules)
        pages = max(1, (len(entries) + 49) // 50)
        if page > pages:
            return "invalid_input: 页码超出范围"
        lines = [
            f"白名单 {page}/{pages}；来源 {snapshot['sources']['allowed_chats']}",
            f"持久/运行{'一致' if rules == self.policy.rules else '不同，需要重新加载'}",
        ]
        if not rules:
            lines.append("持久名单为空：阻止全部普通入站")
        if not self.policy.rules:
            lines.append("运行名单为空：阻止全部普通入站")
        for rule in entries[(page - 1) * 50 : page * 50]:
            lines.append(
                f"{rule} 持久={'是' if rule in rules else '否'} 运行={'是' if rule in self.policy.rules else '否'}"
            )
        return "\n".join(lines)
