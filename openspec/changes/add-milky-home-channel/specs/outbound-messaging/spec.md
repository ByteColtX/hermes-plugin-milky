## MODIFIED Requirements

### Requirement: 出站目标按命名空间路由

`group:<id>` MUST 使用 `send_group_message`，`dm:<id>` MUST 使用 `send_private_message`；`MILKY_HOME_CHANNEL` 只能由 Hermes core/cron 在调用 adapter 前解析为这两种完整 chat key，adapter MUST NOT 将空目标或任意 `home` 标记隐式转换为 home channel。临时会话目标和其他非法目标 MUST 返回 `unsupported` 或本地目标校验失败；目标解析失败 MUST 在网络访问前返回且不得回退默认频道、home channel 或其他目标。

#### Scenario: 群消息发送

- **WHEN** Hermes 向合法 `group:<id>` 目标发送非空消息
- **THEN** 系统 SHALL 调用 `send_group_message`
- **AND** 请求 SHALL 使用该群 ID 而不是默认目标

#### Scenario: 临时会话目标

- **WHEN** Hermes 向临时会话目标发送消息
- **THEN** 发送 SHALL 在网络访问前返回 `unsupported`
- **AND** SHALL 不调用私聊 Action 或群聊 Action

#### Scenario: 非法目标

- **WHEN** 目标为空、负数、非数字或包含额外分隔符
- **THEN** 发送 SHALL 在网络访问前失败
- **AND** SHALL 不回退为 dm、默认目标、home channel 或其他目标

#### Scenario: 系统消息使用已解析的 home target

- **WHEN** Hermes 已将 `MILKY_HOME_CHANNEL` 解析为合法 `group:<id>` 或 `dm:<id>`，再向 adapter 发送系统消息
- **THEN** 系统 SHALL 按该 chat key 的命名空间选择对应 Milky Action
- **AND** adapter SHALL 不重新读取环境变量或改变该目标
