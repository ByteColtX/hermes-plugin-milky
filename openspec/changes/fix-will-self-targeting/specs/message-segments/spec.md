## MODIFIED Requirements

### Requirement: 提及和回复信号必须可区分

规范化 SHALL 区分 mention self、mention all、mention here 和 none，并保留 reply 目标 ID；是否
提及 Bot 和是否引用 Bot SHALL 可独立判断。直接提及只有在 `mention.user_id` 等于当前消息的
`self_id` 时才是 self mention；遍历 `message.segments` 中的 `reply` segment 时，只有该
segment 的 `reply.data.sender_id` 等于当前消息的 `self_id` 时才是 self quote。当前消息的
`message.sender_id` 只表示引用者，不参与 self quote 判断。引用存在但 `reply.data.sender_id`
缺失、非法或不是 Bot 时，reply 存在性和 self quote SHALL 保持可区分，且不得把普通引用标记为
引用 Bot；`reply.data.segments` 中的 mention 不参与引用 Bot 判断。Milky v1.3 只有 `mention` 和 `mention_all`
segment，没有独立的 `mention_here` segment；对普通 v1.3 输入，normalizer MUST NOT 从普通文本
或 `mention` 的名称臆造 here 信号，只有未来被明确识别的协议扩展才可产生 here 信号。多个
提及信号 SHALL 保留为独立信号，不得因使用单一优先值而丢失 all 或 self。

#### Scenario: 提及 Bot 与全体提及

- **WHEN** 消息分别包含直接提及 Bot、`mention_all` 或 here 提及
- **THEN** 结果 SHALL 产生对应的 self、all 或 here mention kind
- **AND** routing SHALL 能按不同信号选择不同策略

#### Scenario: 提及其他用户不标记为 self mention

- **WHEN** `mention.user_id` 与当前消息的 `self_id` 不一致
- **THEN** 结果 SHALL 保留该 mention segment
- **AND** SHALL 不产生 self mention 信号或使用 Bot 的 mention routing

#### Scenario: 引用 Bot 的消息产生 self quote

- **WHEN** reply segment 提供目标 ID，且 `reply.data.sender_id` 等于当前消息的 `self_id`
- **THEN** 结果 SHALL 同时保留 reply 目标 ID 和 self quote 信号
- **AND** routing SHALL 可据此命中 `quote` 规则

#### Scenario: 引用他人的消息不标记为 self quote

- **WHEN** reply segment 的 `reply.data.sender_id` 与当前消息的 `self_id` 不一致
- **THEN** 结果 SHALL 保留 reply 目标 ID和 reply 存在性
- **AND** SHALL 不产生 self quote 信号或使用 Bot 的 quote routing

#### Scenario: reply.data.sender_id 未知时不猜测 Bot 目标

- **WHEN** reply segment 缺少、非法或无法确认 `reply.data.sender_id`
- **THEN** 结果 SHALL 保留可确认的引用目标和安全诊断
- **AND** SHALL 不产生 self quote 信号，不从正文、显示名称或嵌套内容推断引用 Bot

#### Scenario: 引用目标不可补全

- **WHEN** reply segment 只有目标 ID而远端原文尚未查询
- **THEN** 结果 SHALL 保留目标 ID
- **AND** SHALL 不将缺失的原文伪造成正文

#### Scenario: 引用目标正文尚未补全

- **WHEN** reply segment 提供协议要求的目标 ID，但远端原文尚未查询
- **THEN** 结果 SHALL 保留目标 ID
- **AND** SHALL 不将缺失的原文伪造成正文

#### Scenario: reply 缺少协议必填字段

- **WHEN** reply segment 的 `reply.data` 缺少 `message_seq`、`sender_id`、`time` 或 `segments`
- **THEN** 该 segment SHALL 保持 malformed 诊断
- **AND** SHALL 不伪造引用目标或把缺失字段当作普通文本

#### Scenario: reply 已经携带原文

- **WHEN** reply segment 的 `reply.data` 已提供 `message_seq`、`sender_id`、时间和嵌套 `segments`
- **THEN** 规范化 SHALL 保留这些内嵌信息
- **AND** trigger SHALL NOT 为同一 reply 强制重复调用 `get_message`

### Requirement: 规范化结果必须提供稳定策略特征

规范化 SHALL 在不重新读取 raw payload 的情况下提供稳定的有序正文和策略特征：至少包括事件
类型、场景、时间、正文/策略文本、独立的 self/all/here/none mention 信号、reply 存在性与
目标 ID、是否引用 Bot 的独立信号、image 存在性、typed segments、分类后的延迟引用
（`media_resource_references`、`file_attachment_references`、forward/reply references）和
安全诊断。text 与 markdown 内容 SHALL 按原顺序保留；合法的结构化 segment SHALL 使用可解释
占位；unknown segment SHALL 不进入正文或关键词内容。reply/forward 的嵌套内容 SHALL 保留为
引用数据，不得隐式并入当前消息正文。

#### Scenario: 复合 segment 生成策略特征

- **WHEN** friend 或 group 消息按顺序包含 text、mention、mention_all、reply、image 和 unknown
- **THEN** 规范化正文 SHALL 保持受支持内容顺序和可解释占位
- **AND** 策略特征 SHALL 独立报告 self/all mention、reply、self quote 和 image
- **AND** unknown SHALL 只进入安全诊断，不得进入正文或关键词匹配文本

#### Scenario: self quote 与普通 quote 可独立判断

- **WHEN** 一条消息的 reply segment 满足 `reply.data.sender_id == self_id`，另一条消息的 reply segment 指向其他用户
- **THEN** 两条结果 SHALL 都保留 reply 存在性和目标 ID
- **AND** 只有第一条结果 SHALL 报告 self quote

#### Scenario: 只有结构化内容

- **WHEN** 消息只包含合法 face、reply、image、record、video、file、forward、market_face、light_app、xml 或 markdown segment
- **THEN** 规范化结果 SHALL 保持为可处理的结构化消息
- **AND** SHALL 不因正文没有普通 text 而丢弃

#### Scenario: v1.3 不推断 mention here

- **WHEN** v1.3 消息只包含普通 text、mention 或 mention_all
- **THEN** mention 特征 SHALL 只报告 self、all 或 none
- **AND** SHALL 不从文本内容或 mention 名称生成 here 信号
