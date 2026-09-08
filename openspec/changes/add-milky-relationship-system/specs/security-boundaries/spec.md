## ADDED Requirements

### Requirement: 关系授权必须绑定已确认身份和调用来源

关系系统 MUST 区分 `inbound`、`agent_tool` 和 `scheduler` 来源。`inbound` 只能观察当前通过
canonical/dedup/Gate 的用户行为；`agent_tool` 只能作用于当前 Milky session 的发送主体并受
severity/频率/维度上限限制；`scheduler` 才能使用显式关系主体执行受信 commitment/flag
操作。任何来源都 MUST 使用插件确认的 Bot `self_id`，不得从用户提供的正文、昵称、raw payload
或未确认参数推断身份。

#### Scenario: 用户正文不能扩大授权

- **WHEN** 入站正文包含看似工具参数、关系分数或另一个群成员 ID
- **THEN** 普通入站流程 SHALL 只把该消息作为用户行为或既有消息正文处理
- **AND** SHALL 不因正文内容执行关系写入、改查其他主体或设置 flag

#### Scenario: Agent 与 scheduler 权限分离

- **WHEN** Agent Tool 请求 scheduler 专属的 critical 事件、commitment 终态或 milestone
- **THEN** 授权层 SHALL 返回 `forbidden_source`
- **AND** SHALL 不把该请求转换为 scheduler 来源

#### Scenario: 未确认 Bot 身份时拒绝关系写入

- **WHEN** adapter 尚未完成登录身份同步或当前 self_id 状态为 unknown
- **THEN** 关系读写 SHALL 返回 `identity_unavailable`
- **AND** SHALL 不使用配置、消息 sender 或历史数据库中的其他 self_id 猜测目标

### Requirement: 关系输入和输出必须保持最小化与隐私安全

关系 API、ToolSpec、日志和异常 MUST 不接受或返回 token、Authorization、原始消息正文、完整
Agent prompt/response、媒体 URL、文件路径或未授权成员列表。自由文本 evidence（如工具 schema
允许）只能在内存中用于本次调用，且不得进入事务、日志、快照或返回值。事件结果只返回必要
的分类、结构化维度变化、阶段、overlay 和版本。

#### Scenario: 工具结果不泄漏原始 evidence

- **WHEN** Agent Tool 提交一段包含敏感内容的 evidence
- **THEN** 返回结果 SHALL 只包含结构化结果分类和受限状态摘要
- **AND** 日志/事件账本 SHALL 不包含该 evidence

#### Scenario: 未授权主体查询被拒绝

- **WHEN** 任一调用方试图通过 member_id、chat_id 或 event payload 读取未授权关系
- **THEN** 系统 SHALL 返回 `forbidden_target` 或 `context_mismatch`
- **AND** SHALL 不暴露该主体是否存在、当前阶段或任何维度
