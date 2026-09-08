## ADDED Requirements

### Requirement: 关系 ToolSpec 必须是固定且最小的入口

插件 MUST 只新增固定的关系查询和事件入口，不得开放任意关系数据库查询、任意 delta、任意
stage/flag 写入或任意 Milky Action catalog。至少提供 `get_relationship_state` 和
`record_relationship_event` 两个显式 ToolSpec；工具的 schema、工具集、描述和返回分类 MUST
在注册时固定，且不得因用户正文、关键词或 Will 动态创建新工具。

#### Scenario: Hermes 发现关系工具

- **WHEN** Hermes 加载插件并读取显式工具注册
- **THEN** 工具列表 SHALL 包含 `get_relationship_state` 和 `record_relationship_event`
- **AND** SHALL 不包含名为任意 delta、set stage、set flag 或 raw SQL 的工具

#### Scenario: 注册关系工具不联网

- **WHEN** Hermes 在注册阶段发现关系 ToolSpec
- **THEN** 插件 SHALL 只登记 schema、handler 和静态可用性检查
- **AND** SHALL 不打开事件流、不调用 Milky Action 或创建长期任务

### Requirement: Agent 关系工具只能作用于当前 Milky 会话主体

Agent Tool handler MUST 读取 Hermes session context，并要求
`HERMES_SESSION_PLATFORM=milky`。friend 的 `HERMES_SESSION_CHAT_ID` MUST 是合法 `dm:<id>`
且与 `HERMES_SESSION_USER_ID`（若存在）一致；group MUST 是合法 `group:<id>` 且必须存在当前
发送成员 `HERMES_SESSION_USER_ID`。工具不得接受覆盖 `self_id`、chat_id、group_id 或 member_id
的自由参数；Bot `self_id` 必须来自插件已确认的当前运行身份。缺少或冲突的 context MUST 返回
`missing_session_context` 或 `context_mismatch`，不得创建默认主体。

#### Scenario: 群聊 Agent 查询当前发送成员

- **WHEN** 群成员在 `group:<group_id>` 会话中调用 `get_relationship_state`
- **THEN** 工具 SHALL 只返回该 group_id 与当前 `HERMES_SESSION_USER_ID` 的关系
- **AND** SHALL 不允许模型改查同群其他成员

#### Scenario: 私聊上下文不接受伪造目标

- **WHEN** Agent Tool 参数试图将私聊关系目标改为另一个 user_id
- **THEN** 工具 SHALL 返回 `context_mismatch`
- **AND** SHALL 不读取或写入被伪造目标

#### Scenario: 缺少 session context

- **WHEN** Tool handler 在 scheduler、CLI 或旧宿主上下文中看不到合法 Milky session context
- **THEN** 工具 SHALL 返回 `missing_session_context`
- **AND** SHALL 不回退到最近会话、默认 QQ 号、默认群或 `HERMES_SESSION_ID` 推断目标

### Requirement: Agent 事件工具只能提交受限事件并返回事务结果

`record_relationship_event` MUST 只接受事件目录允许的 event code、`minor|normal` severity、
允许的 taste tag 和有限长度的非持久化 evidence；不得接受任意 numeric delta、stage、
overlay、flag、commitment 状态或自由 event code。工具 MUST 以当前 Hermes session context 的
`session_id + message_id + operation` 生成幂等键；缺少 `session_id` 或 `message_id` 时写操作
MUST 返回 `missing_idempotency_context`。成功时 MUST 返回 applied/duplicate、各维度安全 delta、
新 stage 和 overlays；失败时 MUST 返回稳定分类且不伪造状态。

#### Scenario: Agent 记录允许的互动

- **WHEN** Agent 在合法当前会话中记录 `kindness` 或 `preference_match` 的 normal 事件
- **THEN** 工具 SHALL 使用关系服务的固定规则提交一次事件
- **AND** SHALL 返回事务提交后的安全结果
- **AND** SHALL 不允许传入自定义分数

#### Scenario: Agent 记录严重越界被拒绝

- **WHEN** Agent Tool 使用 `critical`、`bond_milestone`、`clear_resentment` 或 commitment
  终态字段提交事件
- **THEN** 工具 SHALL 返回 `forbidden_source` 或 `invalid_arguments`
- **AND** SHALL 不改变关系状态

#### Scenario: Agent 重复调用保持幂等

- **WHEN** 同一个 session_id、message_id 和 operation 由于模型重试被调用两次
- **THEN** 第一次调用 SHALL 应用一次事件
- **AND** 第二次 SHALL 返回 duplicate 以及第一次结果，不得再次扣分

### Requirement: scheduler 服务调用必须显式声明目标和 event_id

插件内部 scheduler 可以直接调用关系服务，但 MUST 显式提供已确认的 `self_id`、scene、
scope_id、subject_id、event_id、source 和 occurred_at；scheduler 不得借用任意当前 Agent
session 推断目标。scheduler 才能提交 major/critical、创建或结算 commitment、设置
`bond_milestone` 等受信事实；所有输入仍 MUST 经过主体键、事件目录、时间和状态迁移校验。

#### Scenario: scheduler 记录跨会话结果

- **WHEN** 插件 scheduler 为一个已确认群成员提交带唯一 event_id 的 `promise_kept`
- **THEN** 服务 SHALL 使用显式 group_id/member_id 作用于该成员关系
- **AND** 不得读取 scheduler 进程中残留的其他 session context

#### Scenario: scheduler 缺少 event_id

- **WHEN** scheduler 省略或重复使用不符合域约束的 event_id
- **THEN** 服务 SHALL 返回 `invalid_event_id`
- **AND** SHALL 不写入事件账本或关系状态
