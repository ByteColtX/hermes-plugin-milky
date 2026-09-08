## Context

当前 `record` 已在 trigger resolver 中通过 Hermes 的 audio helper 生成本地 materialization，并由 mapper 写入 `media_urls`/`media_types`；但纯音频路径仍被归类为 `MessageType.AUDIO`。Hermes core 会将 `AUDIO` 和 `DOCUMENT` 排除在自动 STT 输入之外，而 `VOICE` 才能进入既有语音处理。规范化阶段仍需要保留 typed `record` 和稳定 placeholder，供 wait、历史上下文和资源失败降级使用。

本设计只调整插件到 Hermes 的 MessageEvent 边界。Hermes core 的 STT provider、配置读取、转录 fallback 和 Agent-facing 提示是外部既有能力，不在本仓库内复制或改写。

## Goals / Non-Goals

**Goals:**

- 让成功 materialize 的纯当前 `record` 以 `MessageType.VOICE` 交给 Hermes core。
- 保持音频本地路径与 MIME 在 `media_urls`/`media_types` 中一一对应，并沿用 Hermes 的下载、缓存和安全边界。
- 只从当前消息中移除已经成功交给 core 的插件 record placeholder，避免掩盖资源失败原因或影响历史上下文 renderer。
- 通过 fake Hermes 类型、resolver 和 `handle_message()` 边界测试验证 STT eligibility、媒体配对和提示去重。

**Non-Goals:**

- 不实现、选择或配置任何 Milky 侧 STT provider。
- 不修改 Hermes core，不在插件中复制 core 的转录文本、失败提示或 `stt.enabled` 逻辑。
- 不把历史 `channel_context` 的音频重新 materialize 成本次 Agent 输入，也不为历史语音执行自动 STT。
- 不改变出站 `record`、图片、视频、文件、reply、Gate、Will、dedup 或 temp 消息语义。

## Decisions

### 1. 只在纯 record 且有成功音频 materialization 时选择 `VOICE`

mapper 以 canonical segment 和当前 resolved materialization 共同决定类型。当前消息只有 `record`（允许多个）且至少一个 record 已得到有效本地音频 materialization 时使用 `MessageType.VOICE`；文本或其他受支持内容的混合消息沿用现有混合类型和每附件 MIME 判定。这样不把普通 audio attachment 或 document 误标成 voice，也不改变 Hermes core 对混合事件的既有分类。

备选方案是所有 `record` 都使用 `VOICE`，但这会在资源失败或混合消息中扩大语义，且无法替代 `media_urls` 的本地路径校验，因此不采用。

### 2. 复用现有 resolver 和媒体数组，不新增 STT 通道

record 继续走既有 `get_resource_temp_url` → Hermes `cache_audio_from_url` → 本地路径校验链路。mapper 只消费 resolver 返回的 materialization，并同时生成等长、同序的 `media_urls` 和 `media_types`。远端 URL、resource ID、文件内容和猜测路径不得越过该边界。

备选方案是插件直接调用 `transcribe_audio` 或新增 Milky STT 配置，但这会复制 Hermes core 的 provider 生命周期和 fallback 语义，并破坏媒体所有权，因此不采用。

### 3. 按 typed reference slot 只抑制当前成功 record 的 placeholder

规范化结果继续保留 `[record:NOT SUPPORTED]` 作为稳定内部/历史降级文本。trigger resolver 或 mapper 使用 `record` 引用的已确认槽位和成功 materialization 结果，生成当前 Agent-facing 文本时只删除成功 occurrence 的插件 placeholder；失败 occurrence 仍保留安全降级。不得通过模糊的全局字符串替换删除失败 record，避免多 record 消息错配。

历史 `channel_context` 继续使用历史 renderer 的既有 body，不参与当前 mapper 的 record placeholder 抑制；由于历史 record 不进入本次媒体数组，插件不宣称其已被 STT。

### 4. 把提示职责留给 Hermes core

插件不检查 STT 是否配置、不插入转录文本、不追加“无法转录”或“STT 未启用”提示。只要当前 record 成功进入 `media_urls` 且类型为 `VOICE`，core 负责成功、失败、空转录和禁用状态的 Agent-facing 结果。插件测试只验证交给 core 的事件输入和插件未重复写入 record 提示，不断言 provider 的具体文案。

## Risks / Trade-offs

- [Hermes 版本的 `MessageType` 或 STT 判定发生变化] → 使用显式注入的 Hermes 类型做单元测试，并保留真实宿主集成测试；若缺少 `VOICE` 或 audio helper 能力，按 `unsupported` 安全失败，不伪造 STT。
- [多媒体消息的类型与 core 的每附件判定不一致] → 只对纯 record 采用 `VOICE`，混合事件继续保留 `media_types`，并增加纯 record、record+text、record+image 和 record+file 的回归覆盖。
- [按字符串删除 placeholder 误删失败 occurrence] → 复用 `MediaResourceReference` 的 `body_start`/`body_end` 和 materialization 结果，按 occurrence 处理；没有可信槽位时不删除。
- [历史 record 没有自动 STT，Agent 只能看到占位] → 在规范和测试中明确这是当前设计边界；未来若要支持历史媒体，需单独变更资源集合、context renderer 和 core 输入契约。
- [真实 Hermes provider 未配置导致无法验证转录文案] → 本 change 的验收以 MessageEvent 类型、媒体数组和提示去重为主；真实 provider 结果保留为实机 evidence，不把 fake host 通过报告成 provider 集成成功。

## Migration Plan

1. 先补充/更新脱敏 fixture、mapper/resolver 单元测试和 fake Hermes pipeline 测试。
2. 再实现纯 `record` 的类型选择与当前 placeholder 抑制，运行聚焦测试及项目质量门禁。
3. 在真实 Hermes + Milky 环境验证 STT 已配置、未配置/禁用、provider 失败和资源失败四类结果；不记录音频路径、URL、正文或凭证。
4. 若需要回滚，只回退插件变更；Hermes core 配置和既有出站能力不受影响。

归档前必须确认所有任务完成，并保留真实环境未覆盖边界；OpenSpec validate 通过不等于真实 STT provider 已认证。
