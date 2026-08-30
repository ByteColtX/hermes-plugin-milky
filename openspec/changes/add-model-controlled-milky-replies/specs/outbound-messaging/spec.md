## MODIFIED Requirements

### Requirement: 文本和结构化内容由统一格式转换

出站普通文本和 CQ-compatible 控制码 MUST 按 Milky segment schema 生成。解析器 MUST 识别
NapCat 消息格式文档列出的 `text`、`face`、`image`、`record`、`video`、`at`、`rps`、`dice`、
`shake`、`poke`、`share`、`contact`、`location`、`music`、`reply`、`forward`、`node`、
`json`、`mface`、`file`、`markdown`、`lightapp`、`anonymous`、`redbag`、`gift`、`cardimage`、
`tts` 和 `xml` 类型。能确认映射时使用对应的 Milky outgoing segment；未知、无对应原生
segment 或转换失败时，必须使用完整原始 CQ 字符串生成 text segment。`[CQ:at,qq=<uid>]`
在成功转换时 MUST 映射为 mention segment，`[CQ:reply,id=<msg_id>]` 在成功转换时 MUST
映射为 reply segment；显式出站 file 仍不属于 message segment，必须走独立 `file_upload`；
空白消息 MUST 在网络访问前拒绝。

#### Scenario: 结构化消息

- **WHEN** Hermes 提供文本与结构化 outgoing segments
- **THEN** 请求 body SHALL 包含按原语义生成的 Milky segments
- **AND** adapter SHALL 不在生命周期代码中手工拼接不透明 Action body

#### Scenario: CQ-compatible 控制码

- **WHEN** Hermes 提供含有可确认转换的 at 或 reply CQ-compatible 控制码的文本
- **THEN** 请求 body SHALL 包含对应的 Milky mention 或 reply segment
- **AND** CQ-compatible 控制码本身 SHALL 不作为普通文本发送

#### Scenario: 全部文档 CQ 类型进入解析路径

- **WHEN** Hermes 提供 NapCat 文档列出的任一 CQ 类型
- **THEN** 系统 SHALL 识别该 CQ 类型并尝试形成 Milky outgoing segment
- **AND** 系统 SHALL 保留该 CQ 类型在消息中的原始顺序

#### Scenario: CQ 类型转换失败

- **WHEN** 已识别的 CQ 类型没有确认的 Milky 映射或转换过程失败
- **THEN** 系统 SHALL 使用完整原始 CQ 字符串生成 text segment
- **AND** SHALL 不静默丢弃该 CQ 内容或调用未确认的 Action

#### Scenario: 空白消息

- **WHEN** 出站内容为空或只包含空白
- **THEN** 发送 SHALL 返回本地输入错误
- **AND** SHALL 不访问网络

### Requirement: Agent 选择是否引用或提及

对于 Hermes 为普通 Agent 回复提供的隐式当前消息 reply anchor，出站边界 MUST 默认忽略该
anchor；只有消息正文中显式的合法 CQ-compatible 控制码或未来明确的结构化输入，才可以产生
mention 或 reply segment。没有显式控制码时，系统 MUST NOT 自动引用当前入站消息。

#### Scenario: 没有控制码的普通回复

- **WHEN** Agent 输出普通文本且 Hermes 同时提供当前消息的隐式 reply anchor
- **THEN** 出站请求 SHALL 只包含普通文本
- **AND** SHALL 不包含 reply segment

#### Scenario: 显式 reply 覆盖隐式 anchor

- **WHEN** Agent 输出 `[CQ:reply,id=9001]答复` 且 Hermes 提供另一个隐式 reply anchor
- **THEN** 出站请求 SHALL 只使用显式的 `9001` reply 目标
- **AND** SHALL 不追加隐式 anchor 对应的第二个 reply

#### Scenario: 显式 at 不改变引用状态

- **WHEN** Agent 输出 `[CQ:at,qq=101]答复` 且 Hermes 提供隐式 reply anchor
- **THEN** 出站请求 SHALL 包含 mention `101`
- **AND** SHALL 不因隐式 anchor 增加 reply segment

### Requirement: CQ-compatible 控制码未知或转换失败时原样放行

未知 CQ 码、malformed CQ-compatible 控制码、参数缺失以及已知 CQ 码转换失败时，系统 MUST
将完整原始 CQ 字符串保留为 text segment，并继续发送整条消息。该 fallback 不得触发额外
的 CQ 专用错误、通用文本 fallback、自动重试或第二次发送；目标非法、消息为空等独立的
出站校验仍按既有契约处理。

#### Scenario: malformed 控制码原样放行

- **WHEN** CQ-compatible at 或 reply 控制码的名称、参数或 ID 不符合语法
- **THEN** 发送内容 SHALL 包含完整原始 CQ 字符串对应的 text segment
- **AND** SHALL 不因该 CQ 片段单独阻止整条消息发送

#### Scenario: 未知控制码原样放行

- **WHEN** 文本包含尚未实现的 CQ-compatible 控制码
- **THEN** 发送内容 SHALL 包含未修改的原始 CQ 字符串 text segment
- **AND** SHALL 不把未知控制码转换成未确认的 Milky segment

#### Scenario: 已知 CQ 的转换器失败

- **WHEN** 已知 CQ 类型的字段符合基本格式但转换器无法生成合法 Milky segment
- **THEN** 发送内容 SHALL 回退为该 CQ 片段的原始 text segment
- **AND** 同一条消息的其他内容 SHALL 继续按原顺序发送
