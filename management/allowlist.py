"""执行经宿主命令分发的白名单管理，不实现任何命令权限策略。"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar, copy_context
from dataclasses import dataclass

from management.errors import ManagementError
from session.identity import validate_chat_key, validate_chat_rule

USAGE = (
    "指令格式不正确\n\n"
    "查看白名单\n/milky allowlist list\n\n"
    "添加规则\n/milky allowlist add [目标]\n\n"
    "移除规则\n/milky allowlist del [目标]\n\n"
    "省略目标时，使用当前会话。\n"
    "目标支持 group:群号、dm:QQ号、group:* 和 dm:*。\n"
    "remove 与 del 等效。\n\n"
    "同时从多个入口修改白名单可能导致更改被覆盖。"
)
UNAVAILABLE = "白名单管理暂不可用\n\n请检查插件连接状态后重试。"
STOPPED = "插件连接已停止\n\n本次操作未执行。请在连接恢复后重试。"
INVALID_CONFIG = "白名单配置无效\n\n请检查 allowed_chats 的配置格式。"
BLOCKED = "无法修改白名单\n\n此设置受 Hermes 托管策略限制。"
CONFLICT = "更改未保存\n\n白名单已发生变化。请查看最新名单后重试。"
UNKNOWN = "无法确认操作结果\n\n请先查看白名单，确认状态后再操作。"
SAVED = "更改已保存，尚未生效\n\n请重启 Gateway 以应用更改。"
RELOAD = "配置与当前运行不同。\n请重启 Gateway 以应用当前配置。"


@dataclass(frozen=True)
class Operation:
    """保存已完成语法校验的单次操作。"""

    verb: str
    target: str | None = None


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
    if verb == "list" and len(parts) == 2:
        return Operation(verb)
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
    """由活动 adapter 拥有，串行保存和发布完整规则。"""

    def __init__(self, policy, store, publish):
        self.policy = policy
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
        """宿主放行后读写规则；不查询来源或目标群状态。"""
        if not self.accepts(invocation):
            return UNAVAILABLE
        invocation.consumed = True
        task = asyncio.current_task()
        self._tasks.add(task)
        try:
            async with self._lock:
                if not self.active or invocation.epoch != self.epoch:
                    return STOPPED
                source = invocation.chat_key
                version = self.policy.version
                snapshot = self.store.read()
                rules = snapshot["effective"].get("allowed_chats")
                if rules is None:
                    return INVALID_CONFIG
                rules = frozenset(validate_chat_rule(rule) for rule in rules)
                if operation.verb == "list":
                    return self._list(snapshot, rules)
                target = operation.target or source
                candidate = rules | {target} if operation.verb == "add" else rules - {target}
                if candidate == rules:
                    title = "规则已存在" if operation.verb == "add" else "规则不存在"
                    result = f"{title}\n{target}\n\n未作更改。"
                    if rules != self.policy.rules:
                        result += "\n" + RELOAD
                    return result
                if not snapshot["writable"]["allowed_chats"]:
                    return BLOCKED
                if not self.active or invocation.epoch != self.epoch:
                    return STOPPED
                if version != self.policy.version:
                    return CONFLICT
                result = self.store.save(snapshot["version"], candidate)
                status = result["results"]["allowed_chats"]
                if status != "saved":
                    return BLOCKED if status == "blocked" else UNKNOWN
                if not self.active or invocation.epoch != self.epoch:
                    return SAVED
                try:
                    self._publish(candidate)
                except Exception:  # noqa: BLE001 - 保存成功不得回滚或重试
                    return SAVED
                action = "已添加" if operation.verb == "add" else "已移除"
                return f"{action}白名单规则\n{target}\n\n更改已保存并生效。"
        except ManagementError as error:
            return {
                "blocked": BLOCKED,
                "conflict": CONFLICT,
                "unsupported": UNAVAILABLE,
                "invalid_input": INVALID_CONFIG,
                "malformed": INVALID_CONFIG,
            }.get(error.status, UNKNOWN)
        except Exception:  # noqa: BLE001 - 宿主异常不能泄漏原始配置或异常正文
            return UNKNOWN
        finally:
            self._tasks.discard(task)

    def _list(self, snapshot, rules):
        """完整返回已排序规则，长消息由既有发送流程处理。"""
        runtime = self.policy.rules
        source = snapshot["sources"]["allowed_chats"]
        lines = ["会话白名单", ""]
        if rules == runtime:
            if rules:
                lines.extend(sorted(rules))
                lines.extend(["", f"共 {len(rules)} 条规则"])
            else:
                lines.extend(["尚未添加规则。", "当前不接收任何会话的普通消息。", ""])
            lines.extend([f"配置来源：{source}", "配置与当前运行一致。"])
            if not rules:
                lines.extend(["", "添加当前会话：", "/milky allowlist add"])
        else:
            lines.extend(["当前配置", *(sorted(rules) or ["（空）"]), "", "当前运行"])
            lines.extend(sorted(runtime) or ["（空）"])
            lines.extend(["", f"配置来源：{source}", ""])
            if not rules:
                lines.append("当前配置为空，应用后将停止接收所有会话的普通消息。")
            if not runtime:
                lines.append("当前运行的白名单为空，尚不接收任何会话的普通消息。")
            lines.append(RELOAD)
        return "\n".join(lines)
