## ADDED Requirements

### Requirement: `set_group_member_special_title` 必须使用固定 operationId 和 Milky 参数

插件 MUST 注册名为 `set_group_member_special_title` 的异步 ToolSpec，使用 `milky` 工具集，
并且只调用 `POST /api/set_group_member_special_title`。工具参数 MUST 只有下列三个必填字段：
`group_id: integer`、`user_id: integer` 和 `special_title: string`。两个 QQ ID MUST 是不含布尔
值且范围为 `10001` 至 `4294967295` 的整数；`special_title` MUST 保持字符串类型并按原值
传递，包括空字符串，不得由插件自行 trim、改写或补默认值。工具 MUST 拒绝缺失字段、错误
类型、越界 ID 和额外字段，并在网络访问前返回 `invalid_input`。

#### Scenario: Hermes 发现群成员专属头衔工具

- **WHEN** Hermes 加载插件并读取显式 ToolSpec
- **THEN** 工具列表 SHALL 包含 `set_group_member_special_title`
- **AND** 该工具 SHALL 使用 `milky` 工具集并绑定同名 Milky operationId
- **AND** 注册阶段 SHALL 不发起 Milky HTTP 请求、SSE 连接或长期任务

#### Scenario: 专属头衔请求保留精确字段

- **WHEN** Agent 提供合法 `group_id`、`user_id` 和 `special_title` 调用工具
- **THEN** 系统 SHALL 向保留 path prefix 的 `<base>/api/set_group_member_special_title`
  发送一次 `POST` JSON 请求
- **AND** body SHALL 只包含三个同名字段及 Agent 提供的值
- **AND** SHALL 不因省略、群事件或本地缓存添加其他字段

#### Scenario: 非法专属头衔参数不触网

- **WHEN** Agent 缺少字段、传入布尔或字符串以外的值、使用范围外 QQ 号或添加未声明字段
- **THEN** 工具 SHALL 返回 `invalid_input`
- **AND** SHALL 不调用 Milky client、不发送 HTTP 请求且不修改本地群成员状态

### Requirement: 专属头衔变更必须只由显式调用触发并保留结果边界

`set_group_member_special_title` MUST 只在 Agent 显式提供完整参数并调用对应 ToolSpec 时提交。
普通消息正文、mention、关键词、Will 决策、群成员事件或其他 Tool 调用 MUST NOT 自动触发该
Action。成功响应 MUST 是完整的 Milky 成功 envelope 且 `data` 为确认的空 object；HTTP 200 但
协议失败 MUST 返回 `rejected`，成功响应的 `data` 不是空 object MUST 返回 `malformed`。请求
进入 HTTP 边界后若发生超时、连接中断、写入失败、读取失败或其他未知结果，工具 MUST 返回
`transport_unknown`，不得重试、换目标、伪造成功或更新本地群成员状态。日志只能记录必要的
安全业务 ID 和错误分类，不得记录 access token、Authorization、完整响应或完整
`special_title`。

#### Scenario: 群事件不自动设置专属头衔

- **WHEN** 系统收到群成员增加、群成员资料变更或其他群通知，或普通正文要求设置头衔
- **THEN** 系统 SHALL 不调用 `set_group_member_special_title`
- **AND** SHALL 等待 Agent 的明确 Tool 调用及完整参数

#### Scenario: 成功设置返回空对象 envelope

- **WHEN** 显式 Tool 调用得到 `status=ok`、`retcode=0` 且 `data` 为 `{}`
- **THEN** Tool 调用方 SHALL 收到完整成功 envelope
- **AND** 系统 SHALL 不虚构本地群成员头衔或其他状态

#### Scenario: 协议拒绝或响应结构错误

- **WHEN** Action 返回 HTTP 200 但协议 envelope 表示失败，或成功 envelope 的 `data` 非空 object
- **THEN** 工具 SHALL 分别返回 `rejected` 或 `malformed`
- **AND** SHALL 不把 HTTP 200 或非空响应当作成功

#### Scenario: 变更结果未知时不重试

- **WHEN** 请求已进入 HTTP 边界但客户端无法取得可确认的响应
- **THEN** 工具 SHALL 返回 `transport_unknown`
- **AND** 同一次 Tool 调用 SHALL 只提交一次 Action
- **AND** SHALL 不自动重发或返回成功结果
