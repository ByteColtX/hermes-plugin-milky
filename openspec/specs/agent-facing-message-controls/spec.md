# agent-facing-message-controls Specification

## Purpose

为 Hermes Agent 提供稳定、最小且可验证的 Milky QQ 消息控制语法，使模型可以依据当前
上下文中的真实身份和消息序号自行决定是否 @、引用，或同时执行两种操作。

## Requirements

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

Agent 生成 `[CQ:at,qq=...]` 时 MUST 原样使用当前消息或 `channel_context` 消息头中出现的
`uid`；生成 `[CQ:reply,id=...]` 时 MUST 原样使用当前消息或 `channel_context` 消息头中出现的
`msg_id`。Agent-facing 语法 MUST NOT 允许使用昵称、正文、记忆或猜测替代缺失 ID；字段缺失
时不得生成对应控制码。

#### Scenario: 使用当前消息 ID

- **WHEN** 当前 Agent 输入包含 `[Alice uid 101 msg_id 9001]` 的消息头
- **THEN** Agent SHALL 可以生成 `[CQ:at,qq=101]` 或 `[CQ:reply,id=9001]`
- **AND** 适配器 SHALL 将这些值视为当前消息提供的 ID，而不是从 `Alice` 推断

#### Scenario: 缺少可引用消息序号

- **WHEN** 当前消息和 channel_context 都没有可用的 `msg_id`
- **THEN** Agent SHALL 不生成 `[CQ:reply,id=...]`
- **AND** 出站边界 SHALL 不因缺失值伪造引用目标

#### Scenario: 不从显示名猜测身份

- **WHEN** 上下文只出现 `Alice` 的显示名而没有对应的 `uid`
- **THEN** Agent SHALL 不生成针对 Alice 的 `[CQ:at,qq=...]`
- **AND** 系统 SHALL 保持普通文本发送或由模型选择其他不需要 ID 的回复

### Requirement: Agent 可以独立选择 at、reply 或组合

Agent MUST 可以仅输出普通文本、仅输出 at 控制码、仅输出 reply 控制码，或在同一条消息中
输出 at 和 reply 控制码。组合控制码 MUST 保留为同一条出站消息的结构化元素，不得要求模型
调用额外的隐藏 Action。

#### Scenario: 只 @ 用户

- **WHEN** Agent 输出 `[CQ:at,qq=101]你好 Alice`
- **THEN** 出站消息 SHALL 包含一个针对 uid `101` 的 mention 和文本 `你好 Alice`
- **AND** 出站消息 SHALL 不因当前入站消息存在而自动增加 reply

#### Scenario: 只引用消息

- **WHEN** Agent 输出 `[CQ:reply,id=9001]关于这件事……`
- **THEN** 出站消息 SHALL 包含针对 msg_id `9001` 的 reply 和文本 `关于这件事……`
- **AND** 出站消息 SHALL 不自动增加 mention

#### Scenario: 同时 @ 和引用

- **WHEN** Agent 输出 `[CQ:reply,id=9001][CQ:at,qq=101]你好 Alice`
- **THEN** 出站消息 SHALL 同时包含 reply `9001`、mention `101` 和正文
- **AND** 两个控制码 SHALL 不被当作普通可见文本发送

### Requirement: 文档 CQ 类型都必须可被识别并形成出站 segment

出站解析 MUST 识别 NapCat 消息格式文档列出的 CQ 类型，包括 `text`、`face`、`image`、
`record`、`video`、`at`、`rps`、`dice`、`shake`、`poke`、`share`、`contact`、`location`、
`music`、`reply`、`forward`、`node`、`json`、`mface`、`file`、`markdown`、`lightapp`，以及
文档列出的 `anonymous`、`redbag`、`gift`、`cardimage`、`tts` 和 `xml` 扩展名。每个 CQ
码 MUST 形成一个或多个 Milky outgoing segment：能确认语义映射时使用对应原生 segment，
否则使用只包含原始 CQ 文本的 text segment。

#### Scenario: 可转换的 CQ 类型

- **WHEN** Agent 输出当前已有确认映射的 CQ 类型
- **THEN** 系统 SHALL 将其转换为对应的 Milky outgoing segment
- **AND** SHALL 保留该 CQ 码在消息中的相对顺序

#### Scenario: 暂无 Milky 原生映射的 CQ 类型

- **WHEN** Agent 输出 `music`、`location` 或其他当前没有确认 Milky 原生映射的 CQ 类型
- **THEN** 系统 SHALL 将完整 CQ 码原样放入 text segment
- **AND** SHALL 不调用未确认的 Milky Action 或假设存在等价 segment

#### Scenario: 混合消息中的单个转换失败

- **WHEN** 一条消息包含可转换 CQ 码、转换失败 CQ 码和普通文本
- **THEN** 失败 CQ 码 SHALL 以原始文本保留
- **AND** 其他可转换 CQ 码和普通文本 SHALL 按原顺序继续形成出站 segments

### Requirement: 未知或转换失败的 CQ 内容必须原样放行

未知 CQ 码、已知 CQ 码的字段解析失败、参数缺失、参数格式不符合转换器要求或转换器失败
时，系统 MUST 保留该 CQ 码的原始字符串作为 text segment，并继续处理整条消息。该 fallback
不得修改、截断、解码丢失或静默删除原始 CQ 内容；只有消息本身为空或其他独立的出站目标
校验失败时，才可返回既有本地错误。

#### Scenario: 非法 at ID 原样放行

- **WHEN** Agent 输出的 at 控制码缺少 qq 值或包含非法 ID
- **THEN** 出站 SHALL 将完整 at 控制码原样作为 text segment 保留
- **AND** SHALL 不因该 CQ 码单独阻止整条消息发送

#### Scenario: 未知 CQ 码原样放行

- **WHEN** Agent 输出当前未纳入契约的 CQ 码
- **THEN** 出站 SHALL 将该 CQ 码完整原样保留为 text segment
- **AND** SHALL 不把该 CQ 码转换成未确认的 Milky segment

#### Scenario: 转换器异常原样放行

- **WHEN** 已识别 CQ 码的转换器无法生成合法 Milky segment
- **THEN** 出站 SHALL 回退为该 CQ 码的原始 text segment
- **AND** SHALL 保留同一条消息中其他内容的顺序和内容
