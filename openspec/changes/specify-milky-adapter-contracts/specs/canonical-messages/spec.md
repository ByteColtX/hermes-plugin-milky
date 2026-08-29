## Purpose

建立 friend、group 消息统一且无碰撞的身份记录，让去重、门禁、Will、缓冲和
Hermes 映射都基于同一份可审计的 canonical message，而不是各自猜测协议字段。

## ADDED Requirements

### Requirement: 只接收普通消息事件进入消息流水线

适配器 MUST 只将类型为 `message_receive` 且身份和场景可建立的事件交给普通消息流水线；recall、request、notice、lifecycle 和未知事件 SHALL 保持 observe-only。

#### Scenario: 合法群消息

- **WHEN** 收到带群、发送者和消息内容的 `message_receive` 事件
- **THEN** 事件 SHALL 被规范化为 group 场景消息
- **AND** SHALL 可以继续进入 canonical、Gate 和 Will

#### Scenario: 系统事件

- **WHEN** 收到撤回、请求、通知、生命周期或未知事件
- **THEN** 事件 SHALL 被观察并保留安全 raw 信息
- **AND** SHALL NOT 创建普通 Hermes MessageEvent 或触发 Agent

### Requirement: 场景和 chat key 必须命名空间隔离

消息 MUST 将 friend 映射为 `dm:<十进制 QQ 号>`、group 映射为 `group:<十进制群号>`；空值、负数、非数字和包含额外分隔符的 ID MUST 被拒绝。`temp` 不建立 chat key。

#### Scenario: 群号和用户号相同

- **WHEN** 一个群号和一个用户 QQ 号具有相同十进制字符
- **THEN** 它们 SHALL 生成不同的 `group:` 和 `dm:` chat key

#### Scenario: temp 消息被忽略

- **WHEN** 收到临时会话消息
- **THEN** 解析边界 SHALL 记录 `ignored_temp`
- **AND** SHALL NOT 创建 canonical、buffer、Will 或 Hermes MessageEvent

### Requirement: canonical record 包含完整稳定身份

每条可处理消息 MUST 提供 `platform`、`self_id`、`scene`、`chat_key`、`peer_id`、`sender_id`、字符串形式的 `message_id`、Unix 秒时间戳、typed segments、正文、mention/quote 信号、分类后的 `media_resource_references`、`file_attachment_references`、forward/reply references、raw 和安全 metadata。`self_id` SHALL 来自事件的 `self_id` 并与启动时 `get_login_info.data.uin` 的身份一致；Milky `message_seq` 是 canonical `message_id` 的来源。

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

### Requirement: sender 显示名按场景使用稳定 fallback

规范化 MUST 为 `sender_name` 选择非空且去除首尾空白的显示名。group 消息 MUST 按
`group_member.card` → `group_member.nickname` → `sender_id` 的顺序选择；friend 消息
MUST 按 `friend.nickname` → `sender_id` 的顺序选择。空字符串和只含空白的候选值 MUST
视为缺失；friend 消息 MUST NOT 使用群成员名片。选出的同一个 `sender_name` MUST 同时
用于 Hermes `source.user_name` 和历史/current 紧凑 header；临时会话在协议解析边界忽略，
不得因该显示名规则进入普通 Agent mapper。

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

### Requirement: 去重发生在资源和策略副作用之前

适配器 MUST 使用至少为 `milky:<self_id>:<chat_key>:<message_id>` 的 key，在资源补全、Will 和 Hermes turn 之前以有界 TTL 方式原子检查并插入。

#### Scenario: 重连重复帧

- **WHEN** 同一 self、chat 和 message ID 的事件因重连再次到达 TTL 窗口
- **THEN** 第二帧 SHALL 被判定为重复并停止
- **AND** SHALL 不再次查询或 materialize 附件、改变 Will 或创建 Hermes turn

#### Scenario: 相同正文不同序号

- **WHEN** 同一 chat 收到正文相同但 message ID 不同的两条消息
- **THEN** 两条消息 SHALL 分别处理
- **AND** 去重 SHALL 不使用正文 hash 或时间替代稳定消息 ID

### Requirement: 缺少消息 ID 时显式降级

消息缺少 Milky `message_seq` 时 MUST NOT 伪造稳定去重 key；尽管 v1.3 OpenAPI 将其列为消息必填字段，tolerant parser MAY 将字段缺失的单帧交给 canonical 降级路径，但 MUST 记录 `no_stable_message_id`，且不得把缺失值写入 TTL dedup key。

#### Scenario: 无消息 ID 的一次处理

- **WHEN** 合法消息缺少 message ID
- **THEN** 消息 SHALL 最多按一次当前帧进入后续处理
- **AND** diagnostics SHALL 包含 `no_stable_message_id`
