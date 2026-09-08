## MODIFIED Requirements

### Requirement: Agent-facing 文本区分历史上下文和当前消息

当存在 detached 历史时，适配器 MUST 将历史紧凑记录只放入 `MessageEvent.channel_context`，
并使用资源解析及 batch 内容去重完成后的历史正文。所有历史 renderer 出口 MUST 根据同一已
确认 chat namespace 选择模板：group 历史继续使用既有单行 header，dm 普通历史只使用经过
body 编码的正文，不生成普通消息 header。当前 trigger 消息 MUST 只进入本次
`MessageEvent.text`；group 当前消息继续使用现有紧凑 header，dm 当前消息 MUST 只使用经过
body 编码的正文，不生成 sender、uid、`msg_id`、`reply_to` 或其他普通消息 header。当前消息
仍使用与其媒体代表一致的图片 basename。适配器 MUST NOT 把 `[New message]` 标记或当前消息
复制到 `channel_context`；Hermes 已有的 Agent 输入组装语义负责在历史块和当前消息之间加入
该标记。没有历史时，适配器 MUST 保持 `channel_context=None`，并只交付当前消息正文。
当前 dm 的 Hermes reply metadata、canonical、真实消息 ID 和资源结果 MUST 继续保留，不得
因为 Agent-facing 文本 body-only 而丢失或改写。

#### Scenario: Agent 收到历史和当前消息

- **WHEN** 两条 group 历史消息后收到一条当前 group trigger 消息，且历史中有重复内容图片
- **THEN** `channel_context` SHALL 仅为按顺序渲染的 group 历史记录块，并引用首次代表 basename
- **AND** `text` SHALL 仅为当前 group 消息记录，并引用 batch 选择的图片代表 basename
- **AND** Hermes 的有效 Agent 输入 SHALL 在历史块后以空行和 `[New message]` 分隔当前消息
- **AND** 当前消息 SHALL 不出现在 `channel_context`

#### Scenario: Agent 收到 dm 历史和当前消息

- **WHEN** 一条或多条 dm 历史消息后收到一条当前 dm trigger 消息
- **THEN** `channel_context` SHALL 只包含按 ingress sequence 排列的历史正文行
- **AND** `channel_context` SHALL NOT 包含历史消息的 sender、uid、`msg_id` 或 `reply_to` header
- **AND** `text` SHALL 只包含当前 dm 消息的经过 body 编码的正文
- **AND** `text` SHALL NOT 包含当前消息的 sender、uid、`msg_id` 或 `reply_to` header
- **AND** 当前 trigger SHALL 不出现在 `channel_context`

#### Scenario: 没有历史时交付当前消息

- **WHEN** group trigger 发生时 detached batch 为空
- **THEN** `channel_context` SHALL 为 `None`
- **AND** `text` SHALL 仍使用当前 group 消息的紧凑 header 和规范化正文
- **AND** 适配器 SHALL 不伪造历史标题或空的上下文 block

#### Scenario: 没有历史时交付当前 dm 消息

- **WHEN** dm trigger 发生时 detached batch 为空
- **THEN** `channel_context` SHALL 为 `None`
- **AND** `text` SHALL 只包含当前 dm 消息的经过 body 编码的正文
- **AND** `text` SHALL NOT 包含普通消息 header

#### Scenario: dm 当前消息 reply metadata 与 Agent-facing 文本分离

- **WHEN** 当前 dm 消息引用一条消息，且引用目标的 sender、message sequence 或 own-message 归属已确认
- **THEN** `text` SHALL 只包含当前 dm 正文，不展示 reply header
- **AND** `MessageEvent.reply_to_message_id` SHALL 保留真实引用的 `message_seq`
- **AND** reply author、own-message 和资源解析字段 SHALL 保持已确认值

#### Scenario: system event 在 dm 历史中保持可识别

- **WHEN** dm chat 的普通历史与 context-only system event 按 ingress sequence 合并
- **THEN** 普通 dm 记录 SHALL 只使用正文
- **AND** system event SHALL 使用 `<event <event_type>> <body>` 格式
- **AND** system event SHALL 不形成独立 Hermes turn
