## ADDED Requirements

### Requirement: `get_friend_info` 必须使用固定 operationId 和明确参数

插件 MUST 注册名为 `get_friend_info` 的异步 ToolSpec，使用 `milky` 工具集，并且只调用
`POST /api/get_friend_info`。工具 MUST 只接受必填的 `user_id: integer`；该值 MUST 是不含
布尔值、范围为 `10001` 至 `4294967295` 的 QQ 号。工具 MUST 拒绝缺失字段、错误类型、越界
值和额外字段，并在网络访问前返回 `invalid_input`；不得从好友名称、入站正文或当前会话推断
`user_id`。

#### Scenario: Hermes 发现好友信息工具

- **WHEN** Hermes 加载插件并读取显式 ToolSpec
- **THEN** 工具列表 SHALL 包含 `get_friend_info`
- **AND** 该工具 SHALL 使用 `milky` 工具集并绑定 `get_friend_info` operationId
- **AND** 注册阶段 SHALL 不发起 Milky HTTP 请求、SSE 连接或长期任务

#### Scenario: 好友信息请求使用精确 body

- **WHEN** Agent 以合法 `user_id` 调用 `get_friend_info`
- **THEN** 系统 SHALL 向保留 path prefix 的 `<base>/api/get_friend_info` 发送一次 `POST` JSON 请求
- **AND** 请求 body SHALL 只包含 `{ "user_id": <user_id> }`
- **AND** SHALL 不添加未由目标 operation 契约确认的可选字段或默认值

#### Scenario: 非法好友信息参数不触网

- **WHEN** Agent 缺少 `user_id`、传入布尔值、错误类型、范围外 QQ 号或未声明字段
- **THEN** 工具 SHALL 返回 `invalid_input`
- **AND** SHALL 不调用 Milky client、不发送 HTTP 请求且不记录远端结果

### Requirement: `get_friend_info` 必须保留经过校验的完整查询结果

`get_friend_info` 成功时 MUST 向 Tool 调用方返回完整的 Milky 成功 envelope。由于当前公开
Milky v1.3 schema 未声明该 operation，插件 MUST 只把非空的 JSON object `data` 作为本地最小
结构进行校验，不得擅自规定或改写好友资料内部字段；已确认和未知的 envelope/data 字段都
MUST 保留。`data` 缺失、为 `null`、不是 object，或 envelope 表示协议失败时，工具 MUST 分别
返回 `malformed` 或 `rejected`，不得报告假成功。查询结果不得自动写入普通入站上下文、本地
好友状态或 Agent 指令。

#### Scenario: 返回好友资料对象和扩展字段

- **WHEN** 目标服务返回 `status=ok`、`retcode=0` 且 `data` 为好友资料 JSON object
- **THEN** Tool SHALL 收到完整成功 envelope
- **AND** `data` 内的好友资料字段及未知扩展字段 SHALL 保持可用
- **AND** 插件 SHALL 不把结果改造成摘要、正文或本地缓存状态

#### Scenario: 查询结果结构未确认或损坏

- **WHEN** 成功 envelope 的 `data` 缺失、为 `null`、为数组或其他非 object
- **THEN** 工具 SHALL 返回 `malformed`
- **AND** SHALL 不伪造好友资料、不补默认字段且不向 Agent 报告成功

#### Scenario: HTTP 200 仍表示协议拒绝

- **WHEN** `get_friend_info` 返回 HTTP 200 但 envelope 的 `status` 非 `ok` 或 `retcode` 非零
- **THEN** 工具 SHALL 返回 `rejected`
- **AND** SHALL 不把 HTTP 状态码当作查询成功
