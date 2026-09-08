## Context

当前 adapter 在 `connect()` 中先完成 `MuteTracker.initialize()`，再恢复 Hermes 已持久化的
Milky session route，随后启动 pipeline 和 SSE；`disconnect()` 已负责取消事件流并关闭 pipeline、
sender、MuteTracker 与 client。adapter 已有 `inject_message()` 边界：它只接受 Hermes 已确认的
session key，并把布尔返回值解释为“注入请求被宿主接受”，不会把接受结果误报成 QQ 已发送。

Hermes 的 `AsyncSessionStore.list_sessions()` 返回已有的 `SessionEntry`，其中包含 `session_key`、
`updated_at` 和 `origin`；`origin.chat_id` 可提供插件自己的 `group:<id>`/`dm:<id>` chat key。
Hermes 的 `hermes_time.now()` 使用 `HERMES_TIMEZONE`、Hermes 配置中的 `timezone` 或系统本地时区，
因此插件不需要再定义一套时区配置。Hermes `PluginContext.spawn_task()` 提供受宿主管理的后台任务，
而 `PluginContext.inject_message()` 在 gateway 中可能打断正在运行的 turn；主动唤醒必须先检查 busy。

## Goals / Non-Goals

**Goals:**

- 在插件侧提供固定周期、可取消、最多一个实例的 watcher。
- 只从 Hermes 已有 session route 中选择 Milky、合法且命中 `MILKY_ALLOWED_CHATS` 的 group/dm。
- 将闲置 epoch、人工活动重武装、每日 accepted injection 计数、quiet hours 和安全降级做成可单测的
  进程内组件。
- 复用现有确认 session key、MuteTracker 和 Hermes injection/outbound 边界。

**Non-Goals:**

- 不修改 Hermes Core，不增加 Core timer、Agent queue、session API 或 prompt section。
- 不通过 `get_or_create_session()`、Milky Action、SSE 新事件或 home channel 生成候选或内容。
- 不新增独立 chats、cooldownSeconds 或 timezone 配置；chat 授权继续只由 `MILKY_ALLOWED_CHATS`
  决定。
- 不把主动唤醒变成普通 `message_receive`，不经过普通 Gate/Will/reply-cost 路径，也不复制 Hermes
  busy/follow-up/interrupt 队列。

## Decisions

### 1. 插件 watcher 使用宿主任务所有权，扫描周期固定为 60 秒

在 adapter 完成初始同步、恢复 session route、启动 pipeline 和 event stream 后，使用
`plugin_context.spawn_task()` 创建单个 watcher。watcher 用 `asyncio.Event`/取消响应等待 60 秒，
不把扫描周期暴露为配置；`disconnect()` 先取消并等待该 task，再释放其他组件。若宿主没有可用的
`spawn_task`，主动能力按 `unsupported` 保持关闭，不回退为无主的长期 task。

这比使用 Hermes `/loop` 或 cron 更合适：这些机制面向已有 loop/job 语义，会改变 session/Agent
流程；本能力只需要插件自己的低频观察和严格 injection。固定周期也避免新增一个用户需要理解的
调度配置。

### 2. 候选来自 `list_sessions()`，授权和确认使用两道独立检查

每轮读取 `gateway_runner.async_session_store.list_sessions()`；异步结果由 adapter 等待，读取失败
只影响当前轮。对每个 entry：

1. 从 `origin.platform.value` 确认 `milky`，从 `origin.chat_id` 校验完整 `group:`/`dm:` chat key；
2. 用启动时解析的 allowlist 精确匹配或匹配同命名空间通配符；空 allowlist 对主动能力 fail-closed；
3. 用 adapter 的 `_confirmed_session_keys[chat_key]` 取已确认 session key，并要求它与当前 entry
   的 route 可关联；找不到则跳过；
4. 读取 `entry.updated_at` 作为首次观察该 session 的 idle 基线。

不遍历 Milky 群列表来构造候选，不从 chat key 组合 Hermes key，也不调用任何 session creation API。
同一 chat 如果 session store 返回重复或异常 entry，按 chat key 去重并选择一条可确认 route；冲突时
按 unsupported 跳过，避免向错误 session 注入。

### 3. 用插件拥有的 activity epoch 隔离人工活动和 synthetic turn

新增小型进程内 tracker，按 chat 保存：

- 最近一次人工活动时间/epoch；
- 当前 epoch 是否已被宿主接受主动注入；
- Hermes 当前本地日期和当日 accepted injection 次数；
- 当前主动 turn 的 in-flight 标记及安全诊断。

首次看到已有 entry 时，以 `updated_at` 初始化 idle 基线；普通 `message_receive` 在既有 canonical、
Gate 允许后通知 tracker，更新人工活动并清除“已触发”标记。Gate deny、temp、system event、普通
Agent 回复和出站结果不更新人工活动。主动事件通过 `inject_message()` 直接交给 Hermes，不经过
Milky 普通入站 pipeline，因此不会调用 activity recorder；即使 Hermes 因 synthetic user message
更新 `SessionEntry.updated_at`，tracker 仍以人工活动 epoch 为准，不会自触发第二次。

一次注入只有在返回 `True` 后才标记 epoch 和每日计数；返回 `False`、异常或宿主能力不存在不计数，
也不宣称 turn 已创建。拒绝可以在下一轮重新判断，以便 session route 或 busy 状态后来恢复；接受后
同一 epoch 永不重试，Agent 回复失败也不回滚。

### 4. quiet hours 只保存本地时间窗口，不在插件重复解析时区

配置 parser 只负责 JSON shape、字段和 `HH:MM` 值域。watcher 每轮懒加载 Hermes `hermes_time.now()`
（或等价的宿主官方时钟边界），用该 aware datetime 的本地日期和本地时间执行计数/免扰判断。`start`
晚于 `end` 时按跨午夜区间判断；相等值在启动期拒绝，避免“全天免扰/完全关闭”两种歧义。Hermes
时区配置变化仍由 Hermes 负责，插件不读取或缓存 `timezone` 环境变量。

### 5. 注入前 fail-closed 检查 busy 和 MuteTracker

`inject_message()` 本身可能中断正在运行的 turn，所以 watcher 在提交前检查：

- 当前 tracker 是否已标记该 chat 的主动 turn in-flight；
- Hermes Gateway runner 已暴露的 running-agent 状态是否包含确认的 session key；
- 如果 running-agent 能力不存在、结构异常或无法确认，按 busy/unsupported 跳过；
- group 使用 `MuteTracker.get_snapshot()`/等价只读快照，要求 member 与 whole 都明确为 `unmuted`；
  `unknown`、初始化中、刷新失败和 muted 均跳过；dm 不访问 MuteTracker。

这里不调用 refresh Action：状态查询和刷新所有权仍属于 `MuteTracker`，watcher 不能为了主动发言
绕过其 fail-closed 边界。由于 `_running_agents` 是 Hermes 当前实现的运行态观察面而非插件自有队列，
访问封装在兼容 helper 中；未来宿主提供正式 busy 查询时替换 helper，不改变本 spec。

### 6. 使用固定 event body 和现有 injection/outbound 闭环

tracker 通过 adapter 现有 `inject_message(content, role="user", session_key=...)` 提交单条固定英文
event body。Hermes 接受后负责创建 synthetic turn、执行 Agent；Agent 返回 `[SILENT]` 时由既有 Hermes
语义抑制出站，否则由已有 Milky outbound sender 发送文本或媒体。插件不解析主动回复、不直接调用
`send_group_message`/`send_private_message`，也不把主动 body 写入普通 message dedup、wait buffer、
Will 或 reply cost。

为保持 busy 观察准确，adapter 可在现有 processing hook 看到带 `idle_session_wakeup` 标记的 turn
时更新本地 in-flight；hook 缺失不影响“接受后同 epoch 不重试”，只会让下一轮在无法确认 busy 时
按安全策略跳过。

### 7. 仅在本 change 的边界增加配置和文档

`MilkyConfig` 增加一个结构化 proactive policy（不是四个平铺环境变量），manifest 只增加一个
optional env；redacted summary 只输出 enabled、阈值、次数和是否配置 quiet hours，不输出聊天 ID、
正文或凭证。`README.md` 与 `ARCHITECTURE.md` 说明：白名单为空时普通入站仍保持原语义，但主动
唤醒没有候选；配置修改须重启；进程重启不恢复本地次数/epoch。

## Risks / Trade-offs

- [Risk] `inject_message` 的接受只代表异步交接，Agent 可能随后失败或输出 `[SILENT]`。
  → 接受即消耗一次并锁定当前 epoch；后续结果不回滚、不重复骚扰，结果仍归 Hermes/现有出站链路。
- [Risk] Gateway busy 状态是宿主运行态，缺少正式公共查询时可能无法判断。
  → 只读检查现有 running-agent 观察面；缺失或异常时 fail-closed 跳过，不自行打断 turn。
- [Risk] session store 读取失败、route 暂时未恢复或 MuteTracker 状态未知会漏掉一次机会。
  → watcher 下一轮继续；不创建 session、不强行刷新禁言、不把失败变成已发送。
- [Risk] 重连或进程重启后丢失 epoch/每日计数可能造成同一自然日再次唤醒。
  → 这是进程内状态的明确边界；接受后仍保证单次生命周期内不重复，若要跨重启配额需另立持久化 change。
- [Risk] `updated_at` 包含 Hermes synthetic activity 的实现细节可能随 Core 变化。
  → 首次冷启动使用 `updated_at`，稳态以插件记录的人工 activity callback 为准；synthetic injection
  不进入 callback，Core 变化不会将 Agent 回复误判为人工重武装。

## Migration Plan

1. 实现阶段先补 `MILKY_PROACTIVE_POLICY` parser/manifest 契约测试，再补 tracker 的时间、epoch、
   quiet hours 和每日计数单元测试。
2. 接入 adapter 生命周期和普通 inbound activity callback，使用 fake session store、MuteTracker、
   busy runner 与 injection context 验证 group/dm、白名单、拒绝和清理路径。
3. 更新 README、ARCHITECTURE 和主 specs；运行聚焦测试、完整质量门禁与严格 OpenSpec 校验。
4. 发布后未配置或 `enabled=false` 时行为完全不变；启用时先使用 `maxAttemptsPerDay=1` 和明确
   `quietHours` 观察日志，再按需要调整 idle threshold。
5. 回滚时删除 `MILKY_PROACTIVE_POLICY` 或设为 `{"enabled":false}`；不需要迁移数据，进程内 tracker
   随进程退出释放。
