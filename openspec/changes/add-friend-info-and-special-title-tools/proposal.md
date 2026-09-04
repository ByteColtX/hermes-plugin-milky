## Why

当前固定 ToolSpec 已能查询好友请求和群成员信息，但不能查询指定好友资料，也不能设置群
成员专属头衔。补充这两个明确的 Milky operationId 后，Agent 可以通过现有可审计的工具边界
完成对应能力，不需要暴露任意 Action catalog 或绕过统一错误处理。

## What Changes

- 新增 `get_friend_info` ToolSpec，显式调用 `POST <base>/api/get_friend_info`，只接受合法
  `user_id`，成功时保留完整 Milky envelope 和好友资料对象。
- 新增 `set_group_member_special_title` ToolSpec，显式调用
  `POST <base>/api/set_group_member_special_title`，传递 `group_id`、`user_id` 和
  `special_title` 三个字段；不自动补默认值或修改本地群成员状态。
- 将两个 operationId 加入 `milky/client`、outbound sender、工具注册和 manifest 的固定
  白名单；继续在网络前拒绝错误类型、范围、缺失字段和额外字段。
- 为查询成功、管理成功、协议拒绝、malformed、HTTP 错误和
  `transport_unknown` 增加脱敏 fixture 与回归测试；状态变更结果未知时不重试。
- 更新工具能力清单、架构说明和相关 OpenSpec 契约。当前官方 Milky v1.3 文档明确列出
  `set_group_member_special_title` 的三个字段，但没有列出 `get_friend_info`；实现前必须以
  目标服务的 operation 契约确认后者的返回字段，未确认字段不进入本地 DTO 或默认值推断。

## Capabilities

### New Capabilities

无。两个接口都属于现有固定 QQ 工具能力范围。

### Modified Capabilities

- `qq-action-tools`：增加 `get_friend_info` 查询工具及其参数、完整对象 envelope 和错误边界。
- `qq-group-action-tools`：增加 `set_group_member_special_title` 群成员管理工具及其显式
  调用、参数和未知结果边界。

## Impact

- 影响 `plugin.yaml`、`outbound/tools.py`、`outbound/sender.py` 和 `milky/client.py` 的
  固定工具注册、Action 白名单、参数校验与结果校验。
- 影响 `tests/test_qq_tools.py`、QQ 工具 schemas/request/response fixture，以及 manifest、
  README 和 `ARCHITECTURE.md` 中的工具数量和能力清单。
- 不新增依赖、配置项、入站事件处理或 Hermes core 修改；不改变现有 Gate、Will、普通消息
  流程和附件边界。
- `set_group_member_special_title` 会产生远端状态变化，只能由完整 Tool 调用触发；
  `get_friend_info` 的查询结果只交付给 Tool 调用方，不写入普通入站上下文或本地状态。
