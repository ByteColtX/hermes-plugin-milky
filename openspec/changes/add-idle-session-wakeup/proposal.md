## Why

当前 Milky 插件只会在收到入站消息后驱动已有 Hermes session；长时间无人发言的会话不会被
主动检查。需要在不修改 Hermes Core、不过度触达未授权会话的前提下，由插件侧为已经存在且
命中 `MILKY_ALLOWED_CHATS` 的 `group:<id>` 或 `dm:<id>` session 提供一次可控的闲置唤醒。

## What Changes

- 新增插件侧 idle-session watcher，在连接完成后周期性检查已存在的 Hermes session。
- 只处理同时满足以下条件的会话：Hermes 已确认或恢复的 session、完整 chat key 命中
  `MILKY_ALLOWED_CHATS`、闲置时间达到阈值；不创建 session、不猜测 session key、不扫描白名单
  之外的会话。
- 新增单一 JSON 配置 `MILKY_PROACTIVE_POLICY`，包含 `enabled`、`idleSeconds`、
  `maxAttemptsPerDay` 和可选 `quietHours`；不新增独立会话列表、冷却或时区配置。
- 复用 Hermes Core 的时区解析，不在插件配置中重复声明时区；配置只在启动时解析，非法 JSON、
  类型、范围或时间格式阻止启动。
- 每个 chat 的同一 inactivity epoch 最多注入一次；新的人工消息会重新武装该会话。只有
  `inject_message()` 被宿主接受时才计入 `maxAttemptsPerDay`。
- 夜间免扰期间不注入、不消耗每日次数；退出免扰后若仍满足闲置条件，watcher 可在下一轮检查
  尝试一次。
- group session 只有在 `MuteTracker` 明确确认 Bot 当前可发言时才允许唤醒；dm session 不做
  群禁言查询。
- 通过 Hermes 已有 `inject_message` 交接以下固定英文事件内容；Agent 无有价值内容时必须回复
  `[SILENT]`，否则沿用现有 Hermes/Milky 出站流程：

  ```text
  <event idle_session_wakeup> System message: This conversation has been quiet for a long time. If appropriate, liven things up with a brief message, meme, or image. If you have nothing worthwhile to add, reply exactly [SILENT].
  ```

- watcher 在断开、重连和插件卸载时取消并释放；不修改 Hermes Core，不复制 Hermes Agent 队列，
  不直接调用 Milky Action 生成内容。

## Capabilities

### New Capabilities

- `idle-session-wakeup`: 定义白名单内、已存在 session 的闲置检测、夜间免扰、每日尝试上限、
  固定事件注入文案、busy/mute/失败处理和人工活动后的重新武装行为。

### Modified Capabilities

- `configuration`: 增加 `MILKY_PROACTIVE_POLICY` 的 JSON schema、默认值、范围、错误和 Hermes
  时区复用规则。
- `plugin-lifecycle`: 增加 watcher 的启动、取消、重连去重和停止语义，明确计时器由插件提供，
  不依赖或修改 Hermes Core。

## Impact

- 影响 `config/` 的启动配置对象和 manifest 配置声明；影响 `adapter.py` 的连接生命周期、已确认
  session 恢复和 `inject_message` 交接边界。
- 需要新增插件侧 watcher 与有限的进程内每日计数/inactivity epoch 状态，以及配置、watcher、
  注入拒绝、夜间免扰、白名单、禁言、busy、重连和停止路径测试。
- 需要更新 `README.md`、`ARCHITECTURE.md` 和对应 OpenSpec 主规范，说明单一 JSON 配置和主动
  注入的安全边界。
- 不新增 Milky HTTP Action、SSE 事件类型、外部持久化数据库或 Hermes Core 改动；watcher 状态
  随插件进程停止或重连丢失，已发送的 Hermes session/transcript 仍由 Hermes 所有。
