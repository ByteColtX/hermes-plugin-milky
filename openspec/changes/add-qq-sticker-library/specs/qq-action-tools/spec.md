## ADDED Requirements

### Requirement: Sticker tools MUST be fixed local-library ToolSpecs

Milky plugin MAY 在现有 `milky` toolset 中注册固定的 `sticker_categories`、`sticker_search`、
`sticker_send` 和 `sticker_forget`。自动 sticker collection SHALL 是内部旁路，不得注册为 Agent Tool；
这些工具 SHALL 使用稳定的本地 library 契约，不得伪装成未确认的 Milky operationId，不得开放任意
Action catalog，也不得因普通消息、关键词、Will 或系统事件隐式执行发送、删除或维护动作。
`sticker_search` 和 `sticker_send` SHALL 沿用 `add-sticker-search-and-id-send` 的
intent/emotion/tags、limit、opaque ID 和互斥查询/ID 契约；本 change 不重新定义 category、keyword
或 index 参数。

#### Scenario: Tool registration has no network side effect

- **WHEN** Hermes 在注册阶段发现 sticker tools
- **THEN** 插件 SHALL 只登记 schema、handler 和 availability check
- **AND** SHALL 不建立 Milky client、SSE、视觉调用、长期任务或远端资源请求

#### Scenario: Automatic collection is not an Agent mutation tool

- **WHEN** 当前消息包含一张经过 resource resolver materialize 的图片
- **THEN** 系统 MAY 由内部质量流水线自动判断并入库
- **AND** Agent SHALL 不需要也不能通过 Tool 参数触发该内部入库流程
- **AND** 自动收集失败 SHALL 不伪造 Tool 成功或改变普通消息 handoff

#### Scenario: Ordinary message cannot invoke send or forget

- **WHEN** 普通消息只包含图片、关键词或 Will decision
- **THEN** 系统 SHALL 不自动执行 `sticker_send`、`sticker_forget` 或维护命令
- **AND** 发送和删除状态变化 SHALL 只能来自显式固定工具或既有显式维护命令

### Requirement: Sticker ToolSpec arguments MUST be strict and bounded

`sticker_categories` MUST 不接受参数；`sticker_search` MUST 只接受其既有契约声明的
`intent`、`emotion`、`tags` 和 `limit`；`sticker_send` MUST 接受互斥的既有查询模式或单独
`sticker_id`；`sticker_forget` MUST 只接受当前可见自动条目的 opaque `sticker_id`。所有 schema
MUST 拒绝额外字段、空字符串、布尔冒充整数、超长文本、任意 scope、目标、路径、URL 或超出上限
的列表；非法输入 SHALL 在读取图片或发送网络 Action 前返回 `invalid_input`。

#### Scenario: Unknown ToolSpec field is rejected

- **WHEN** Agent 向任一 sticker tool 传入未声明字段、category、keyword、index、scope 或 target
- **THEN** 工具 SHALL 返回 `invalid_input`
- **AND** SHALL 不改变数据库、文件或远端会话

#### Scenario: Sticker ID is treated as opaque

- **WHEN** Agent 传入格式异常、已删除、不可见或不是当前可解析结果的 `sticker_id`
- **THEN** 工具 SHALL 返回 `sticker_not_found`、`not_found` 或 `invalid_input`
- **AND** SHALL 不把该值解释为路径、URL、资源 URI、内容 hash 或 Milky Action 名称

#### Scenario: Forget is limited to current automatic scope

- **WHEN** Agent 使用当前会话可见的自动 `sticker_id` 调用 `sticker_forget`
- **THEN** 工具 SHALL 只删除当前自动作用域的 entry
- **AND** SHALL 不删除手动共享条目、其他会话的 entry 或仍被引用的共享 asset

#### Scenario: Forget does not replace manual maintenance

- **WHEN** Agent 使用手动 `/milky sticker` 库条目的 ID 调用 `sticker_forget`
- **THEN** 工具 SHALL 返回 `unsupported` 或 `unauthorized`
- **AND** SHALL 要求通过既有显式 `sticker del` 维护路径处理手动条目

### Requirement: Sticker send ToolSpec MUST account for one network side effect

`sticker_send` 在选定条目、完成文件校验并进入发送边界后 MUST 最多调用一次现有 Milky native image
send；使用统计 SHALL 在发起发送调用后 claim 一次。成功、拒绝、未知和不支持结果 SHALL 保持既有
出站错误分类；工具不得通过多次重试规避未知结果，也不得在工具结果中伪造成功消息序号。

#### Scenario: Native send succeeds

- **WHEN** 当前可见 sticker 被选中且 native image send 返回可确认成功
- **THEN** Tool SHALL 返回既有成功状态和受限发送回执
- **AND** library 使用统计 SHALL 已只更新一次

#### Scenario: Native send has unknown result

- **WHEN** native image send 已进入网络边界但结果未知
- **THEN** Tool SHALL 返回 `transport_unknown` 或对应既有分类
- **AND** SHALL 不重发
- **AND** 已发起调用的使用统计 SHALL 不因未知结果回滚

#### Scenario: Send target is not current session

- **WHEN** 工具内部状态试图把 sticker 发往其他群、好友、temp 目标或未确认目标
- **THEN** Tool SHALL 在网络 Action 前返回 `unauthorized`、`invalid_input` 或 `unsupported`
- **AND** SHALL 不调用 Milky send Action
