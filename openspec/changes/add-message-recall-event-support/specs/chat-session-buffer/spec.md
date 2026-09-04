## MODIFIED Requirements

### Requirement: context-only 系统事件使用独立有界缓冲

系统 MUST 为每个可识别 chat 维护独立、有界、可丢失的 context-only 事件缓冲。该缓冲与
普通 wait buffer 分离，不得进入普通 canonical、Will 或 reply cost 状态。登记的系统事件
只有在后续同 chat trigger 时作为 `channel_context` 注入一次；注入后 MUST 原子清除，溢出时
MUST 丢弃最早事件并记录安全诊断。系统事件无可确认 chat key 时 MUST 只观察，不得创建
全局或默认 chat 的上下文。字段完整的 `message_recall` MUST 按其 `message_scene` 和
`peer_id` 写入对应 `dm:` 或 `group:` chat；它与其他 context-only 事件共享相同的顺序、
容量、一次性消费和失败边界。

#### Scenario: 系统事件等待下一次 trigger

- **WHEN** `group_nudge`、群成员变更事件或字段完整的 `message_recall` 在没有 trigger 的时期到达
- **THEN** 事件 SHALL 进入对应 chat 的 context-only 缓冲
- **AND** SHALL 不调用 Hermes、Will 或普通 wait buffer
- **AND** 下一次该 chat trigger SHALL 消费这些事件一次

#### Scenario: 撤回事件按场景隔离

- **WHEN** 一个 `message_recall` 的 `message_scene` 为 `friend` 或 `group` 且 `peer_id` 合法
- **THEN** 系统 SHALL 分别将其写入 `dm:<peer_id>` 或 `group:<peer_id>` 的 context-only 缓冲
- **AND** SHALL 不因相同数字的好友号与群号把事件写入另一种场景

#### Scenario: 系统事件缓冲与普通消息按 ingress 顺序合并

- **WHEN** 一个 chat 先后产生普通 wait 消息、`message_recall` 和 `group_nudge`
- **THEN** 下一次 trigger 的 `channel_context` SHALL 按 ingress sequence 混合排列这些记录
- **AND** 撤回事件 SHALL 使用 `<event message_recall> ...` 格式
- **AND** 所有系统事件 SHALL NOT 形成独立 Hermes turn

#### Scenario: 系统事件缓冲溢出

- **WHEN** context-only 缓冲达到上限后又收到新事件
- **THEN** 系统 SHALL 保留最新上限数量的事件
- **AND** SHALL 丢弃最早事件并记录不含正文的溢出诊断

#### Scenario: 撤回事件交接失败

- **WHEN** 包含 `message_recall` 的 detached context batch 在 trigger 交接时失败
- **THEN** 系统 SHALL 只重试同一 batch 或记录不可恢复失败
- **AND** SHALL NOT 自动重复追加撤回事件或把其升级为独立 Agent turn

#### Scenario: 无法建立 chat key

- **WHEN** 系统事件缺少或包含非法群号/好友号，或 `message_recall` 的场景与 `peer_id` 无法确认
- **THEN** 系统 SHALL 保持 observe-only
- **AND** SHALL NOT 写入任何 chat context、普通 buffer 或 Hermes transcript
