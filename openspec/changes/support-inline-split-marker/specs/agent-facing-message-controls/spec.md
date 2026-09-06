## MODIFIED Requirements

### Requirement: 平台提示必须公开基础消息控制语法

Milky 平台提示 MUST 告知 Agent 默认不自动 @ 或引用，并 MUST 说明以下两种 CQ-compatible 出站语法及其含义：[CQ:at,qq=<uid>] 用于 @ 指定用户，[CQ:reply,id=<msg_id>] 用于引用指定消息。平台提示 MUST 同时说明 Agent MAY 在需要模拟自然聊天节奏时，在回复中使用单独成行或普通正文行中的大小写严格匹配、未转义 [SPLIT]；有效标记会被删除并按顺序生成最多三条文本消息，空段不发送。提示 MUST 说明 [[SPLIT]] 用于发送字面量 [SPLIT]，并说明完整 CQ-compatible code 按整体解析，而 malformed CQ-like 文本按普通正文规则处理。提示 MUST 说明独立 MEDIA: 附件由 Hermes 在文本投递后交给 Milky，当前不支持与文本段交错。平台提示 MAY 提醒 Agent 按需加载完整的 QQ reference skill；对于 skill 中列出的其他 CQ 码，提示不得把其 fallback 文本行为误称为已确认的 Milky 原生能力。

#### Scenario: Agent 获得基础语法和分段说明

- **WHEN** Hermes 为 Milky 会话构建平台相关 Agent 上下文
- **THEN** 平台提示 SHALL 包含 at、reply 和 [SPLIT] 的使用说明
- **AND** SHALL 明确 [SPLIT] 可以单独成行或出现在普通正文行中、区分大小写且最多产生三条文本消息
- **AND** SHALL 明确 [[SPLIT]] 用于输出字面量 [SPLIT]
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

- **WHEN** 平台提示说明普通回复可以包含 MEDIA: 附件指令
- **THEN** 提示 SHALL 说明文本分段先于附件投递
- **AND** SHALL 说明当前不能让文本段和附件交错

#### Scenario: 平台提示保持稳定

- **WHEN** 不同消息触发同一 Milky 会话的平台提示
- **THEN** 平台提示 SHALL 不嵌入当前消息的 uid、msg_id、正文、token 或媒体 URL
- **AND** 每轮变化的消息身份 SHALL 只通过当前消息或 channel_context 提供
