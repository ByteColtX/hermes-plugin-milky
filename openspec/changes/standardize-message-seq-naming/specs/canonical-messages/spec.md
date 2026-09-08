## MODIFIED Requirements

### Requirement: canonical record 包含完整稳定身份

每条可处理消息 MUST 提供 `platform`、`self_id`、`scene`、`chat_key`、`peer_id`、`sender_id`、字符串形式的 `message_seq`、Unix 秒时间戳、typed segments、正文、mention/quote 信号、分类后的 `media_resource_references`、`file_attachment_references`、forward/reply references、raw 和安全 metadata。`self_id` SHALL 来自事件的 `self_id` 并与启动时 `get_login_info.data.uin` 的身份一致；Milky `message_seq` SHALL 是 canonical `message_seq` 的唯一来源，不得从时间、正文、`ingress_sequence` 或本地计数器推导。通过 friend/group 身份交叉校验后，record MUST 继续携带供会话介绍使用的场景资料；friend 只允许 `user_id`、`nickname`、`sex`，group 只允许 `group_id`、`group_name`、`member_count`、`description`、`announcement`。raw、extras、group member 和未知扩展 MUST NOT 成为会话介绍字段。

#### Scenario: 时间和序号规范化

- **WHEN** 协议消息提供可解析的时间和消息序号
- **THEN** record SHALL 保存规范化 Unix 秒和 Milky `message_seq` 字符串
- **AND** SHALL 保留足以诊断未知扩展的 raw 信息而不暴露凭证

#### Scenario: 登录身份使用 uin

- **WHEN** `get_login_info` 成功返回 `data.uin` 和 `data.nickname`
- **THEN** 适配器 SHALL 将 `data.uin` 作为后续 canonical 的 self ID
- **AND** SHALL NOT 等待或臆造名为 `user_id` 的登录字段

#### Scenario: 身份字段缺失

- **WHEN** 无法确认场景、peer 或 sender 身份
- **THEN** 规范化 SHALL 分类拒绝该消息
- **AND** SHALL NOT 创建空或伪造身份的 Hermes turn

#### Scenario: group 交叉身份不一致

- **WHEN** group 消息的 `peer_id`、`group.group_id` 或 `group_member.group_id` 不能相互确认
- **THEN** 规范化 SHALL 分类拒绝该消息
- **AND** SHALL NOT 使用其中任意一个字段猜测 chat key

#### Scenario: friend 最小资料沿 canonical 边界保留

- **WHEN** friend 的 `friend.user_id` 与 `peer_id` 一致
- **THEN** canonical SHALL 保留 `user_id`、`nickname` 和 `sex` 供会话快照使用
- **AND** SHALL 忽略 `category`、`remark`、raw 和未知扩展

#### Scenario: group 最小资料沿 canonical 边界保留

- **WHEN** group 的 `group.group_id` 与 `peer_id` 一致
- **THEN** canonical SHALL 保留 `group_id`、`group_name`、`member_count`、`description` 和 `announcement`
- **AND** SHALL 忽略 group member 身份字段和未知扩展

### Requirement: 去重发生在资源和策略副作用之前

适配器 MUST 使用至少为 `milky:<self_id>:<chat_key>:<message_seq>` 的 key，在资源补全、Will 和 Hermes turn 之前以有界 TTL 方式原子检查并插入。该 key 中的 `message_seq` MUST 直接来自 canonical 已确认的 Milky 序号。

#### Scenario: 重连重复帧

- **WHEN** 同一 self、chat 和 `message_seq` 的事件因重连再次到达 TTL 窗口
- **THEN** 第二帧 SHALL 被判定为重复并停止
- **AND** SHALL 不再次查询或 materialize 附件、改变 Will 或创建 Hermes turn

#### Scenario: 相同正文不同序号

- **WHEN** 同一 chat 收到正文相同但 `message_seq` 不同的两条消息
- **THEN** 两条消息 SHALL 分别处理
- **AND** 去重 SHALL 不使用正文 hash、时间或 `ingress_sequence` 替代 `message_seq`

### Requirement: 缺少消息 ID 时显式降级

消息缺少 Milky `message_seq` 时 MUST NOT 伪造稳定去重 key；尽管 v1.3 OpenAPI 将其列为消息必填字段，tolerant parser MAY 将字段缺失的单帧交给 canonical 降级路径，但 MUST 记录 `no_stable_message_seq`，且不得把缺失值写入 TTL dedup key。

#### Scenario: 无消息 ID 的一次处理

- **WHEN** 合法消息缺少 `message_seq`
- **THEN** 消息 SHALL 最多按一次当前帧进入后续处理
- **AND** diagnostics SHALL 包含 `no_stable_message_seq`
