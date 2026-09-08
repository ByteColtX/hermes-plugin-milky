## Context

当前 Milky parser 和 segment DTO 已使用协议字段 `message_seq`，但 canonical 消息、去重诊断、群聊 Agent-facing header 和 Milky 出站结果仍有 `message_id`/`msg_id` 命名。Hermes `MessageEvent` 与宿主 `SendResult` 是外部契约，仍要求 `message_id`；因此本 change 需要在 Milky/插件边界完成改名，并在 Hermes 交接处保留显式映射。

## Goals / Non-Goals

**Goals:**

- 让插件内部代表 Milky 消息序号的命名统一为 `message_seq`。
- 让群聊普通消息的 Agent-facing header 使用 `msg_seq`，并清楚区分它与 `ingress_sequence`。
- 让缺失序号诊断、去重规范、出站 Milky 结果和相关文档使用一致术语。
- 保持 Milky HTTP/SSE wire 字段、序号值、去重时序、reply 解析和消息投递语义不变。
- 在 Hermes boundary 集中完成 `message_seq` → `MessageEvent.message_id`、`reply_to_message_id` 或宿主 `SendResult.message_id` 的兼容映射。

**Non-Goals:**

- 不修改 Hermes core 的 `MessageEvent`、`SendResult`、session environment 或 reply metadata 字段名。
- 不把 `ingress_sequence` 改名为消息序号，也不使用它替代 Milky `message_seq`。
- 不改变 Milky OpenAPI Action 名称、请求/响应 JSON、SSE event schema 或 `message_seq` 的整数协议类型。
- 不为旧的 `msg_id` header 或 `no_stable_message_id` 诊断保留双写/兼容别名；这是明确的命名迁移。

## Decisions

### 1. 按边界而不是全局替换命名

Milky parser/model 层继续直接表达 `message_seq`；canonical 的稳定字段、引用字段、去重相关局部变量和诊断改为 `message_seq`。群聊文本标签使用短形式 `msg_seq`，因为它是 Agent-facing header 的字段标签；它的值仍是同一真实 Milky `message_seq`。

Hermes 交接层保留宿主要求的 `message_id` 和 `reply_to_message_id`，只在构造 `MessageEvent`/宿主发送结果时赋值。这样不会把插件命名迁移误传为 Hermes core API 变更。

备选方案是保留 canonical `message_id`、只替换 header 文本。该方案不能消除插件内部和诊断中的协议语义混淆，因此不采用。

### 2. 只改字段名，不改值和类型边界

入站 canonical 继续把 Milky 整数 `message_seq` 规范化为当前使用的字符串稳定值；reply 的真实序号、缺失值行为和 dedup value 均不改变。Milky client 的发送结果在 Milky/插件内部以 `message_seq` 表示，交给 Hermes 时再生成兼容的 `message_id` 字段。

备选方案是把所有内部序号改成整数。该方案会扩大类型变化和边界风险，与现有 Hermes 字符串 ID 和安全序列化契约无关，因此不采用。

### 3. 将命名迁移作为显式 breaking change

群聊 `channel_context` 的 `msg_id` 文本标签和 `no_stable_message_id` 诊断属于可观察字符串，直接替换为 `msg_seq` 和 `no_stable_message_seq`。测试必须同时断言新值存在和旧值不存在；不在运行时输出两个标签，也不把旧诊断作为别名返回，以免消费者继续依赖含混命名。

### 4. 采用边界清单驱动实现和验证

实现时先按以下边界清单处理引用，再做质量检查：

- Milky/插件内部允许改名：canonical identity、dedup helper 参数和 key 术语、normalizer/parser 诊断、context renderer 的普通 group header、Milky client 的发送结果、resource/observability 的安全关联字段。
- 必须保留的 Hermes 名称：`MessageEvent.message_id`、`MessageEvent.reply_to_message_id`、Hermes `SendResult.message_id`、宿主 session context 的 `HERMES_SESSION_MESSAGE_ID`。
- 必须保留的 Milky wire 名称：事件、reply segment、`get_message`/`recall_group_message` 入参和 `send_*` 响应中的 `message_seq`。

避免对仓库执行无差别字符串替换；每个命名变更都要由 canonical、pipeline、outbound 和 context 测试覆盖其所在边界。

## Risks / Trade-offs

- [下游 prompt 或脚本解析 `msg_id`] → 在 README、架构文档和变更说明中明确迁移到 `msg_seq`，并用回归测试拒绝旧 header 标签。
- [误改 Hermes `message_id` 导致宿主交接失败] → 采用边界清单；增加 fake Hermes 断言，验证 event/result 仍只接收 `message_id`，值等于确认的 `message_seq`。
- [缺失序号诊断消费者依赖旧字符串] → 将 `no_stable_message_seq` 作为明确 breaking change，更新所有 fixture/test 断言，不双写旧分类。
- [把 `ingress_sequence` 误当作消息序号] → 保持 ingress 排序测试和 dedup 测试独立，验证相同 `message_seq` 才去重、不同 `message_seq` 即使正文相同也分别处理。
- [内部 Milky SendResult 改名遗漏 sender 映射] → 为 Milky client 结果和 Hermes outbound result 分别增加成功路径断言，确认同一字符串在 boundary 处完成一次映射。

## Migration Plan

1. 先更新 delta spec、`ARCHITECTURE.md`、`README.md` 和相关实现注释，明确 Milky `message_seq`、Agent header `msg_seq` 与 Hermes `message_id` 的三层边界。
2. 按边界清单重命名 canonical、诊断、renderer 和 Milky-side outbound result，并保持 wire payload 与 Hermes boundary 字段不变。
3. 更新脱敏 fixture、unit/fake integration 测试，覆盖 group header、dm 无 header、reply 序号、缺失序号、dedup 和出站结果映射。
4. 运行聚焦测试、完整 pytest、Ruff、format、build、diff 检查和 OpenSpec strict validate；失败时按旧标签残留、Hermes boundary 回归、诊断分类和协议 wire 变化分类修复。
5. 若需要回滚，回退本 change 的命名变更和对应文档/测试；不得回滚或修改 Milky 远端消息序号，也不需要迁移持久化数据，因为 dedup key 的实际数字值不变。
