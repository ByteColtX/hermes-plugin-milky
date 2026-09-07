## MODIFIED Requirements

### Requirement: canonical record 包含完整稳定身份

每条可处理消息 MUST 提供 `platform`、`self_id`、`scene`、`chat_key`、`peer_id`、`sender_id`、字符串形式的 `message_id`、Unix 秒时间戳、typed segments、正文、mention/quote 信号、分类后的 `media_resource_references`、`file_attachment_references`、forward/reply references、raw 和安全 metadata。`self_id` SHALL 来自事件的 `self_id` 并与启动时 `get_login_info.data.uin` 的身份一致；Milky `message_seq` 是 canonical `message_id` 的来源。对于 friend 或 group 场景，canonical record MUST 在通过交叉身份校验后继续携带供 Hermes handoff 使用的最小场景 metadata；该 metadata 只包含已确认的 friend/group 介绍字段，不得把完整 raw entity 或未知扩展变成 Agent 指令。

#### Scenario: 时间和序号规范化

- **WHEN** 协议消息提供可解析的时间和消息序号
- **THEN** record SHALL 保存规范化 Unix 秒和 Milky 序号字符串
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

- **WHEN** friend 消息的 `friend.user_id` 与 `peer_id` 一致，且好友实体通过协议解析
- **THEN** canonical record SHALL 保留供会话介绍使用的 `user_id`、`nickname` 和 `sex` 字段
- **AND** SHALL 不把 category、remark、raw 或未知扩展字段纳入会话介绍 metadata

#### Scenario: group 最小资料沿 canonical 边界保留

- **WHEN** group 消息的 `group.group_id` 与 `peer_id` 一致，且群实体通过协议解析
- **THEN** canonical record SHALL 保留供会话介绍使用的 `group_id`、`group_name`、`member_count`、`description` 和 `announcement` 字段
- **AND** SHALL 不把 group member 的身份字段或未知扩展当作群资料

### Requirement: sender 显示名按场景使用稳定 fallback

规范化 MUST 为 `sender_name` 选择非空且去除首尾空白的显示名。group 消息 MUST 按 `group_member.card` → `group_member.nickname` → `sender_id` 的顺序选择；friend 消息 MUST 按 `friend.nickname` → `sender_id` 的顺序选择。空字符串和只含空白的候选值 MUST 视为缺失；friend 消息 MUST NOT 使用群成员名片。选出的同一个 `sender_name` MUST 同时用于 Hermes `source.user_name` 和历史/current 紧凑 header；临时会话在协议解析边界忽略，不得因该显示名规则进入普通 Agent mapper。

#### Scenario: 群聊优先使用群名片

- **WHEN** group 消息的 `group_member.card`、`group_member.nickname` 和 `sender_id` 分别可用
- **THEN** canonical `sender_name` SHALL 使用 `group_member.card`
- **AND** Hermes source 和上下文 header SHALL 使用同一个群名片

#### Scenario: 群名片缺失时回退昵称和 QQ 号

- **WHEN** group 消息的群名片为空或只含空白
- **THEN** canonical `sender_name` SHALL 回退到非空的 `group_member.nickname`
- **AND** 当群名片和昵称都缺失时 SHALL 回退到字符串形式的 `sender_id`

#### Scenario: 私聊不使用群名片

- **WHEN** friend 消息同时带有 group card 候选和 friend nickname
- **THEN** canonical `sender_name` SHALL 使用 `friend.nickname`
- **AND** 当 friend nickname 缺失时 SHALL 使用 `sender_id`
- **AND** SHALL NOT 将 group card 作为私聊显示名
