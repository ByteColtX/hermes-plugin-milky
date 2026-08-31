# mute-tracking Specification

## Purpose

维护 Milky Bot 自身在各群的可发言权威状态，使用 fail-closed 的 muted/unmuted 二态模型，
正确处理成员禁言、全体禁言、查询失败和事件更新，减少确定不能回复时的无效 Agent turn 与发送请求。

## Requirements

### Requirement: 初始群禁言同步使用正确顺序和字段

连接初始化 MUST 依次获取登录信息、群列表，再只为白名单允许的群查询 Bot 自身成员信息；
成员禁言截止时间 MUST 读取 `member.shut_up_end_time`；启动同步和主动刷新调用
`get_group_member_info` 时 MUST 传入 `no_cache=true`，以避免读取过期的成员状态缓存。
白名单为空时沿用允许所有群的语义，
`dm:<id>` 白名单项不触发群成员查询。

#### Scenario: 初始化多个群

- **WHEN** 适配器完成登录信息和群列表请求
- **THEN** SHALL 为群列表中的每个群查询 `group_id` 与 `user_id=self_id` 的成员信息
- **AND** SHALL 在所有必要查询完成前不将消息标记为初始化完成

#### Scenario: 成员字段为 null

- **WHEN** 成员信息的 `shut_up_end_time` 为 null
- **THEN** member mute SHALL 表示查询成功且当前为 unmuted
- **AND** SHALL NOT 读取或推断为其他协议字段

#### Scenario: 空白名单初始化多个群

- **WHEN** 适配器完成登录信息和群列表请求且白名单为空
- **THEN** SHALL 为群列表中的每个群查询 `group_id` 与 `user_id=self_id` 的成员信息
- **AND** SHALL 在所有必要查询完成前不将消息标记为初始化完成

#### Scenario: 初始同步只扫描群白名单

- **WHEN** 白名单包含 `group:100`、`dm:200`，而群列表包含群 `100` 和群 `101`
- **THEN** SHALL 只查询群 `100` 的 Bot 成员信息
- **AND** SHALL 不查询群 `101` 或因 `dm:200` 查询群成员

#### Scenario: 成员字段被服务端省略

- **WHEN** 成功的 `get_group_member_info` 响应省略 `member.shut_up_end_time`
- **THEN** tracker SHALL 将该次成员查询视为成功且当前 member mute 为 unmuted
- **AND** SHALL 不因字段省略把成功响应退化为永久 muted；只有请求失败或响应结构损坏时才保持既有 fail-closed 状态

#### Scenario: 成员状态查询绕过缓存

- **WHEN** tracker 在启动同步或主动刷新时查询 Bot 自身成员信息
- **THEN** SHALL 向 `get_group_member_info` 传入 `no_cache=true`
- **AND** SHALL 不因服务端返回过期缓存而把当前成员禁言误判为 unmuted

#### Scenario: 个人禁言 TTL 到期

- **WHEN** 成员查询或 `group_mute` 事件得到未来的 `shut_up_end_time`，且本地时间达到该截止时间
- **THEN** member mute SHALL 自动更新为 `unmuted`
- **AND** SHALL 不依赖新的 Milky 查询或 `duration=0` 事件才能恢复群消息处理

### Requirement: 状态模型区分已确认和未确认的全体禁言

每个群 MUST 维护 member mute、whole mute、观测时间和刷新时间。member mute 只能是
`muted` 或 `unmuted`，初始值 MUST 为 `muted`；由于 Milky v1.3 没有读取全体禁言状态的
Action 或群实体字段，whole mute 在完成成员查询但没有明确事件时 MUST 为 `unknown`。
初始化尚未完成时，Gate MUST 继续 fail-closed；`unknown` 的 whole mute 不得被当作已确认的
`muted`，也不得阻止群消息。

#### Scenario: 查询失败保持 fail-closed 状态

- **WHEN** 某群刷新查询失败
- **THEN** 系统 SHALL 保留上次二态状态
- **AND** 若此前从未成功维护状态，系统 SHALL 保持 muted，不得把失败解释成 unmuted

#### Scenario: 全量刷新发现群离开

- **WHEN** 新的群列表不再包含之前记录的群
- **THEN** 该群的旧状态 SHALL 从当前 tracker 快照中清理

#### Scenario: 全体禁言状态不可查询

- **WHEN** 成员查询成功但 Milky 没有提供全体禁言读取结果或对应事件
- **THEN** whole mute SHALL 记录为 `unknown`
- **AND** 状态汇总 SHALL 计入 `unknown`，群 Gate SHALL 不因该状态误判为已禁言

### Requirement: 禁言事件更新遵循 Milky 语义

`group_mute` 的 `duration=0` MUST 清除对应成员禁言，正 duration MUST 计算截止时间并安排本地
TTL 到期更新；`group_whole_mute` MUST 按 `is_mute` 更新 whole mute 状态。

#### Scenario: 取消成员禁言

- **WHEN** 收到 `group_mute` 且 duration 为 0
- **THEN** 对应群的 member mute SHALL 变为 unmuted
- **AND** SHALL 不把 0 解释为永久禁言

#### Scenario: 开启全体禁言

- **WHEN** 收到 `group_whole_mute` 且 `is_mute` 为 true
- **THEN** whole mute SHALL 变为 muted
- **AND** 群出站门禁 SHALL 阻止发送

### Requirement: 刷新受锁、冷却和并发上限保护

群状态主动刷新 MUST 具备每群锁、冷却和并发上限；群消息任意文本、图片、文件、语音或视频发送失败时 MAY 触发对应群刷新，私聊发送失败 MUST NOT 查询群成员状态。发送失败触发的刷新 SHALL 是独立的只读状态维护，不得阻塞、改变或驱动原始发送结果的 fallback、重试或第二次提交。

#### Scenario: 多条群发送失败

- **WHEN** 同一群的多条出站请求几乎同时失败
- **THEN** tracker SHALL 合并或限制刷新请求
- **AND** SHALL 不产生无界的成员查询风暴

#### Scenario: 私聊发送失败

- **WHEN** dm 发送失败
- **THEN** 系统 SHALL 原样返回发送错误
- **AND** SHALL 不调用群成员查询或刷新任何群状态

#### Scenario: SSE 重连不重新扫描

- **WHEN** 事件流断线后重新建立连接
- **THEN** MuteTracker SHALL 保留现有内存状态
- **AND** SHALL 不重新执行登录后的群列表和成员全量扫描

#### Scenario: 传输未知时刷新不驱动重发

- **WHEN** 群消息发送结果为 `transport_unknown` 且刷新钩子被触发
- **THEN** tracker MAY 使用 `get_group_member_info` 更新 Bot 自身的成员禁言快照
- **AND** 刷新完成、失败或超时 SHALL 不触发 fallback、重试或第二次发送，原始 SendResult SHALL 保持 `transport_unknown`
