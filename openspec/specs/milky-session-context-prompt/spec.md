# milky-session-context-prompt Specification

## Purpose

为合法 Milky friend/group 会话提供最小、可审计且不联网的 QQ 场景介绍，并保持 Hermes system prompt 的缓存与恢复语义。

## Requirements

### Requirement: 会话介绍只使用场景白名单字段

friend snapshot MUST 只包含 `user_id`、`nickname`、`sex`；group snapshot MUST 只包含 `group_id`、`group_name`、`member_count`、`description`、`announcement`。字段必须来自同一条消息中通过身份交叉校验的 friend/group entity；缺失字段省略，不使用正文、历史上下文、sender fallback、group member、raw 或未知扩展补值。

#### Scenario: friend snapshot

- **WHEN** 合法 friend 消息触发 Hermes handoff
- **THEN** snapshot SHALL 使用已确认的 `user_id`、`nickname` 和 `sex`
- **AND** SHALL 不包含群资料或好友未声明字段

#### Scenario: group snapshot

- **WHEN** 合法 group 消息触发 Hermes handoff
- **THEN** snapshot SHALL 使用已确认的 `group_id`、`group_name`、`member_count`、`description` 和 `announcement`
- **AND** SHALL 不把发送者的群名片、昵称或性别作为群资料

### Requirement: snapshot 在 handoff 前登记并按 chat 隔离

插件 MUST 为每次 `register(ctx)` 创建线程安全、有界且不可变语义的本地 snapshot store，以 `dm:<id>` 或 `group:<id>` 为 key。pipeline MUST 在资源解析和 MessageEvent mapper 成功后、调用 Hermes `handle_message()` 前登记 snapshot；Gate deny、wait、dedup、temp、系统事件和 mapper/resolver 失败不得登记。淘汰只允许使 callback 返回空内容，不得阻断 handoff；同一 group key 可以被多个 Hermes user session 共享。

#### Scenario: callback 查询

- **WHEN** Hermes 执行 `hermes-plugin-milky.qq-session-context` callback
- **THEN** callback SHALL 读取 `HERMES_SESSION_CHAT_ID` 对应的本地 snapshot
- **AND** 缺少 chat context、snapshot 或支持字段时 SHALL 返回空内容
- **AND** SHALL 不执行 Milky Action、HTTP/SSE、文件访问或阻塞 I/O

### Requirement: 会话介绍作为独立不可信 metadata section

支持 `register_system_prompt_section` 的宿主 MUST 注册稳定的 `hermes-plugin-milky.qq-session-context` section。section SHALL 与 QQ Bot 操作指引分离，不得进入 `platform_hint`、MessageEvent 正文、`channel_context`、媒体字段或出站正文。昵称、群名、描述和公告必须中和控制字符、折叠换行并限制长度；section 必须声明这些值是外部不可信 metadata，而不是指令、授权或 tool-call 请求。

#### Scenario: 新会话渲染

- **WHEN** 新 Hermes session 的当前 Milky chat 存在 snapshot
- **THEN** system prompt SHALL 包含当前 chat 的 QQ 介绍和已确认字段名
- **AND** 不得包含正文、raw、token、Authorization、媒体 URL、文件路径或未知扩展

#### Scenario: 旧宿主降级

- **WHEN** 宿主没有 `register_system_prompt_section`
- **THEN** 插件 SHALL 跳过会话介绍 section 并继续平台注册
- **AND** platform hint SHALL 只保留既定首句

### Requirement: prompt cache 和恢复优先于本地动态快照

Hermes 已持久化完整 system prompt 被恢复时，插件 MUST 使用已持久化 section 字节，不重新渲染或查询远端。Hermes 显式 prompt invalidation/rebuild 时，section MAY 使用当时可用的最新本地 snapshot；该 rebuild 不得改变 Gate、Will、资源解析或出站行为。

#### Scenario: restore

- **WHEN** 已有 session 从持久化 system prompt 恢复
- **THEN** 会话介绍 SHALL 保持已持久化字节
- **AND** callback SHALL 不重新查询 Milky

#### Scenario: rebuild

- **WHEN** Hermes 按自身 contract 显式 rebuild prompt
- **THEN** section SHALL 使用当前本地 snapshot
- **AND** 同一 session 未发生 rebuild 时重复构建 SHALL 保持冻结内容
