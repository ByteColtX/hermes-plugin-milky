## Context

归档的 `simplify-dm-channel-context` 已让 dm 历史 `channel_context` 使用 body-only，但保留了
当前 `MessageEvent.text` 的既有普通消息 header。实际日志中的 `msg` 来自当前 `text`，因此
私聊仍会显示 `<sender uid ... msg_id ...>`。本 change 需要把相同的 chat-aware 选择规则延伸
到当前 Agent-facing 文本，同时保留 group 文本、system event 和 Hermes 内部 metadata 边界。

当前历史路径已经在 `session.buffer` 和 `inbound.pipeline` 之间共享 dm/group renderer 选择；
当前消息路径仍在 batch 兼容属性和 `inbound.hermes_mapper` 中直接调用普通 header renderer。实现
必须收敛这两个出口，避免 detached batch、最终 pipeline 和 Hermes 日志看到不同的 dm 文本。

## Goals / Non-Goals

**Goals:**

- 让普通 dm 当前消息和历史消息都只向 Agent 提供经过 body 编码的正文。
- 保持 group 当前消息、group 历史、dm system event 和 ingress/context 顺序行为不变。
- 保留 dm 当前消息的真实 message ID、reply metadata、canonical、资源和媒体字段。
- 让 batch 直接访问、公开 helper、resolved pipeline 和最终 `MessageEvent.text` 使用同一 dm/group
  选择规则。
- 用回归测试证明 Hermes 日志所消费的当前 dm `text` 不再含普通消息 header。

**Non-Goals:**

- 不删除或改写 Hermes 内部 `MessageEvent.reply_to_message_id`、reply author、own-message
  或 canonical 身份字段。
- 不把 dm system event 的 `<event ...>` 类型标识压成普通正文。
- 不改变 group header、group self-reply 文案、媒体 materialization、资源查询、Gate、Will、
  dedup 或出站 Action。
- 不从正文、sender 名称或日志文本推断 chat namespace。

## Decisions

### 1. 共享普通消息 Agent-facing renderer

新增或扩展 chat-aware 的普通消息渲染边界，使其同时服务历史记录和当前 `MessageEvent.text`。
已确认 `dm:` 时返回 `_escape_body(body)`；已确认 `group:` 时继续调用现有 header renderer。
system event 继续单独走 event renderer，不接受 dm body-only 选择。

备选方案是只在 `inbound.hermes_mapper` 中删除 dm header。该方案会让
`DetachedTriggerBatch.current_text`、公开 helper 和实际 Hermes 交接结果分叉，因此不采用。

### 2. Agent-facing 文本与内部 metadata 分离

dm 文本 renderer 只改变可见正文，不修改 canonical 或 resolved reply 结果。mapper 继续从
canonical/resolved 对象填充 `message_id`、`reply_to_message_id`、reply author、own-message、
媒体和 metadata；这些字段不再依赖 Agent-facing header 才能保留。

### 3. group 仍使用 header renderer

chat namespace 必须来自已确认的 batch/canonical chat key。group 当前和历史均继续使用现有字段
顺序、self-reply label 和转义；dm 当前和历史均不输出普通 header。缺少或混用 namespace 仍然
失败，不回退到 group 模板。

### 4. 测试锁定日志可见边界

测试同时断言 `event.text` 和 `event.channel_context`：dm 两者均无普通 header，group 两者
保留既有 header；dm reply metadata 仍为真实 ID；system event 在 dm context 中仍以 event
格式出现。resolved history/current body、换行编码、空上下文和媒体字段继续来自同一批次。

## Risks / Trade-offs

- [dm Agent 无法从普通文本直接取得 sender/message ID/reply ID] → 这是明确的 Agent-facing 取舍；
  Hermes event 内部字段和 canonical 仍保留真实值，显式控制码能力若依赖 header 需按新契约评估。
- [当前 renderer 接入遗漏会导致日志和 Agent 输入仍显示 header] → 对 batch current text、mapper
  event.text 和最终 fake Hermes event 增加同一 dm 案例断言。
- [group 被错误套用 body-only] → 只接受已确认 `dm:`/`group:` namespace，并保留 group 字节级
  regression assertions。
- [system event 与 dm 正文混排难以识别] → 保留 `<event <event_type>> <body>`，仅普通消息使用
  body-only。

## Migration Plan

1. 先补充当前 dm `MessageEvent.text`、历史 `channel_context`、reply metadata 和 group 不变性的
   脱敏测试。
2. 将共享 chat-aware renderer 接入当前消息 batch/helper/mapper 出口，禁止 dm 普通消息回退到
   header renderer。
3. 更新 `ARCHITECTURE.md` 和两个主 capability spec，说明 dm 当前与历史均 body-only。
4. 运行聚焦测试、完整质量门禁和 OpenSpec strict validation；真实 Hermes/Milky 集成仍记录为
   未覆盖边界。
5. 回滚只需恢复 dm 当前消息的 header renderer 选择，不涉及远端状态迁移。
