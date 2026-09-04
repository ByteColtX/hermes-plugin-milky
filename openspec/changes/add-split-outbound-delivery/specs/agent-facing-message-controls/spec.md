## MODIFIED Requirements

### Requirement: 平台提示必须公开基础消息控制语法

Milky 平台提示 MUST 告知 Agent 默认不自动 @ 或引用，并 MUST 说明以下两种 CQ-compatible 出站语法及其含义：`[CQ:at,qq=<uid>]` 用于 @ 指定用户，`[CQ:reply,id=<msg_id>]` 用于引用指定消息。平台提示 MUST 同时说明 Agent MAY 在需要模拟自然聊天节奏时，在回复中使用单独成行且大小写严格匹配的 `[SPLIT]`；有效标记会被删除并按顺序生成最多三条文本消息，空段不发送。提示 MUST 说明独立 `MEDIA:` 附件由 Hermes 在文本投递后交给 Milky，当前不支持与文本段交错。平台提示 MAY 提醒 Agent 按需加载完整的 QQ reference skill；对于 skill 中列出的其他 CQ 码，提示不得把其 fallback 文本行为误称为已确认的 Milky 原生能力。

#### Scenario: Agent 获得基础语法和分段说明

- **WHEN** Hermes 为 Milky 会话构建平台相关 Agent 上下文
- **THEN** 平台提示 SHALL 包含 at、reply 和 `[SPLIT]` 的使用说明
- **AND** SHALL 明确 `[SPLIT]` 必须独立成行、区分大小写且最多产生三条文本消息
- **AND** SHALL 明确默认不自动添加 @ 或引用

#### Scenario: Agent 获得基础语法

- **WHEN** Hermes 为 Milky 会话构建平台相关 Agent 上下文
- **THEN** 平台提示 SHALL 包含 at 和 reply 两种 CQ-compatible 语法
- **AND** SHALL 明确默认不自动添加 @ 或引用

#### Scenario: Agent 获得基础语法说明

- **WHEN** Hermes 为 Milky 会话构建平台相关 Agent 上下文
- **THEN** 平台提示 SHALL 包含 at 和 reply 两种 CQ-compatible 语法
- **AND** SHALL 明确默认不自动添加 @ 或引用

#### Scenario: Agent 获得媒体顺序说明

- **WHEN** 平台提示说明普通回复可以包含 `MEDIA:` 附件指令
- **THEN** 提示 SHALL 说明文本分段先于附件投递
- **AND** SHALL 说明当前不能让文本段和附件交错

#### Scenario: 平台提示保持稳定

- **WHEN** 不同消息触发同一 Milky 会话的平台提示
- **THEN** 平台提示 SHALL 不嵌入当前消息的 uid、msg_id、正文、token 或媒体 URL
- **AND** 每轮变化的消息身份 SHALL 只通过当前消息或 channel_context 提供

### Requirement: 控制码 ID 必须来自 Agent 可见的真实消息头

Agent 生成 `[CQ:at,qq=...]` 时 MUST 原样使用当前消息或 `channel_context` 消息头中出现的 `uid`；生成 `[CQ:reply,id=...]` 时 MUST 原样使用当前消息或 `channel_context` 消息头中出现的 `msg_id`。Agent-facing 语法 MUST NOT 允许使用昵称、正文、记忆或猜测替代缺失 ID；字段缺失时不得生成对应控制码。

#### Scenario: 使用当前消息 ID

- **WHEN** 当前 Agent 输入包含消息头中的真实 uid 和 msg_id
- **THEN** Agent SHALL 可以生成合法的 at 或 reply 控制码
- **AND** 适配器 SHALL 将这些值视为消息提供的 ID，而不是从显示名推断

#### Scenario: 缺少可引用消息序号

- **WHEN** 当前消息和 channel_context 都没有可用的 `msg_id`
- **THEN** Agent SHALL 不生成 `[CQ:reply,id=...]`
- **AND** 出站边界 SHALL 不因缺失值伪造引用目标

#### Scenario: 不从显示名猜测身份

- **WHEN** 上下文只出现显示名而没有对应的 `uid`
- **THEN** Agent SHALL 不生成针对该显示名的 `[CQ:at,qq=...]`
- **AND** 系统 SHALL 保持普通文本发送或由模型选择其他不需要 ID 的回复
