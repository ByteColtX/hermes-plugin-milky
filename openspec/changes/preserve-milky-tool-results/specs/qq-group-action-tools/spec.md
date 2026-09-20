# Spec Delta

## MODIFIED Requirements

### Requirement: 群文件查询结果必须保留完整成功 envelope

`get_group_file_download_url` 和 `get_group_files` 成功或失败时，只要取得远端响应体，Tool 调用方
都 SHALL 收到该响应体的完整原始内容。工具 MUST 保留未知 envelope、data、文件和文件夹字段，
不得执行成功结构校验、敏感字段过滤、容器转换、JSON 重建、摘要、普通消息投影或自动下载动作。
工具只返回远端响应体，不在调用中下载、缓存、解码或自动 materialize 文件；未取得远端响应体时，
才返回既有本地或传输分类。

#### Scenario: 获取群文件下载链接

- **WHEN** Agent 以合法 `group_id` 和 `file_id` 调用 `get_group_file_download_url`，远端返回包含下载链接或其他内容的响应体
- **THEN** Tool SHALL 返回完整原始响应体
- **AND** SHALL 保留远端返回的未知扩展字段
- **AND** SHALL 不直接读取或下载该 URL

#### Scenario: 获取群文件和文件夹列表

- **WHEN** Agent 调用 `get_group_files`，远端返回包含文件、文件夹数组或其他形状的响应体
- **THEN** Tool SHALL 返回完整原始响应体
- **AND** 响应中的协议字段和未知扩展字段 SHALL 保持可用
- **AND** SHALL 不把列表自动写入入站上下文或本地缓存

#### Scenario: 查询结果缺少历史最小结构

- **WHEN** 响应体缺少 `data.download_url`、`data.files`、`data.folders`，或不是 JSON object
- **THEN** 工具 SHALL 将已取得的响应体原样交给 Tool 调用方
- **AND** SHALL 不返回 `malformed` 替代结果、查询成功摘要或伪造缺失字段

#### Scenario: 查询结果缺少最小结构

- **WHEN** 成功响应缺少 `data.download_url`，或 `data.files`/`data.folders` 不是对象数组
- **THEN** 工具 SHALL 返回已取得的原始响应体
- **AND** SHALL 不报告查询成功或伪造缺失字段

### Requirement: 群管理 Action 必须保留确定性错误边界且不得盲目重试

群请求和群邀请的接受/拒绝属于可能改变远端状态的 Action。只要请求取得远端响应体，无论其
HTTP 状态、协议状态或数据结构为何，工具 MUST 原样返回该响应体；不得由插件校验、重建、过滤
或替换为 `rejected`、`http_error`、`malformed` 或成功结果。请求进入 HTTP 边界后，如果未取得
响应体、超时、连接中断、写入失败或读取失败，工具 MUST 返回 `transport_unknown`，不得重试、
换目标或伪造成功；错误日志 MUST 不包含认证凭证、完整异常正文、下载 URL 或敏感自由文本。

#### Scenario: 群请求 Action 的结果未知

- **WHEN** 接受或拒绝群请求/邀请的请求已进入 HTTP 边界，但客户端未取得远端响应体
- **THEN** 工具 SHALL 返回 `transport_unknown`
- **AND** 同一次 Tool 调用 SHALL 不再次提交该 Action

#### Scenario: 远端协议拒绝群操作

- **WHEN** 群请求或群邀请 Action 返回 HTTP 200 但协议 envelope 表示失败
- **THEN** Tool 调用方 SHALL 收到完整原始响应体
- **AND** SHALL 不把 HTTP 200 当作成功，也 SHALL 不改造成固定 `rejected` 结果

#### Scenario: 成功管理结果保留协议边界

- **WHEN** 接受或拒绝群请求/邀请返回成功 envelope、非空 data、未知字段或其他可获得响应体
- **THEN** Tool 调用方 SHALL 收到完整原始响应体
- **AND** 插件 SHALL 不虚构本地请求状态或远端对象

### Requirement: 专属头衔变更必须只由显式调用触发并保留结果边界

`set_group_member_special_title` MUST 只在 Agent 显式提供完整参数并调用对应 ToolSpec 时提交。
普通消息正文、mention、关键词、Will 决策、群成员事件或其他 Tool 调用 MUST NOT 自动触发该
Action。只要取得远端响应体，Tool 调用方 SHALL 收到完整原始响应体，无论其是否为成功 envelope、
空 object、协议失败或其他 JSON 形状；插件不得校验、过滤、重建或替换响应体。请求进入 HTTP
边界后若未取得远端响应体，工具 MUST 返回 `transport_unknown`，不得重试、换目标、伪造成功
或更新本地群成员状态。日志只能记录必要的安全业务 ID 和错误分类，不得记录 access token、
Authorization、完整响应或完整 `special_title`。

#### Scenario: 群事件不自动设置专属头衔

- **WHEN** 系统收到群成员增加、群成员资料变更或其他群通知，或普通正文要求设置头衔
- **THEN** 系统 SHALL 不调用 `set_group_member_special_title`
- **AND** SHALL 等待 Agent 的明确 Tool 调用及完整参数

#### Scenario: 成功设置返回远端响应

- **WHEN** 显式 Tool 调用得到成功 envelope、`data` 为 `{}` 或包含扩展字段的响应体
- **THEN** Tool 调用方 SHALL 收到完整原始响应体
- **AND** 系统 SHALL 不虚构本地群成员头衔或其他状态

#### Scenario: 成功设置返回空对象 envelope

- **WHEN** 显式 Tool 调用得到 `status=ok`、`retcode=0` 且 `data` 为 `{}`
- **THEN** Tool 调用方 SHALL 收到完整原始响应体
- **AND** 系统 SHALL 不虚构本地群成员头衔或其他状态

#### Scenario: 协议拒绝或响应结构错误

- **WHEN** Action 返回 HTTP 200 但协议 envelope 表示失败，或成功 envelope 的 `data` 非空 object
- **THEN** Tool 调用方 SHALL 收到完整原始响应体
- **AND** SHALL 不把 HTTP 200 或非空响应改写成成功、`rejected` 或 `malformed`

#### Scenario: 变更结果未知时不重试

- **WHEN** 请求已进入 HTTP 边界但客户端未取得远端响应体
- **THEN** 工具 SHALL 返回 `transport_unknown`
- **AND** 同一次 Tool 调用 SHALL 只提交一次 Action
- **AND** SHALL 不自动重发或返回成功结果
