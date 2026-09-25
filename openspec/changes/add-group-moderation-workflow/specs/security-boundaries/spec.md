# Spec Delta

## MODIFIED Requirements

### Requirement: QQ Tool 远端响应原样交付

全部已注册 Tool，包括名片赞、好友和群戳一戳、群消息撤回、群信息、群成员列表、群成员信息、
成员禁言、全员禁言、合并转发、私聊和群文件下载链接、群文件列表、好友请求查询与处理、好友信息、
删除好友、踢出成员、退群、群请求与群邀请处理和专属头衔，只要取得远端响应体，就 MUST 把该
响应体原样交给 Hermes core 作为 Tool 结果。该规则适用于成功 envelope、协议拒绝、非 2xx HTTP
状态、非对象 JSON、数组、标量、显式 `null`、非 JSON 文本、空 body 和其他任何可获得的响应体。
插件 MUST NOT 依据 HTTP 状态或响应内容将结果改造成摘要 DTO、插件状态、固定错误或附加状态码的
包装对象，MUST NOT 对结果执行任何脱敏（包括按键名剔除、掩码或改名 `access_token`、
`authorization`、`cookie`、`password`、`token` 等字段），也不得为了生成日志而过滤、遍历、
冻结、复制、重构或摘要该结果。响应体转换为 Hermes
core 可接受的字符串时 SHALL 使用 UTF-8 解码，无法解码的字节 SHALL 以替换字符表示并仍然交付。

Hermes core 在插件交付之后对 Tool 结果执行的变换（`transform_tool_result` hook、JSON `error`
字段截断、超长结果落盘替换为预览）不在本契约范围内；插件 MUST NOT 注册 `transform_tool_result`，
MUST NOT 尝试规避或还原这些变换，也 MUST NOT 宣称最终进入模型上下文的内容与远端响应一致。

#### Scenario: Tool 返回任意可获得的远端响应

- **WHEN** 任一已注册 Tool 的远端 Action 返回任意 HTTP 状态和响应体
- **THEN** Tool 调用方 SHALL 收到内容不变的远端响应体
- **AND** 结果中的数组、显式 `null`、未知字段以及 `access_token`、`authorization`、`cookie`、`password`、`token` 等敏感键 SHALL 保持可用，不被剔除、掩码或改名
- **AND** 结果 SHALL 不包含插件附加的状态码、分类或包装字段

#### Scenario: 远端响应体不是预期 envelope

- **WHEN** 远端响应体是非 JSON 文本、JSON 数组、JSON 标量、空 body 或未知 envelope
- **THEN** Tool SHALL 仍将已取得的响应体原样交给 Tool 调用方
- **AND** SHALL 不将其归类为插件自有 `malformed` 结果或补造 envelope

#### Scenario: Tool 没有远端结果

- **WHEN** 参数校验失败、Action 未注册、client 未绑定或已关闭，或传输没有取得远端响应体
- **THEN** Tool SHALL 返回既有固定错误分类
- **AND** SHALL 不伪造远端成功结果
- **AND** 日志是否存在 SHALL 不改变该结果

#### Scenario: Tool 返回成功协议结果

- **WHEN** 已注册 Tool 的远端 Action 返回成功协议结果
- **THEN** Tool 调用方 SHALL 收到未重构的原始协议结果
- **AND** 日志 MAY 记录该调用的 Tool 名称、固定结果分类、状态码和耗时
- **AND** 日志 SHALL NOT 记录入参、结果 body、下载 URL 或媒体字段

#### Scenario: 响应体含非 UTF-8 字节

- **WHEN** 远端响应体包含无法按 UTF-8 解码的字节
- **THEN** Tool SHALL 用替换字符表示这些字节并交付其余内容
- **AND** SHALL 不返回插件本地错误分类

#### Scenario: Hermes core 后置处理不改变插件契约

- **WHEN** Hermes core 或其他插件通过 `transform_tool_result`、`error` 字段截断或结果落盘改写插件已交付的 Tool 结果
- **THEN** 插件交付给 core 的值 SHALL 仍与远端响应体内容一致
- **AND** 插件 SHALL 不注册 `transform_tool_result`，也不尝试还原被 core 改写的结果

recall_group_message、set_group_member_mute 和 kick_group_member MUST 在网络处置前共用群管案件授权、真实目标、角色、时效和动作防重检查。缺少可信案件关联、权限或参数不符返回 blocked；可信合法方案等待 Web 批准返回 pending_review 和不透明案件标识。此例外只扩展无处置响应时的本地分类，不改变实际远端响应原样交付，也不得为了案件日志解析不透明 Tool 响应。

#### Scenario: 群管工具未获准

- **WHEN** 三个群管工具之一被调用，但尚无业务授权或可信案件关联
- **THEN** 系统 SHALL 返回 blocked 或合法待审方案的 pending_review，不调用处置 Action
- **AND** SHALL 不因聊天正文、工具参数中的声明或宿主长期批准而跳过检查

#### Scenario: 工具与后台争用同一方案

- **WHEN** 群管工具和后台执行者尝试执行同一已获准案件动作
- **THEN** 最多一方 SHALL 提交 Action，另一方返回已有案件状态或 blocked
- **AND** 已提交 Tool 的远端响应 SHALL 原样交付，不能以案件摘要替换

## ADDED Requirements

### Requirement: 群管短期证据必须与日志及执行记录隔离

系统 MUST 仅为本地命中案件在当前 profile 的独立受控证据区保存必要命中正文和有界上下文，供模型复核及认证 Web 审阅。该业务证据最多保留 24 小时、每 profile 总量最多 64 MiB，仅允许运行账户访问；响应 MUST 禁止缓存，前端按纯文本显示且不自动加载媒体。不得保存已知凭证、媒体 URL、其他 URL、附件 bytes、模型原文或原始工具参数/结果；过滤、截断与缺失 MUST 明示，证据不足不得自动处罚。此例外不允许在日志、异常、fixture、快照输出或持久执行记录保存敏感正文。

#### Scenario: Web 读取具体案件证据

- **WHEN** 当前已认证操作者读取所属 profile 的未过期案件
- **THEN** 系统 SHALL 仅提供该案受控纯文本证据及完整性状态，不回显秘密或其他 profile 数据
- **AND** 日志与执行记录 SHALL 只引用案件和证据标识，不复制正文

#### Scenario: 到期或超额

- **WHEN** 证据已到 24 小时，或新增证据将突破 64 MiB 配额
- **THEN** 系统 SHALL 分别清理到期证据或拒绝新案件并标记覆盖缺口，不静默删除有效证据再报告完整审阅
