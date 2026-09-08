## Context

当前 `inbound/system_events.py` 将五类受支持事件转换为 `ContextOnlyEvent`，
`inbound/pipeline.py` 再把非 `message_receive` 事件写入按 chat 隔离的 system context FIFO；
`session/buffer.py` 负责统一添加 `<event <event_type>>` 前缀。普通路径只在下一次同 chat
消息 trigger 时消费该 FIFO。启动配置由 `MilkyConfig` 一次性解析，adapter 在完成初始化后
创建入站 pipeline。

Hermes 已确认的 `PluginContext.inject_message()` 是会话注入接口：CLI 可直接排队，Gateway
需要已有 session key、`allow_gateway_injection` 授权和 live gateway；adapter 可从 Hermes
持久化 session route 恢复已有 key；返回 `True` 只代表异步
注入请求被接受。该接口注入的是 synthetic user message，不是 system prompt section，也不
修改 Hermes core。对应 contract 见 `specs/system-events-and-safety/spec.md`。

## Goals / Non-Goals

**Goals:**

- 将 `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 默认设为 `false`，并在启动期固定其值。
- 无论开关状态，保留字段完整的入群/退群事件到 system context；关闭时使用无 Tip 的基础英文 body。
- 开启时在成员事件 body 末尾追加固定 Tip，并在注入能力接受后立即消费该群待处理的 system context、触发一个 Agent turn。
- 保持事件 ingress sequence、FIFO、普通消息消费路径、英文文案、安全字段过滤和失败保留语义可测试。

**Non-Goals:**

- 不修改 Hermes core、prompt cache 或 system prompt section；不把动态成员事件伪装成稳定 system prompt。
- 不直接调用 Milky 出站 Action；Agent turn 产生的回复仍由 Hermes 既有平台交接处理。
- 不从 `group:<id>`、`dm:<id>` 或其他插件 chat key 猜测 Hermes Gateway session key；未确认 key 时不得注入。
- 不复制 Hermes 的 Agent 队列、busy/follow-up/interrupt 逻辑；注入调度和冲突语义归 Hermes 所有。

## Decisions

### 1. 单一启动开关，默认关闭即时通知

在 `MilkyConfig` 增加 `group_member_event_notifications: bool`，由
`MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 解析，缺失默认 `false`，只接受大小写不敏感的
`true`/`false`。其他值在启动期报 `ConfigError`，配置完成后本次插件生命周期内不热切换。

一个总开关同时控制入群和退群，避免两类事件出现不一致的社交策略。默认关闭是为了避免
部署升级后突然产生 Agent turn；即使关闭，事件仍保留到普通消息的 context 消费，因此不会
静默丢失事件事实。

替代方案是默认开启或拆成两个变量。默认开启会产生未显式同意的即时 turn，拆分变量则增加
配置和测试面，均不符合本 change 的低副作用目标。

### 2. 先渲染基础 body，再按开关追加 Tip

系统事件渲染层先生成不含 Tip 的英文基础 body。关闭开关时直接将基础 body 写入 system
context；开启开关时在同一条 body 的末尾追加 delta spec 中固定的 `Tip`。Tip 的存在只由
启动配置决定，不由注入是否成功决定：注入失败时，带 Tip 的记录仍保留在 FIFO，稍后的普通
消息可以消费它。

`Details` 继续按既有确认字段和固定 key 顺序生成，缺失的 `operator_id`/`invitor_id` 省略；
不接受 payload 中的 nickname、display text、URL、timestamp、raw 扩展或用户正文。nudge 和
recall 使用固定英文 body，事件类型前缀仍由 context renderer 添加。

### 3. 通过 Hermes 会话注入实现即时 turn

成员事件在同 chat admission 内完成 append。开关开启时，pipeline 读取当前 chat 的待处理
system context，按 ingress sequence 渲染为注入内容，并向 Hermes 注入接口提交一次 synthetic
user message；注入内容必须保留已渲染的 `<event ...>` 行和 Tip。只有注入接口返回接受后，
系统才原子 drain 这批 system context，避免拒绝、无 session 或宿主停止时丢失事件。

注入需要由宿主边界提供已确认或持久化恢复的 Gateway session key 和授权结果；实现不得把 Milky 的
`group:<id>` 直接当作 Hermes key。注入返回成功后不等待 Agent 完成，也不复制 Hermes 的
busy/interrupt/follow-up 队列；若 Hermes 当前 turn 正在运行，使用其已定义的 injection 语义。

关闭开关时不调用注入接口，事件留在 system context，沿现有普通消息 trigger 路径消费；
这使“默认关闭”与“开启后立即通知”形成清晰的可观察差异。

### 4. 失败时保留缓冲，保持其他系统事件不变

session key 缺失、Gateway injection 未授权、live gateway 不可用或 `inject_message` 返回
拒绝时，系统记录固定的 `unsupported`/`failed` 分类并保留 system context；不重复提交、不
主动发送 fallback 消息。后续普通消息仍可以按既有顺序消费该记录。

nudge、recall、request、file upload 和未知事件不受成员开关影响；它们继续遵守原有的
observe-only/context-only、Gate/Will、reply cost 和敏感字段边界。即时成员通知是唯一新增的
系统事件到 Agent turn 的显式例外。

### 5. 测试与文档覆盖双路径和宿主边界

配置测试覆盖默认 `false`、大小写变体和非法值；渲染测试覆盖无 Tip/有 Tip 的完整英文 body、
可选字段、事件顺序和 payload 污染；pipeline 测试覆盖关闭时留存、开启时成功 drain+注入、
注入拒绝时保留，以及其他事件不触发即时 turn。Fake host 只证明本地交接逻辑，真实 Gateway
授权和 session key 能力保持为受控集成边界，不报告未验证的实机成功。

## Risks / Trade-offs

- [Risk] 默认关闭会让已有部署不再即时欢迎/告别，但成员事实仍会在下一次普通消息中出现。
  → 文档明确 `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS=true` 的启用方式，并在测试中断言关闭路径仍保留基础 body。
- [Risk] `inject_message` 在 Agent 忙碌时遵循 Hermes 的既有中断/注入语义，可能打断当前 turn。
  → 不在插件复制或重写队列；记录接受/拒绝分类，具体 busy 行为交由 Hermes contract 管理。
- [Risk] Gateway 没有 session key 或未授予 `allow_gateway_injection` 时，开启通知无法即时触发。
  → 不猜测 key、不丢弃带 Tip 的事件，保留到下一次普通消息，并记录低敏失败分类。
- [Risk] 即时 turn 的 synthetic user 内容可能改变用户可见回复节奏。
  → 只在用户显式开启开关时启用，Tip 使用条件式措辞，且不直接调用 Milky 出站 Action。
- [Risk] 英文 body、Tip 和即时 drain 会改变现有 snapshot/fixture 及缓冲生命周期。
  → 先补契约 fixture 和双路径 pipeline 测试，再运行项目质量门禁；失败注入路径保留可恢复上下文。

## Migration Plan

1. 实现阶段先补配置、渲染、pipeline 和 Hermes injection fake 的契约测试，再接入生产交接路径。
2. 发布后未设置变量的现有部署默认为关闭：成员事件仍进入 system context，但不带 Tip、不即时触发。
3. 需要成员即时通知时设置 `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS=true`，确认 Hermes plugin entry 已授予
   `allow_gateway_injection`，并重启 Gateway 使配置生效。
4. 回滚时删除该变量或显式设置 `false`；不需要迁移持久化数据，短期 system context 按原有 FIFO
   消费或淘汰。若回滚到不认识注入能力的旧版本，旧版本应继续按其默认 observe-only 行为运行。

## Open Questions

无。session key 无法确认时的处理已固定为保留缓冲并记录安全失败；是否需要更复杂的多 session
广播或排队策略属于后续独立 change。
