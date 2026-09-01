## Why

当前插件已经注册了一组显式 QQ ToolSpec，但转发详情、私聊文件下载链接、群成员管理和好友关系管理仍无法由 Agent 按需调用。Milky v1.3.0 已确认这些 operationId 及其请求字段，补齐固定工具可以让需要明确业务意图的查询和管理操作通过统一的参数校验、协议 envelope 和错误边界执行。

## What Changes

- 新增 `get_forwarded_messages`、`get_private_file_download_url`、`kick_group_member` 和 `quit_group` 四个显式 ToolSpec。
- 新增 `delete_friend`、`get_friend_requests`、`accept_friend_request` 和 `reject_friend_request` 四个好友相关显式 ToolSpec。
- 为每个工具按 Milky v1.3.0 schema 固定必填字段、类型、数值范围、可选字段和禁止的额外字段，并在 HTTP 请求前拒绝非法输入。
- 通过现有 Milky Action client/sender 边界调用对应 `/api/{operationId}`；成功结果保留完整 envelope、未知字段和协议业务值。
- 统一处理未连接、协议拒绝、HTTP 错误、非 JSON、字段缺失和传输未知结果；可能产生副作用的管理操作不自动重试，也不由入站事件或普通正文隐式触发。
- 更新工具发现、plugin manifest、脱敏协议 fixture、ToolSpec 单元/集成回归和按任务记录的质量证据。
- 不新增任意 Milky Action catalog，不自动批准或拒绝好友请求事件，不把好友请求或群管理工具变成入站 Agent 触发器。

## Capabilities

### New Capabilities

- `qq-action-tools`: 为 Hermes Agent 提供 8 个与 Milky v1.3.0 operationId 对齐的固定 QQ 查询和管理工具。

### Modified Capabilities

- `security-boundaries`: 为包含私聊文件下载 URL 或敏感拒绝理由的 Tool 结果增加审计日志排除边界，同时保留 Tool 调用方接收完整成功 envelope 的行为。

现有 `milky-http-actions` 已规定所有 Action 的 POST、认证、envelope、参数前置校验和错误分类；本 change 只新增遵守这些通用边界的工具覆盖，不改变其 requirement。

## Impact

- 影响 `outbound/tools.py`、`outbound/sender.py`、`milky/client.py`，必要时扩展 `milky/models.py` 和解析器以承载协议确认的只读结果。
- 影响根入口工具注册、`plugin.yaml` 的 `provides_tools` 和 QQ tools 文档；注册阶段仍不得联网或创建长期任务。
- 新增协议 fixture 和测试，覆盖 8 个请求 body、成功/失败 envelope、未知字段保留、缺失字段、非法参数、未连接和 `transport_unknown`。
- 群踢人、退群、删除好友、同意/拒绝好友请求属于可能改变远端状态的 Action；本 change 只允许显式 Tool 调用到达 Milky，不新增事件自动化或隐式授权机制。
