## Why

Milky v1.3 把消息序号统一命名为 `message_seq`，但插件当前在 canonical record、去重诊断、上下文 header、出站结果和文档中混用 `message_id`、`msg_id` 与 `message_seq`。这种混用容易把协议消息序号和 Hermes 的 `MessageEvent.message_id`、buffer 的 `ingress_sequence` 混淆；尤其群聊 `channel_context` 暴露 `msg_id`，实际值却来自 Milky `message_seq`。

## What Changes

- 将插件自身表示 Milky 消息序号的字段、局部变量、方法参数、去重命名、诊断名称和文档统一为 `message_seq`；保持其当前字符串/整数边界语义不变。
- 将群聊普通消息的 Agent-facing header 从 `msg_id` 改为 `msg_seq`，使其与 Milky OpenAPI 的 `message_seq` 对齐；`reply_to` 的值仍表示被引用消息的 `message_seq`。
- 将缺少稳定消息序号的诊断从 `no_stable_message_id` 统一为 `no_stable_message_seq`，并同步更新测试、fixture 说明和安全可观测文档。
- 将稳定去重 key 及其规范说明中的占位名称改为 `message_seq`；key 仍只由已确认的 Milky 消息序号组成，不使用正文、时间或 `ingress_sequence` 替代。
- 在进入 Hermes 的适配边界显式保留兼容映射：Hermes 要求的 `MessageEvent.message_id`、`reply_to_message_id` 以及宿主 session 环境字段不改名，其值来自插件确认的 `message_seq`。
- **BREAKING**：依赖群聊 `channel_context` 中 `msg_id` 文本标签或插件缺失序号诊断字符串的外部消费者需要迁移到 `msg_seq` 和 `no_stable_message_seq`。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `canonical-messages`：将 canonical 稳定身份、去重 key 和缺失序号诊断的插件命名统一为 `message_seq`，并明确与 Hermes `message_id` 的边界映射。
- `hermes-message-pipeline`：将 group 的 Agent-facing 普通消息 header 使用的 `msg_id` 标签改为 `msg_seq`，同时保持 Hermes MessageEvent 字段契约不变。
- `outbound-messaging`：将插件内部出站成功结果对 Milky `data.message_seq` 的命名说明统一为 `message_seq`，并明确交给 Hermes SendResult 时的兼容映射。

## Impact

- 受影响代码：`inbound/` canonical 与 normalizer、`session/` identity 与 context renderer、`milky/` client/parser/resource 诊断、`outbound/` 发送结果和相关适配边界。
- 受影响测试和 fixture：canonical、parser、context rendering、pipeline、outbound 和集成 fake 的字段断言与诊断断言。
- 受影响文档：`ARCHITECTURE.md`、`README.md`、相关主 spec 和本 change artifacts。
- Milky HTTP/SSE wire contract 不变：协议请求、事件和响应仍使用 `message_seq`；Hermes core 的 `message_id` API 不变。不会修改 Hermes core、消息序号的类型语义、去重时序或消息投递行为。
