## Purpose

维护 Milky Bot 自身在各群的可发言权威状态，使用 fail-closed 的 muted/unmuted 二态模型，
正确处理成员禁言、全体禁言、查询失败和事件更新，减少确定不能回复时的无效 Agent turn 与发送请求。

## ADDED Requirements

### Requirement: 初始群禁言同步使用正确顺序和字段

连接初始化 MUST 依次获取登录信息、群列表，再为每个群查询 Bot 自身成员信息；成员禁言截止时间 MUST 读取 `member.shut_up_end_time`。

#### Scenario: 初始化多个群

- **WHEN** 适配器完成登录信息和群列表请求
- **THEN** SHALL 为群列表中的每个群查询 `group_id` 与 `user_id=self_id` 的成员信息
- **AND** SHALL 在所有必要查询完成前不将消息标记为初始化完成

#### Scenario: 成员字段为 null

- **WHEN** 成员信息的 `shut_up_end_time` 为 null
- **THEN** member mute SHALL 表示查询成功且当前为 unmuted
- **AND** SHALL NOT 读取或推断为其他协议字段

#### Scenario: 成员字段被服务端省略

- **WHEN** 成功的 `get_group_member_info` 响应省略 `member.shut_up_end_time`
- **THEN** tracker SHALL 将该次成员查询视为成功且当前 member mute 为 unmuted
- **AND** SHALL 不因字段省略把成功响应退化为永久 muted；只有请求失败或响应结构损坏时才保持既有 fail-closed 状态

### Requirement: 状态模型只有 muted 和 unmuted

每个群 MUST 维护 member mute、whole mute、观测时间和刷新时间；每个 mute 字段只能是 muted 或 unmuted，初始值 MUST 为 muted。

#### Scenario: 查询失败保持 fail-closed 状态

- **WHEN** 某群刷新查询失败
- **THEN** 系统 SHALL 保留上次二态状态
- **AND** 若此前从未成功维护状态，系统 SHALL 保持 muted，不得把失败解释成 unmuted

#### Scenario: 全量刷新发现群离开

- **WHEN** 新的群列表不再包含之前记录的群
- **THEN** 该群的旧状态 SHALL 从当前 tracker 快照中清理

### Requirement: 禁言事件更新遵循 Milky 语义

`group_mute` 的 `duration=0` MUST 清除对应成员禁言，正 duration MUST 计算截止时间；`group_whole_mute` MUST 按 `is_mute` 更新 whole mute 状态。

#### Scenario: 取消成员禁言

- **WHEN** 收到 `group_mute` 且 duration 为 0
- **THEN** 对应群的 member mute SHALL 变为 unmuted
- **AND** SHALL 不把 0 解释为永久禁言

#### Scenario: 开启全体禁言

- **WHEN** 收到 `group_whole_mute` 且 `is_mute` 为 true
- **THEN** whole mute SHALL 变为 muted
- **AND** 群出站门禁 SHALL 阻止发送

### Requirement: 刷新受锁、冷却和并发上限保护

群状态主动刷新 MUST 具备每群锁、冷却和并发上限；群消息任意文本、图片、文件、语音或视频发送失败时 MAY 触发对应群刷新，私聊发送失败 MUST NOT 查询群成员状态。

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
