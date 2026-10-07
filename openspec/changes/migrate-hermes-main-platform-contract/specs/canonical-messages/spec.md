# Spec Delta

## ADDED Requirements

### Requirement: adapter 替换期间继承活动消息去重状态

同一 Gateway 进程内替换 Milky adapter 时，插件 MUST 让 Hermes 继承仍在 TTL 窗口内的 canonical 消息去重状态。继承后的重复判定 MUST 继续发生在资源补全、Will 和 Hermes handoff 之前；该保证不扩展为进程重启后的持久化恢复。

#### Scenario: adapter 重建后收到相同消息

- **WHEN** Gateway 在去重 TTL 窗口内重建 Milky adapter，随后再次收到相同 `self_id`、chat key 和 `message_seq`
- **THEN** 第二帧 SHALL 被判定为重复
- **AND** SHALL 不再次补全资源、改变 Will 或创建 Hermes turn

#### Scenario: 新序号仍可处理

- **WHEN** 重建后的 adapter 收到相同 chat 的不同 `message_seq`
- **THEN** 该消息 SHALL 按新的 canonical key 独立处理
- **AND** SHALL 不因继承其他消息的去重状态而误丢弃

#### Scenario: 缺少序号不获得合成身份

- **WHEN** 重建后的 adapter 收到缺少 `message_seq` 的消息
- **THEN** 系统 SHALL 保留 `no_stable_message_seq` 降级
- **AND** SHALL 不从时间、正文或进程内计数生成可继承的去重 ID
