## Why

当前文件入站引用已经保留 `file_hash`，但文件正文 placeholder 只展示 `file_id` 和
`file_name`，导致 Agent 无法从上下文直接识别私聊文件查询所需的 TriSHA1。Milky v1.3.0
还提供了群文件查询、群请求和群邀请操作，而插件尚未将这些 operationId 纳入固定 ToolSpec，
因此需要补齐可审计的显式能力边界。

## What Changes

- 将入站文件 placeholder 扩展为同时展示 `file_id`、`file_name` 和 `file_hash`；缺失或为
  `null` 的值使用现有 `NOT SUPPORTED` 占位，不伪造哈希。
- 新增以下 6 个与 Milky v1.3.0 operationId 一一对应的固定 ToolSpec：
  - `get_group_file_download_url`
  - `accept_group_request`
  - `reject_group_request`
  - `accept_group_invitation`
  - `reject_group_invitation`
  - `get_group_files`
- 按 Milky OpenAPI 固定各工具的必填字段、枚举、数值范围、nullable 可选字段和
  `additionalProperties: false`；可选字段省略时不由插件自行补默认值。
- 查询工具保留完整成功 envelope、文件下载 URL、群文件/文件夹数组和未知扩展字段；群请求
 及邀请处理工具只允许显式调用，并保留协议拒绝和传输未知结果。
- 所有工具继续通过现有 client/sender 边界访问对应 `/api/{operationId}`，在网络访问前校验
  参数；不开放任意 Action catalog，不从入站事件、正文、关键词或 Will 隐式触发操作。
- 更新 manifest、ToolSpec 文档、脱敏协议 fixture、工具注册/调用测试、文件 placeholder
  测试和 OpenSpec 证据台账。

## Capabilities

### New Capabilities

- `qq-group-action-tools`: 为 Hermes Agent 提供群文件下载、群文件列表、入群请求和群邀请
  的 6 个固定 Milky ToolSpec。

### Modified Capabilities

- `message-segments`: 文件 placeholder 增加 `file_hash`，并对缺失哈希保持明确的安全占位。

## Impact

- 影响 `inbound/extractor.py` 的文件 placeholder，以及 `outbound/tools.py`、
  `outbound/sender.py`、`milky/client.py` 的 ToolSpec、handler、sender 委托和 Action 校验。
- 影响 `plugin.yaml`、`README.md`、`ARCHITECTURE.md` 和 `skills/qq-tools/SKILL.md` 中的固定
  工具清单与参数说明；固定 ToolSpec 数量由 17 个扩展为 23 个。
- 新增合成 Milky v1.3.0 请求/响应 fixture，覆盖查询成功 envelope、空对象管理结果、非法
  参数、协议拒绝、HTTP/非 JSON/transport unknown、未知字段保留和日志脱敏。
- 群请求、群邀请的接受/拒绝属于可能改变远端状态的操作；本 change 不引入自动处理、审批
  队列、本地群状态同步或自动重试。
