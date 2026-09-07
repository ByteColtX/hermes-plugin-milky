## MODIFIED Requirements

### Requirement: Agent-facing 文本区分历史上下文和当前消息

当存在 detached 历史时，适配器 MUST 将历史紧凑记录只放入 `MessageEvent.channel_context`，
并使用资源解析及 batch 内容去重完成后的历史正文。group 历史记录 MUST 继续使用既有单行
header 格式；dm 历史普通消息 MUST 只使用经过 body 编码的正文，不生成普通消息 header。
当前 trigger 消息 MUST 继续以现有紧凑 header 格式放入 `MessageEvent.text`，并使用与其
媒体代表一致的图片 basename。适配器 MUST NOT 把 `[New message]` 标记或当前消息复制到
`channel_context`；Hermes 已有的 Agent 输入组装语义负责在历史块和当前消息之间加入该标记。
没有历史时，适配器 MUST 保持 `channel_context=None`，并只交付当前消息正文。

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
- **AND** `text` SHALL 继续使用当前 dm 消息的现有单行 header 和规范化正文
- **AND** Hermes 的有效 Agent 输入 SHALL 仍在历史块后以空行和 `[New message]` 分隔当前消息
- **AND** 当前消息 SHALL 不出现在 `channel_context`

#### Scenario: 没有历史时交付当前消息

- **WHEN** trigger 发生时 detached batch 为空
- **THEN** `channel_context` SHALL 为 `None`
- **AND** `text` SHALL 仍使用当前消息的现有紧凑 header 和规范化正文
- **AND** 适配器 SHALL 不伪造历史标题或空的上下文 block
