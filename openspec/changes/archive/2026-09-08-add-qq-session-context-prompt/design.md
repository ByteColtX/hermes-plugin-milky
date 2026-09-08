## Context

当前 Milky normalizer 已将 `FriendEntity`、`GroupEntity` 和 `GroupMemberEntity` 放入 `NormalizedMessage`，但 `CanonicalMessage` 没有继续携带 friend/group 场景资料。`inbound/hermes_mapper.py` 的 source builder 已尝试从 canonical 读取 friend/group，因此当前 `chat_name` 等资料存在丢失边界。

Hermes 的 `register_system_prompt_section` callback 只收到有限的 session-info mapping，不包含群名、群描述、公告、好友性别等平台资料。Hermes gateway 在调用 Agent 前会设置 `HERMES_SESSION_CHAT_ID`，其值来自 `SessionSource.chat_id`；Milky source 已使用 `dm:<id>` 或 `group:<id>` 作为该字段。这个现有边界足以让插件用本地 chat key 找到资料，不需要修改 Hermes core 或解析 Hermes 完整 session key。

Hermes 会持久化完整 system prompt。恢复已有 prompt 时，插件 section 不应再次查询或改变已持久化内容；当前 Hermes 源码在显式 prompt invalidation/rebuild 边界会重新渲染插件 section，因此新快照只在新 session 或该类明确 rebuild 边界生效。

## Goals / Non-Goals

**Goals:**

- 让 Agent 在首次 Milky friend/group session prompt 中看到用户要求的最小 QQ 会话资料。
- 保留现有 canonical、Gate、Will、资源解析、MessageEvent 正文和 Hermes detached handoff 语义。
- 让 callback 无网络、无文件 I/O、无远端查询，并安全处理可被用户控制的文本。
- 让旧 Hermes 宿主和未提供资料的消息安全降级。
- 通过测试确认 prompt section 注册、快照时序、并发隔离、恢复和失败边界。

**Non-Goals:**

- 不修改 `/Users/bytecolt/PythonProjects/hermes-agent` 的 section API、`SessionSource` 或 system prompt renderer。
- 不在 `register()`、section callback 或 normalizer 中调用 `get_group_info`、`get_friend_info` 或其他 Milky Action。
- 不把介绍资料写入 `MessageEvent.text`、`channel_context`、Will 输入、普通消息正文或出站内容。
- 不提供每轮实时群资料刷新；实时查询仍属于显式 ToolSpec 或未来独立能力。
- 不把完整 protocol entity、raw payload、category、remark、群成员资料或未知扩展写入介绍。

## Decisions

### 1. 在 canonical 边界保留最小场景资料

normalizer 继续负责协议解析和 friend/group 交叉身份校验；canonical record 增加可供后续 handoff 使用的最小场景 metadata。实现可以保留经过校验的 typed entity 引用，但进入 prompt snapshot 前必须只复制本 change 明确的字段，不能让 `raw` 或 `extras` 成为隐式资料来源。

这样可以保持“canonical 是后续层唯一事实来源”的项目边界，并修复 mapper 已存在但当前读不到 `friend`/`group` 的丢失问题。不会在 prompt callback 中重新解析 raw JSON。

### 2. 使用注册实例绑定的本地 snapshot store

根插件注册入口创建一个与该插件注册实例关联的、线程安全且有界的 chat metadata store，并将同一 store 传给 adapter/pipeline 和 section callback。pipeline 在资源 resolver 与 MessageEvent mapper 完成后、调用 Hermes `handle_message()` 前写入当前 `chat_key` 的不可变快照。

快照以 Milky 的 `dm:<id>` / `group:<id>` 为 key，而不是自行拼接或解析 Hermes `agent:<namespace>:...` session key。Hermes callback 通过已有 `gateway.session_context.get_session_env("HERMES_SESSION_CHAT_ID")` 读取当前 source chat key，再查 store。这样既兼容 Hermes 的 group-per-user session，也避免依赖 profile、group session isolation 或内部 session key 格式。

store 使用固定的有界淘汰策略，不新增环境变量；淘汰只会让 section 返回空内容，不会阻断消息 handoff。不同 chat 的快照必须相互隔离；同一 group 的多个 Hermes user session 可以共享同一 group metadata。

### 3. 新增独立 section，不改写现有操作指引 section

现有 `hermes-plugin-milky.qq-platform-guidance` 继续只负责 Bot identity 和 QQ 操作语法。新增的 section 使用独立稳定 ID，例如 `hermes-plugin-milky.qq-session-context`，只负责当前 friend/group 的介绍。两者都在根 `register(ctx)` 中注册，避免把动态资料混入 `platform_hint` 或让 identity section 依赖入站 session metadata。

callback 的输入仍是 Hermes 提供的有限 `session_info`；平台 chat key 通过已有 task-local session context 获取。非 gateway、测试 fake 或没有当前 chat context 时，callback fail-open 返回空内容。

### 4. 采用快照而不是 callback 查询

section callback 必须同步且不能阻塞 Agent prompt 构建。把 `get_group_info` 或 `get_friend_info` 放在 callback 中会引入不可控延迟、连接生命周期耦合和恢复时的非确定性，也违反现有“section callback 只读本地缓存”的边界。

入站 `message_receive` 已带有可用的 friend/group typed entity 时，直接使用该实体；资料缺失时省略字段，不为了完整介绍而发起额外 Action。未来如需主动刷新，应作为独立的显式、可分类查询能力设计。

### 5. 只渲染白名单字段并中和不可信文本

snapshot 只保存本 change 定义的字段。ID 使用已通过 parser/canonical 的数值；文本字段在渲染前统一去除控制字符、折叠换行、限制长度，并使用不会生成新的 prompt 结构的安全表示。section 先说明字段是 untrusted metadata，再输出字段名和值。

不把 `group_member.nickname/card/sex` 误当作群资料；group member 的 sender 名继续由既有 canonical fallback 负责。好友和群资料的缺失不转换成 `unknown`、零值或占位 QQ 号。

### 6. 保持原有 handoff 顺序和缓存语义

snapshot 写入点位于已通过 Gate/Will 的 trigger、资源解析和 mapper 之后，且早于 Hermes `handle_message()`。因此 wait、Gate deny、temp、系统事件和 mapper 失败不会建立普通会话介绍状态；reply cost 仍只由现有 trigger 逻辑负责。

Hermes 第一次构建新 session prompt 时读取该快照并冻结 section。已有持久化 prompt 恢复时不重新读取 store 以外的数据，也不联网；Hermes 显式 invalidation/rebuild 时按其现行 contract 重新渲染，使用当时仍可用的本地快照。

### 7. 不使用 on_session_start 或 per-turn hook 注入

Hermes `session:start` 是观察事件，callback 返回值不能修改 system prompt，且 payload 没有所需 QQ 资料。`pre_llm_call` 等动态 hook 会把稳定会话资料变成每轮注入，破坏本 change 要求的 session prompt cache 语义。因此它们不作为本 change 的注入路径。

## Risks / Trade-offs

- [Risk] 群名称、描述或公告可由外部用户控制，可能包含伪造 prompt 指令。→ 渲染前做换行/控制字符中和、长度限制，并明确标注为 untrusted metadata；不渲染未知 entity 字段。
- [Risk] section snapshot 可能早于真实 Agent 执行而被同 chat 的后续事件更新。→ store 按 chat key 保存经过 canonical 校验的最新快照；群资料对同 chat 共享，friend chat 天然按用户隔离；测试覆盖并发不同 chat 隔离。不会依赖全局可变 prompt 字节。
- [Risk] session 恢复或 Hermes 进程重启后本地 store 可能没有资料。→ 已持久化 prompt 优先恢复；没有持久化 section 时 callback fail-open，不联网、不伪造资料。
- [Risk] Hermes core 文档与当前源码对 compression rebuild 时 section 是否重新渲染的描述存在差异。→ 设计遵循当前源码的恢复与 invalidation 行为，不把 compression refresh 作为跨进程持久保证；用真实 Hermes 集成测试记录证据。
- [Risk] 固定有界 store 淘汰活跃 chat 的资料。→ 淘汰只导致本次 section 缺失，不影响消息交接或出站；新 trigger 可重新登记快照。
- [Risk] 现有 `build_source` 对 friend/group typed entity 的读取修复可能影响 `chat_name`。→ 以 canonical fixture 和 Hermes source fake 回归现有 `dm:`/`group:` chat key、sender name、message ID 和平台字段。

## Migration Plan

1. 先补 canonical、snapshot、section callback 和 fake Hermes 测试，再实现数据和注册接线。
2. 更新 `ARCHITECTURE.md`、相关主规范和 README 的当前能力说明；不新增配置和 Milky Action。
3. 运行聚焦测试、完整 pytest、Ruff、format、build、diff 检查和 OpenSpec strict validation。
4. 通过真实 Hermes 宿主验证新 session 首次 prompt、已有 session prompt restore、显式 rebuild、旧宿主降级及 callback 无网络；未覆盖的行为写入 evidence ledger。
5. 回滚只需移除新增 section 注册和 snapshot handoff；既有 QQ 操作指引 section、platform hint、MessageEvent 正文和出站行为保持原逻辑。
