## Context

现有 SSE 消费和通用 `Event` DTO 已能接收 `message_recall`，但入站系统事件解析器只允许 nudge 和群成员变更进入 context-only 缓冲，其余系统事件直接观察。系统上下文已经具备按 chat 隔离、有界 FIFO、ingress sequence 排序和下一次 trigger 一次性注入的边界；本设计复用这条路径，不改变普通消息的 canonical、Gate、Will 或 Hermes handoff。

`message_recall` 事件只携带撤回元数据。当前仓库已有脱敏的 group 事件 fixture；friend 事件的实现与测试必须以事件中明确提供的 `message_scene=friend`、`peer_id`、`message_seq` 和 `sender_id` 为前提，不使用 OneBot 字段别名或消息正文推断协议语义。

## Goals / Non-Goals

**Goals:**

- 在事件解析边界严格校验撤回事件的场景和 ID 字段。
- 将合法 friend/group 撤回事件映射到命名空间隔离的 context-only chat，并复用既有顺序和容量语义。
- 让下一次同 chat trigger 获得固定、可解释且不含未确认扩展的撤回元数据。
- 保持 malformed、非法场景、缓冲溢出、观察日志和失败交接的安全降级。

**Non-Goals:**

- 不把撤回事件转成普通 `message_receive`、普通 `MessageEvent` 或独立 Agent turn。
- 不调用 `get_message` 恢复原消息，不下载资源，不发送回复，不调用 `recall_group_message`，也不修改权限或本地群状态。
- 不新增 Action、ToolSpec、配置项、事件恢复游标或系统事件 TTL dedup；事件帧重复问题仍遵循当前系统事件路径，若未来需要稳定事件去重应另立契约。

## Decisions

### 1. 在现有系统事件解析边界增加 `message_recall`

把 `message_recall` 加入已有 context-only 事件类型集合，并在同一解析函数中分支校验字段。这样可以保持 SSE 接收循环、普通消息 canonical 和 pipeline 的责任边界不变；将事件改造成 `message_receive` 会错误地绕过普通消息所需的正文、去重、Gate 和 Will 语义。

备选方案是仅在 observer 中记录撤回事件。该方案无需改变状态，但 Agent 永远看不到事件，不能满足 proposal 的上下文支持目标，因此不采用。

### 2. 通过 `message_scene` 和 `peer_id` 选择 chat key

`friend` 只映射为 `dm:<peer_id>`，`group` 只映射为 `group:<peer_id>`；`temp`、未知场景、缺失值、布尔值、负数和非整数 ID 直接安全拒绝。`message_seq` 与 `sender_id` 是展示撤回元数据的必要字段，`operator_id` 仅在协议明确提供且校验通过时追加。

不从 `self_id`、事件外层类型、群成员缓存或 `display_suffix` 推断缺失的场景和目标，避免把撤回事件写入错误会话。

### 3. 根据操作人存在性选择群撤回文案

对于 `group` 撤回事件，`operator_id` 缺失或 null 时使用 `uid <sender_id> 撤回了消息 msg_seq <message_seq>`；存在时使用 `管理员 uid <operator_id> 撤回了 uid <sender_id> 的消息 msg_seq <message_seq>`。这直接表达群成员只能撤回自己的消息、管理员可以撤回群员消息的业务规则；事件类型仍由通用上下文 renderer 添加为 `<event message_recall>` 前缀。`friend` 事件不添加“管理员”角色标签，按是否存在操作人使用基础或无角色的操作人文案。`display_suffix`、未知扩展、timestamp、raw payload 和原消息正文不进入 Agent-facing context。

备选方案是统一使用“消息已被撤回，操作者为……”的中性文案。该方案无法直接区分群员自撤回和管理员代撤回，降低了 Agent 对事件的可解释性，因此不采用。

### 4. 复用 context-only FIFO 和 admission 顺序

合法事件沿用既有 per-chat admission，使用当前 ingress sequence 写入独立系统事件缓冲；它与普通 wait buffer 分离，并在同 chat 的下一次 trigger 中与普通历史按序合并后原子清除。缓冲已满时保留最新事件并记录安全溢出诊断。

不新增针对撤回事件的专用队列或插件侧 Agent 执行队列，因为这会复制 Hermes busy/follow-up 语义并改变稳定的生命周期边界。

### 5. 保持 observe-only 的外部副作用边界

事件处理只做本地字段校验、固定文本渲染和上下文登记；pipeline 仍调用现有 observer 供诊断使用，但不触发资源 resolver、Will、reply cost、Hermes `handle_message()` 或任何 Milky Action。这样主动撤回工具和被动撤回通知保持清晰分离。

### 6. 以脱敏 fixture 和 fake host 固定行为

测试覆盖 group/friend 合法事件、可选操作人、非法/缺失字段、temp、不同 chat key 隔离、与普通 wait 及其他系统事件的 ingress 顺序、一次性消费、缓冲溢出、observer 失败和“无网络/无 Hermes turn”。真实 Milky/Hermes host 仍不在规划阶段验证范围内；未知服务端字段继续按安全观察或 malformed 边界处理。

## Risks / Trade-offs

- [撤回正文不可恢复] → 上下文明确展示 `message_seq` 和发送/操作人元数据，并在规范和 README 中说明不承诺恢复正文。
- [服务端 friend 事件字段语义未由现有 fixture 完整证明] → 只接受规范明确的 `message_scene`、`peer_id`、`message_seq`、`sender_id` 字段；补充合成 fixture，但不把 fake 结果宣称为真实服务兼容证明。
- [高频撤回事件可能挤占上下文缓冲] → 复用既有独立有界 FIFO，保留最新事件并记录不含正文的溢出诊断。
- [SSE 重连可能再次交付同一撤回事件] → 本 change 不发明事件 ID 或恢复游标，也不引入未经确认的 dedup 语义；重复帧遵循现有系统事件行为，后续如需去重另行定义协议契约。
- [context-only 交接失败后事件可能丢失] → 沿用 detached batch 的同批次重试或不可恢复失败记录，禁止无条件重新追加导致重复。

## Migration Plan

实现阶段先补齐事件 fixture 和系统事件解析/上下文回归测试，再接入既有 pipeline，随后更新主规范、架构和 README。部署后无需数据迁移或配置迁移；回滚只需撤销本 change 的实现与文档，既有 `message_recall` observe-only 行为仍可工作。

归档前必须以代码、测试和 evidence ledger 证明：合法事件只进入 context-only 路径，非法事件 fail-closed，且没有新增网络调用、Agent turn 或远端 Action。
