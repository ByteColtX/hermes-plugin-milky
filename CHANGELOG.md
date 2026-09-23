# Changelog

## [1.9.0] - 2026-09-23

### 新增

- 增加只读 `sticker_search`，并让 `sticker_send` 支持按持久化贴纸 ID 精确发送；继续校验当前会话、条目和文件，每次调用最多执行一次发送 Action。
- 普通文本出站会精确拦截 Hermes 静默标记失败后的固定兜底提示，避免将内部提示发送到 QQ。

### 变更与修复

- Milky Tool 将 HTTP 响应正文原样交付调用方，不再由插件解析并重建 envelope 或过滤响应字段；插件日志仍不记录完整响应正文。
- 修正 Will 关键词判断，只从可匹配的消息文本触发，避免结构化提及名称造成误触发或错误兴趣增益。
- 静默兜底提示被拦截时不会产生 QQ 消息或远端消息 ID；适配器仍返回成功，Hermes Gateway 可能据此将投递记录为 delivered。

### 验证与边界

- 完整测试：`1004 passed, 3 skipped`；跳过项涉及当前环境缺少 Hermes host 或需显式启用的真实集成。
- Ruff、格式检查、`uv build`、`uv lock --check`、`git diff --check` 和 `openspec validate --changes --strict` 通过；未连接真实 Hermes/Milky，也未执行真实消息发送。

## [1.8.0] - 2026-09-13

### 新增

- 增加显式 `/milky sticker` 人工维护闭环：支持导入、预览、列举、编辑、重新分析、删除、清理和重建索引。
- 增加受限的 `sticker_send` Agent Tool：根据当前 Milky 会话和贴纸元数据选择并发送一张贴纸。

### 变更与边界

- 贴纸库使用独立 plugin-data 存储，支持图片格式与 SHA-256 校验、字段级人工修正、发送统计和安全错误分类。
- `sticker_send` 只在存在可用库条目时暴露，不接受 Agent 指定目标、贴纸 ID、路径或 URL；一次调用最多执行一次发送 Action。
- 新增运行时依赖 `Pillow>=12.3.0` 和 `jieba>=0.42.1`；未执行真实 Milky 发送或上传 smoke。

### 验证

- `951 passed, 3 skipped`；跳过项为当前环境缺少 Hermes host 或需要显式开启的真实 Hermes 集成。
- Ruff、格式检查、`uv build`、`uv lock --check`、`git diff --check` 和 OpenSpec strict validate 均通过。

## [1.7.0] - 2026-09-09

### 变更与修复

- 出站 CQ-compatible 控制码的 `CQ` 前缀改为大小写不敏感；类型、字段、真实 ID 校验和未知/非法
  控制码的原文 fallback 保持不变，`[SPLIT]` 边界也使用同一规则。
- 统一插件内部 Milky 消息序号的 `message_seq` 命名；群聊 Agent-facing header 使用 `msg_seq`，
  Hermes 交接仍保留宿主要求的 `message_id` 映射。

### 验证与边界

- 发布前已通过完整测试、Ruff、格式检查、构建、`git diff --check` 和 OpenSpec strict validate。
- 未执行真实 Hermes host、Milky 服务、消息发送或文件上传；真实部署环境仍需单独验证。

## [1.6.0] - 2026-09-09

### 新增

- 纯 `record` 语音在成功 materialize 后以 `MessageType.VOICE`、本地音频路径和 MIME
  交给 Hermes core，由 Hermes core 按宿主配置处理 STT。
- 新增 `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS`，默认关闭；开启后，已确认 session key 且宿主接受
  `inject_message` 时，群成员入退群事件可即时触发 Agent turn。

### 变更与边界

- 成功交给 Hermes core 的当前语音不再重复显示插件占位符；插件不读取或配置 STT provider，
  也不负责音频格式转换。某些 provider 不支持特定音频格式时，当前 Hermes core/provider 链路可能
  直接失败；格式转换不属于插件职责，插件不增加转码或重试。
- 群成员通知关闭时继续写入 system context，开启但注入失败或 session 未确认时保留上下文，
  不猜测 session key、不直接调用 Milky Action。

### 验证与边界

- 完整测试：875 passed，3 skipped；Ruff、格式检查、构建、`git diff --check` 和 OpenSpec strict
  validate 均通过。
- 未执行真实 Hermes/Milky 连接、消息发送或真实 STT provider 验证；目标环境仍需自行验证 provider
  对具体音频格式的支持情况。

## [1.5.0] - 2026-09-08

### 新增

- 新增 `MILKY_LONG_TEXT_FORWARD_THRESHOLD`，支持按可见规范化文本长度将超长文本和有序
  native `image`/`record`/`video` 批次收纳为单个 `forward`；默认值为 `0`，合法范围为
  `0..4096`，超过正值阈值才启用。
- 支持 QQ 会话介绍 system prompt section；在兼容的 Hermes 宿主中，为 friend/group 会话
  注入经过安全清洗的最小资料快照，不发起实时查询。

### 变更与修复

- 简化私聊历史上下文：普通私聊消息改为只保留正文，不再生成 sender、UID、消息 ID 和
  reply header；群聊历史继续保留既有 header 语义。
- 超长文本 forward 在身份不可用时使用固定安全身份 `user_id=10001`、`sender_name=QQ用户`；
  文档/文件继续使用独立 upload，不猜测分离的 `MEDIA:` 调用属于同一 forward 批次。

### 验证与边界

- 完整测试、Ruff、格式检查、构建、`git diff --check` 和 OpenSpec strict validate 均在发布前执行。
- 未执行真实 Milky 写入 smoke；真实 Hermes host、Milky 服务和消息发送仍需在目标部署环境中验证。

## [1.4.0] - 2026-09-07

### 变更与修复

- willingness 的 `mentionForce`、`quoteForce`、`mentionGain`、`quoteGain` 和 `pokeGain` 现在只
  消费明确指向当前 Bot 的结构化目标信号；他人/全体/`here` 提及、非 Bot 或未知引用和 poke
  不再错误触发对应 force 或 gain。
- 移除插件私有安全日志后端，统一通过 Hermes logger 输出 `hermes_plugins.milky.*` 命名空间下的
  结构化事件；保留 Action、SSE、入站、资源、出站、Mute 和 Tool 的结果分类与耗时观测。
- Tool 成功结果继续向调用方原样交付，日志不再复制 Tool 参数、响应 body、下载 URL、路径或自由文本。
- 完善日志、SSE 重连、生命周期、home channel、Tool 权限和敏感信息边界的架构文档、README 与
  OpenSpec 契约。

### 验证与边界

- 完整测试：810 passed，2 skipped；跳过项为当前环境缺少 Hermes host 的集成测试。
- Ruff、格式检查、构建和 OpenSpec strict validate 均通过。
- 未执行真实 Hermes host、Milky 服务、消息发送或文件上传；真实部署环境仍需单独验证。

## [1.3.0] - 2026-09-06

### 新增

- willingness 支持 `forceKeywords` 强制触发关键词；`MILKY_ALLOWED_CHATS` 支持按命名空间匹配
  `group:*` 和 `dm:*`。
- 初始群禁言同步对所有选中群同时发起成员查询，仍在全部结果收集完成后才开放适配器。
- 出站文本支持普通正文行中的未转义 `[SPLIT]`、`[[SPLIT]]` 字面量，以及完整 CQ-compatible
  候选和 malformed CQ-like 内容的明确解析边界。

### 变更与修复

- willingness 的 `replyCost` 改为在 `trigger` 决策完成后立即扣除；资源解析、映射、Hermes
  交接或后续任务失败不回滚该次扣费，且每个 trigger 最多扣除一次。
- 初始群禁言同步保留 fail-closed、`no_cache=true`、取消清理和稳态刷新有界并发语义。
- 收窄 CQ 保护范围：只保护语法完整的 CQ-compatible 候选，malformed 或未闭合 CQ-like 内容按
  普通文本处理；补充平台提示、架构文档和 README 的行为说明。

### 验证与边界

- 聚焦回归 42 passed；完整测试 813 passed、2 skipped。Ruff、格式检查、构建和 OpenSpec strict
  validate 均通过。
- 未执行真实 Milky/Hermes 连接、消息发送或文件上传；真实部署环境仍需单独验证。

## [1.2.0] - 2026-09-05

### 新增

- 将固定 QQ ToolSpec 从 17 个扩展到 25 个，新增 `get_group_file_download_url`、
  `get_group_files`、`accept_group_request`、`reject_group_request`、
  `accept_group_invitation`、`reject_group_invitation`、`get_friend_info` 和
  `set_group_member_special_title`。
- 支持严格独立行 `[SPLIT]` 控制出站文本，按顺序最多发送三条消息；空段、相邻空白行和
  长度预检遵循固定边界。
- 支持合法 friend/group `message_recall` 事件写入 context-only system context FIFO，不触发
  Agent、Will 或 Milky Action。
- 入站 face segment 支持使用插件内置 catalog 显示中文名称，并对 emoji pack、无效条目、
  冲突名称和缺失目录安全回退。
- 同一 trigger 内的重复入站图片支持按内容去重，并同步正文、媒体路径和 MIME 类型。
- 新增 `MILKY_MAX_LOCAL_MEDIA_BYTES`，默认值为 32 MiB，允许范围为 8–32 MiB，用于限制
  出站本地图片、音频、视频、CQ sticker 和文件上传的读取。

### 变更与修复

- 将 Milky 平台操作指引迁移到连接后渲染的 system prompt section，并注入已确认的 QQ UID
  和昵称；补充 `MEDIA:`、`[SILENT]`、`[SPLIT]` 和 CQ-compatible 语法说明。
- CQ sticker 的本地图片统一经过 materialization 后再发送，避免将本地路径直接交给 Milky。
- 修正自引用消息的 `your_previous_msg` 上下文标记，以及撤回事件的管理员文案判定。
- `/milky` 从返回原始 JSON 改为固定中文摘要，仅展示已确认的实现和协议字段。
- 统一 Milky QQ CQ reference 和 Action tools skill 命名，补充 face ID 和群文件参考资料。

### 已知边界

- Slash command 当前没有独立的发送者授权；ToolSpec 当前没有独立的调用者和目标授权，建议
  仅在成员可信且目标受控的会话中启用。
- 本版本自动化测试覆盖 fake Hermes、fake Milky transport 和脱敏 fixture；真实 Hermes 宿主
  与真实 Milky 服务的完整链路仍需在目标部署环境中验证。
