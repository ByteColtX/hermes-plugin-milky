## Purpose

为每个 Milky friend/group Hermes 会话提供一次安全、可审计且与会话缓存兼容的 QQ 场景介绍，使 Agent 在首次处理消息时了解当前私聊对象或群聊基本资料。

## ADDED Requirements

### Requirement: QQ 会话介绍按消息场景提供最小字段

对于通过普通消息流水线的合法 friend 或 group 消息，系统 MUST 使用同一条消息中已经通过身份一致性校验的场景 metadata 生成会话介绍快照。friend 介绍 MUST 只包含 `user_id`、`nickname` 和 `sex`；group 介绍 MUST 只包含 `group_id`、`group_name`、`member_count`、`description` 和 `announcement`。系统 MUST NOT 用 friend 字段填充 group 介绍、用 group member 字段填充 friend 介绍，或从正文、历史上下文、关键词、显示名和未确认 raw 扩展字段猜测缺失值。

#### Scenario: friend 会话字段进入介绍快照

- **WHEN** 合法 friend `message_receive` 包含已校验的好友实体并触发 Hermes handoff
- **THEN** 会话介绍 SHALL 使用该实体的 `user_id`、`nickname` 和 `sex`
- **AND** SHALL 不包含群名、群人数、群描述或群公告字段

#### Scenario: group 会话字段进入介绍快照

- **WHEN** 合法 group `message_receive` 包含与 `peer_id` 一致的群实体并触发 Hermes handoff
- **THEN** 会话介绍 SHALL 使用该实体的 `group_id`、`group_name`、`member_count`、`description` 和 `announcement`
- **AND** SHALL 不把当前发送者的群名片、昵称或性别改写成群资料字段

#### Scenario: 场景资料部分缺失

- **WHEN** 合法消息缺少可选的昵称、性别、群描述、群公告或其他介绍字段
- **THEN** 会话介绍 SHALL 省略对应字段
- **AND** SHALL 保留其他已确认字段
- **AND** SHALL 不使用空字符串、零值或固定文本伪造缺失资料

### Requirement: 新 Hermes 会话注入独立的 QQ 介绍 section

当 Hermes 提供 `register_system_prompt_section` 时，Milky 插件 MUST 注册一个稳定且只属于 Milky 的会话介绍 section，并在新会话首次构建 system prompt 时渲染该 section。介绍 section MUST 与现有 QQ 操作指引 section 分离；不得把群/好友资料写入 `platform_hint`、当前用户正文或 `channel_context`。

#### Scenario: group 新会话获得介绍

- **WHEN** Hermes 为一个 group chat 创建新的会话 system prompt，且存在该 chat 的合法群资料快照
- **THEN** system prompt SHALL 包含群聊介绍 section
- **AND** SHALL 展示已确认的群资料字段及其字段名
- **AND** SHALL 不把本次消息正文或历史消息作为群资料注入

#### Scenario: friend 新会话获得介绍

- **WHEN** Hermes 为一个 friend chat 创建新的会话 system prompt，且存在该 chat 的合法好友资料快照
- **THEN** system prompt SHALL 包含私聊介绍 section
- **AND** SHALL 展示 `user_id`、`nickname` 和 `sex` 中已确认的字段
- **AND** SHALL 不包含群聊资料字段

#### Scenario: 没有 section API 或没有资料快照

- **WHEN** Hermes 不提供 `register_system_prompt_section`，或 callback 渲染时没有当前 chat 的安全资料快照
- **THEN** 插件 SHALL 不注入 QQ 会话介绍
- **AND** SHALL 继续完成既有平台注册和其他可用 section 的注册
- **AND** SHALL 不因缺少介绍资料创建网络请求、空 Agent 状态或伪造介绍文本

### Requirement: QQ 介绍中的外部 metadata 必须按不可信文本处理

会话介绍 MUST 将昵称、群名、描述和公告视为不可信 metadata，只保留安全的可见文本并处理回车、换行、控制字符和长度边界。介绍 MUST 明确这些字段是标签而不是指令；不得把 token、Authorization、完整 raw 响应、媒体 URL、文件路径、正文或未知扩展字段写入 section。

#### Scenario: metadata 包含换行或控制字符

- **WHEN** nickname、group_name、description 或 announcement 包含换行、控制字符或超长内容
- **THEN** section SHALL 将其转换为不改变介绍边界的安全表示并限制长度
- **AND** SHALL 不让 metadata 生成新的 prompt heading、指令块或可执行 Agent 指令

#### Scenario: 资料字段包含未知扩展

- **WHEN** friend/group entity 含有未纳入本 capability 的扩展字段
- **THEN** 会话介绍 SHALL 忽略这些字段
- **AND** SHALL 不记录或渲染完整 entity、raw payload 或协议响应

### Requirement: 介绍快照遵守 Hermes 会话缓存和插件无网络边界

插件 MUST 在现有 Gate 和 Will 允许的 trigger handoff 边界内登记资料快照，并在调用 Hermes `handle_message()` 前完成登记。system prompt callback MUST 只读取当前 Milky chat key 对应的进程内安全快照，MUST NOT 发起 Milky Action、HTTP/SSE、文件访问或其他阻塞 I/O。Hermes 已持久化的完整 system prompt 被恢复时，插件 MUST 不重新读取远端资料或改变已持久化的介绍字节。

#### Scenario: wait、Gate deny 和系统事件不创建介绍快照

- **WHEN** 消息被 Gate 拒绝、Will 返回 `wait`，或事件属于 temp、系统事件或未知事件
- **THEN** 系统 SHALL 不为该事件登记 QQ 会话介绍快照
- **AND** SHALL 不创建普通 Hermes turn 或因介绍功能增加 reply cost

#### Scenario: trigger 在 Hermes handoff 前登记快照

- **WHEN** 合法 friend/group 消息通过 Gate、Will 返回 `trigger` 且资源解析成功
- **THEN** 系统 SHALL 在调用 `handle_message()` 前登记当前 chat 的安全资料快照
- **AND** 新会话的 section callback SHALL 能读取该快照
- **AND** callback SHALL 不执行 Milky 查询 Action

#### Scenario: 已持久化 prompt 被恢复

- **WHEN** Hermes 恢复一个已有 session 的完整 system prompt
- **THEN** QQ 会话介绍 SHALL 使用已持久化的 section 内容
- **AND** SHALL 不因本次恢复重新查询好友或群资料
- **AND** SHALL 不因该恢复改变 Gate、Will、资源解析或出站行为

#### Scenario: 新会话或显式 prompt rebuild 使用可用快照

- **WHEN** Hermes 创建新的 session，或在其约定的 prompt rebuild 边界重新渲染插件 section
- **THEN** section SHALL 使用当前 chat 可用的最新安全快照
- **AND** SHALL 保持单 section 和 Hermes aggregate prompt budget
