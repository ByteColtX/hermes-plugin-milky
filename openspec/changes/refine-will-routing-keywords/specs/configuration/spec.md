## MODIFIED Requirements

### Requirement: Will 和缓冲配置保持嵌套且可验证

`MILKY_WILL_POLICY` MUST 支持完整嵌套的 `engine`、`routing`、`willingness` 和 `priority`
字段；routing MUST 支持 `direct`、`mention`、`mentionAll`、`quote`、`poke` 和
`allMessage` 六个 `wait`/`trigger` 动作字段，以及 `keywords` 字符串数组。routing
MUST NOT 接受 `group`、`image` 或 `mentionHere` 字段。省略 Will policy 时 SHALL 使用
架构定义的完整默认 routing，其中 `allMessage` SHALL 为 `wait` 且 `keywords` SHALL
为空数组；`MILKY_SESSION_BUFFER_SIZE` 默认 SHALL 为 20，值 0 SHALL 禁用历史缓冲。

#### Scenario: 使用完整嵌套策略

- **WHEN** 配置提供 `engine`、六个 routing 动作、`keywords`、willingness 全部字段和
  `priority`
- **THEN** 适配器 SHALL 按字段类型和值域保留该策略
- **AND** SHALL 不把嵌套字段合并为旧的扁平策略

#### Scenario: 关键词数组校验

- **WHEN** `routing.keywords` 是字符串数组，且每一项都是非空字符串
- **THEN** 配置 SHALL 接受该数组
- **AND** routing SHALL 将正文命中任意一项解释为确定性 `trigger`

#### Scenario: 旧 routing 字段被拒绝

- **WHEN** 配置包含 `routing.group`、`routing.image` 或 `routing.mentionHere`
- **THEN** 启动 SHALL 失败并指出不支持的 routing 字段类别
- **AND** SHALL 不将旧字段静默转换为 `allMessage`、关键词或其他规则

#### Scenario: 空关键词数组保持等待默认

- **WHEN** 配置省略 `routing.keywords` 或显式提供空数组，且 allMessage 为 `wait`
- **THEN** 普通消息在没有其他触发规则命中时 SHALL 返回 `wait`

#### Scenario: 非法策略被拒绝

- **WHEN** `engine`、动作值、关键词数组、数值或布尔字段不符合策略契约
- **THEN** 启动 SHALL 失败并指出安全的配置错误类别
