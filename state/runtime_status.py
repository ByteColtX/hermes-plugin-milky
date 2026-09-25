"""只读展示当前实例的生命周期、事件流和白名单观察。"""

from __future__ import annotations

import inspect
import math
import time

from session.identity import validate_chat_rule

UNAVAILABLE = "运行状态暂不可用\n\n无法确认当前插件实例及其归属。"
_PHASES = {"starting": "启动中", "running": "运行中", "stopped": "已停止", "failed": "运行失败"}
_STREAM_PHASES = {
    "connecting": "连接中",
    "connected": "已连接",
    "reconnecting": "重连中",
    "stopped": "已停止",
}


def format_duration(seconds):
    """按单调经过时间舍去秒，不把缺失观察当作零。"""
    if seconds is None:
        return "未知"
    if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
        return "未知"
    minutes = int(seconds // 60)
    if not minutes:
        return "不足 1 分钟"
    days, minutes = divmod(minutes, 1440)
    hours, minutes = divmod(minutes, 60)
    return " ".join(
        f"{value} {unit}"
        for value, unit in ((days, "天"), (hours, "小时"), (minutes, "分钟"))
        if value
    )


def _rules(value):
    """仅接受已取得的完整规则集合，非法值保持未知。"""
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise TypeError("invalid_rules")
    return frozenset(validate_chat_rule(rule) for rule in value)


class RuntimeStatus:
    """由 adapter 驱动运行代次，不通过任务或客户端存在推断连接。"""

    def __init__(self, policy, profile, event_stream, *, clock=time.monotonic):
        self.policy = policy
        self.profile = profile
        self.event_stream = event_stream
        self.clock = clock
        self.epoch = 0
        self.phase = "stopped"
        self.started_at = None
        self.elapsed = None
        self.bound = False

    def starting(self):
        """开始新的实例运行代次，但尚未启动计时。"""
        self.epoch += 1
        self.phase = "starting"
        self.started_at = None
        self.elapsed = None
        self.bound = True

    def running(self):
        """初始同步完成时开始本次运行计时。"""
        self.phase = "running"
        self.started_at = self.clock()
        self.elapsed = None

    def stop(self, *, failed=False):
        """冻结本次运行时间并使正在读取的旧代次失效。"""
        if self.phase == "running" and self.started_at is not None:
            self.elapsed = max(0, self.clock() - self.started_at)
        self.phase = "failed" if failed else "stopped"
        self.epoch += 1
        self.bound = False

    def _trusted(self):
        """只接受注册时绑定且仍属于当前作用域的 profile。"""
        current = getattr(self.profile, "is_current", None)
        return self.bound and callable(current) and current() is True

    async def status(self):
        """只读最新有效规则，并在读取后复核实例归属与规则版本。"""
        try:
            if not self._trusted():
                return UNAVAILABLE
            epoch = self.epoch
            phase = self.phase
            version = getattr(self.policy, "version", None)
            try:
                runtime = _rules(getattr(self.policy, "rules", None))
            except (TypeError, ValueError):
                runtime = None
            elapsed = self.elapsed
            if phase == "running" and self.started_at is not None:
                elapsed = max(0, self.clock() - self.started_at)
            duration = (
                "尚未开始"
                if phase == "starting" and self.started_at is None
                else format_duration(elapsed)
            )
            stream = _STREAM_PHASES.get(
                getattr(self.event_stream(), "connection_state", None), "未知"
            )
            consistency = "白名单配置一致性未知。"
            try:
                read = getattr(self.profile, "allowed_chats", None)
                if callable(read):
                    latest = read()
                    if inspect.isawaitable(latest):
                        latest = await latest
                else:
                    snapshot = self.profile.read()
                    if inspect.isawaitable(snapshot):
                        snapshot = await snapshot
                    latest = snapshot["effective"]["allowed_chats"]
                configured = _rules(latest)
                if runtime is not None and version is not None and version == self.policy.version:
                    consistency = (
                        "白名单配置与当前运行一致。"
                        if configured == runtime
                        else "白名单配置与当前运行不同。\n请重启 Gateway 以应用当前配置。"
                    )
            except Exception:  # noqa: BLE001 - 配置失败不泄漏正文也不影响可信本地字段
                consistency = "白名单配置一致性未知。"
            if epoch != self.epoch or not self._trusted():
                return UNAVAILABLE
            if version != getattr(self.policy, "version", None):
                consistency = "白名单配置一致性未知。"
            lines = [
                "Milky · 运行状态",
                "",
                f"插件: {_PHASES.get(phase, '未知')}",
                f"事件流: {stream}",
                f"本次运行: {duration}",
                "",
            ]
            lines.append(
                "运行白名单: 未知" if runtime is None else f"运行白名单: {len(runtime)} 条规则"
            )
            if runtime == frozenset():
                lines.append("当前不接收任何会话的普通消息。")
            lines.append(consistency)
            return "\n".join(lines)
        except Exception:  # noqa: BLE001 - 归属观察失败保持整条不可用
            return UNAVAILABLE
