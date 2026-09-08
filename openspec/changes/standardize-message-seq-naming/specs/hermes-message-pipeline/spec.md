## MODIFIED Requirements

### Requirement: Agent-facing 文本区分历史上下文和当前消息

当存在 detached 历史时，适配器 MUST 将历史紧凑记录只放入 `MessageEvent.channel_context`，并使用资源解析及 batch 内容去重完成后的历史正文。所有历史 renderer 出口 MUST 根据同一已确认 chat namespace 选择模板：group 历史继续使用既有单行 header，且普通消息的真实 Milky 序号 MUST 使用 `msg_seq` 标签；dm 普通历史只使用经过 body 编码的正文，不生成普通消息 header。当前 trigger 消息 MUST 只进入本次 `MessageEvent.text`；group 当前消息继续使用带 `msg_seq` 的紧凑 header，dm 当前消息 MUST 只使用经过 body 编码的正文，不生成普通消息 header，并使用与其媒体代表一致的图片 basename。对于已经成功 materialize 并交给 Hermes core 的当前 `record`，适配器 MUST 从当前 `text` 移除插件生成的 `[record:NOT SUPPORTED]` 占位，不得重复渲染 STT 成功文本、STT 失败提示或 STT 未启用提示；这些提示由 Hermes core 的既有语音处理负责。资源 materialization 失败的当前 `record` MAY 保留既有安全失败占位。历史 `record` 暂不自动 materialize 为本次 Agent 输入或自动 STT，历史 renderer SHALL 保留既有 record 占位策略。适配器 MUST NOT 把 `[New message]` 标记或当前消息复制到 `channel_context`；Hermes 已有的 Agent 输入组装语义负责在历史块和当前消息之间加入该标记。没有历史时，适配器 MUST 保持 `channel_context=None`，并只交付当前消息正文。

#### Scenario: Agent 收到历史和当前消息

- **WHEN** 两条历史消息后收到一条当前 trigger 消息，且历史中有重复内容图片
- **THEN** `channel_context` SHALL 仅为按顺序渲染的历史记录块，并引用首次代表 basename
- **AND** `text` SHALL 仅为当前消息记录，并引用 batch 选择的图片代表 basename
- **AND** Hermes 的有效 Agent 输入 SHALL 在历史块后以空行和 `[New message]` 分隔当前消息
- **AND** 当前消息 SHALL 不出现在 `channel_context`

#### Scenario: 群聊 header 使用 Milky 消息序号标签

- **WHEN** group 历史或当前消息包含已确认的 Milky `message_seq`
- **THEN** Agent-facing 普通消息 header SHALL 使用 `msg_seq <message_seq>`
- **AND** header SHALL NOT 使用 `msg_id` 表示该序号
- **AND** `reply_to` 的值 SHALL 仍表示已确认的被引用消息 `message_seq`，或在已确认自引用时使用既有 `your_previous_msg` 标签

#### Scenario: 当前 record 不重复渲染 core 提示

- **WHEN** 当前 `record` 已成功 materialize，并且 Hermes core 会处理该 MessageEvent 的 `media_urls`
- **THEN** 当前 `MessageEvent.text` SHALL 不包含插件生成的 `[record:NOT SUPPORTED]`
- **AND** 插件 SHALL 不根据 STT 是否配置、是否失败或是否返回空文本自行追加语音提示
- **AND** core 产生的转录文本或语音降级提示 SHALL 成为该语音输入的唯一 core-level 提示来源

#### Scenario: 没有历史时交付当前消息

- **WHEN** trigger 发生时 detached batch 为空
- **THEN** `channel_context` SHALL 为 `None`
- **AND** group 的 `text` SHALL 仍使用包含 `msg_seq` 的当前消息紧凑 header，dm 的 `text` SHALL 只使用经过 body 编码的正文
- **AND** 适配器 SHALL 不伪造历史标题或空的上下文 block

#### Scenario: Agent 收到 dm 历史和当前消息

- **WHEN** 一条或多条 dm 历史消息后收到一条当前 dm trigger 消息
- **THEN** `channel_context` SHALL 只包含按 ingress sequence 排列的历史正文行
- **AND** `channel_context` SHALL NOT 包含历史消息的 sender、uid、`msg_seq` 或 `reply_to` header
- **AND** `text` SHALL 只包含当前 dm 消息的经过 body 编码的正文
- **AND** `text` SHALL NOT 包含当前消息的 sender、uid、`msg_seq` 或 `reply_to` header
- **AND** 当前 trigger SHALL 不出现在 `channel_context`

#### Scenario: Agent 收到无历史的当前 dm 消息

- **WHEN** dm trigger 发生时 detached batch 为空
- **THEN** `channel_context` SHALL 为 `None`
- **AND** `text` SHALL 只包含当前 dm 消息的经过 body 编码的正文
- **AND** `text` SHALL NOT 包含普通消息 header

#### Scenario: dm 当前消息 reply metadata 与 Agent-facing 文本分离

- **WHEN** 当前 dm 消息引用一条消息，且引用目标的 sender、message sequence 或 own-message 归属已确认
- **THEN** `text` SHALL 只包含当前 dm 正文，不展示 reply header
- **AND** `MessageEvent.reply_to_message_id` SHALL 保留真实引用的 `message_seq`
- **AND** reply author、own-message 和资源解析字段 SHALL 保持已确认值
