## Context

当前 `trigger` 的 Will 决策发生在 per-chat admission 内，但 reply cost 在 detached handoff 完成后才执行。资源解析、Hermes `handle_message()` 和最终出站发送不属于 willingness 决策本身；详见 proposal.md 及本 change 的 delta spec。

## Goals / Non-Goals

**Goals:**

- 让同一 chat 的下一次 Will 决策立即看到前一次 `trigger` 的扣分。
- 将一次 `trigger` 映射为一次、同步、不可回滚的 `replyCost`。
- 保持实现不需要 pending cost、异步确认、回滚或插件侧 Agent 队列。

**Non-Goals:**

- 不改变 willingness 的加分、衰减、概率、force 或 per-chat 隔离公式。
- 不等待或改变 Hermes Agent、Milky `send_*_message` Action、资源解析和出站发送。
- 不为失败的 trigger 增加重试、补偿或新的持久化状态。

## Decisions

### 在 trigger 决策后、释放 admission 前扣分

Will 返回 `trigger` 后，pipeline 在当前 chat 的 admission 临界区内立即执行一次 reply cost，再 drain wait buffer 并创建 detached handoff。这样后续同 chat 事件必须排在这次状态更新之后，不会观察到未扣分的窗口。

替代方案是继续在 handoff 成功后扣分，会保留当前竞态；或者增加 pending cost 并在成功/失败时确认或释放，语义更精细但不符合本 change 的简化目标。

### 复用现有 reply-cost 反馈边界

继续使用现有 Will reply-cost 反馈入口，不新增 pending 状态或跨模块确认协议；只把调用位置和文档语义改为“trigger 参与成本”。routing engine 没有 willingness cost 状态，因此保持无副作用。

### 失败不补偿

扣分成功执行后，资源解析、mapper、Hermes `handle_message()` 或 detached task 的后续失败均不恢复分数。这样状态只由入站 Will 决策决定，不依赖远端执行结果，也避免失败路径再次引入异步协调。

### 观测名称跟随新语义

现有 reply-cost 诊断应在 trigger 扣分时记录；pipeline 的计数应表示已执行的扣费次数，而不是成功 handoff 次数。成功或失败的 detached handoff 继续分别使用原有交接诊断，不重复记录扣费。

## Risks / Trade-offs

- [Milky 或 Hermes 故障时仍消耗 willingness] → 这是本 change 明确选择的语义；不增加回滚，避免远端结果重新控制 Will 状态。
- [进程在 trigger 扣分后立即停止] → 该次成本保留；状态本来就是进程内可丢失状态，不引入持久化补偿。
- [测试或监控把 reply cost 理解为成功交接] → 更新测试名称、计数断言和文档，将“参与成本”和“handoff 成功”分开表达。

## Migration Plan

无需数据迁移。发布后新进入的 `trigger` 使用即时扣分；回滚代码即可恢复旧的成功 handoff 扣分时点，但回滚不会恢复已经在新版本中消耗的进程内分数。

