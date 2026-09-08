## Context

当前 `channel_context` 的普通历史记录和当前 `MessageEvent.text` 共用普通消息 renderer。实际
流水线会在 detached batch 的资源解析完成后，把历史消息与 context-only system event 合并为
有序文本；历史消息已有 `chat_key`、scene、sender、ID、reply 和正文，但现有上下文输出没有
按 friend/group 区分。主规范也将所有普通历史统一描述为带 header 的格式。

当前实现存在多个需要同时修正的 renderer 出口：`DetachedTriggerBatch.channel_context` 直接
从未解析的历史消息构造上下文；`inbound.pipeline._render_resolved_history()` 在实际
`MessageEvent` 交接前用资源解析后的正文重新构造上下文；`session.buffer.render_channel_context()`
是公开导出，并由 `format_channel_context` 兼容别名转发。三者都经过
`render_ordered_context()` 或等价的普通记录分支，但该分支目前默认调用带 header 的
`render_message_record()`。只修改 detached batch 属性会遗漏实际 Hermes 交接，只修改 pipeline
又会让公开 helper 和直接访问结果继续分叉。

本 change 只改变 dm 历史普通消息的 Agent-facing 展示。group 历史、当前消息文本、canonical
身份、reply metadata、system event、资源 materialization、buffer 顺序和空值语义都保持原状。

## Goals / Non-Goals

**Goals:**

- 将 dm 普通历史记录从 group 普通消息 header 中解耦。
- 让 dm `channel_context` 每条普通记录只输出已解析正文，并保持单行、顺序和安全转义边界。
- 让所有产生历史 `channel_context` 的入口共享同一套 dm/group 选择规则；pipeline 入口仍使用资源解析后的正文，直接 batch/helper 入口使用其已提供的正文。
- 保持 group renderer 与当前 `MessageEvent.text` 的既有输出字节级稳定。
- 让 dm 普通历史与 system event 混排时仍按 ingress sequence 合并，且 system event 继续可识别。
- 用回归测试固定 dm、group、system context 和边界字符的行为差异。

**Non-Goals:**

- 不为 group 增加 timestamp、字段或新的模板。
- 不改变当前 trigger 的 `MessageEvent.text`，也不移除当前消息的 reply metadata。
- 不修改 canonical 字段、Milky parser、Will/Gate/dedup、资源查询、媒体去重或出站能力。
- 不把 dm 的 system event 改成 body-only；`<event ...>` 是事件类型边界，不是普通消息 header。
- 不从 body、sender 名称或 raw payload 推断 chat 类型或重新构造消息身份。

## Decisions

### 1. 统一历史 renderer 策略，保留多个入口的边界

保持现有普通消息 renderer 负责当前 `MessageEvent.text`，并继续作为 group 普通消息的
header renderer。新增的 chat-aware context renderer 负责历史普通记录，并由有序上下文合并
器统一调用；它根据已验证的 dm/group chat namespace 选择普通历史模板。这样 dm 的 body-only
规则不会意外改变当前触发消息，也不会改变 group 输出。

三个入口分别按以下边界接入同一策略：

- `DetachedTriggerBatch.channel_context` 传入 batch 自身已验证的 `chat_key`，渲染 batch
  当前持有的历史正文；它没有资源解析结果，不自行联网或补全正文。
- `_render_resolved_history()` 在 resolver 完成后传入 batch 的 `chat_key`，使用
  `ResolvedMessage.body` 渲染实际交给 Hermes 的历史上下文；它不能回退到 batch 属性的
  未解析正文。
- 公开 `render_channel_context()` 保留现有导出和 `format_channel_context` 别名，支持显式
  `chat_key`，或仅在所有消息都提供同一个经验证的 `chat_key` 时选择模板；缺少或混用 chat
  namespace 时失败，不从正文、sender 名称或 raw payload 猜测 group。

备选方案是直接让现有 `render_message_record` 按 chat 类型改变。该方案会同时改变当前
`MessageEvent.text`，扩大行为范围并破坏当前文本契约，因此不采用。

### 2. dm 普通历史使用 body-only，system event 保留事件 header

dm 的每条普通历史记录只取资源解析完成后的安全正文，并使用现有 body 换行编码；不输出
sender、uid、`msg_id`、`reply_to` 或新标题。system event 仍使用 `<event <event_type>> <body>`，
因为事件类型是识别撤回、nudge 等 observe-only 信息所需的边界，而不是私聊普通消息的冗余
身份 header。

备选方案是保留一个最小的 `reply_to` header，或把 system event 也压成 body-only。前者仍会
把私聊历史中的非必要元数据带入 Agent 上下文，后者会让 system event 与普通正文不可区分，
均不符合已确认范围。

### 3. chat 类型来自已确认的会话身份，并贯穿有序合并

renderer 必须使用 canonical/detached batch 已确认的 chat namespace 或等价 scene 信息，
不得从正文、sender 名称、header 文本或 raw payload 猜测。一个 detached batch 只对应一个
chat，因此普通历史记录与当前 system context 可以共享该上下文选择；system event 的固定
事件格式不受选择影响。`render_ordered_context()` 只负责按 ingress sequence 合并记录，
普通记录必须调用 chat-aware renderer，不能在合并路径中重新默认到 group header。

### 4. 保留现有编码、排序和空值语义

dm body 继续使用既有 body 编码，尤其将回车和换行编码为字面量 `\\n`；多条记录继续按
ingress sequence 使用单个换行拼接。没有普通历史和 system event 时仍返回 `None`，不返回
空字符串或伪造标题。group header 的尖括号、反斜杠和换行转义完全不动。

### 5. 以行为测试保护所有出口和不变边界

测试应覆盖 dm wait/trigger 的 body-only 输出、dm reply 被省略但内部 metadata 保留、dm
与 system event 按顺序混排、dm 正文换行转义、空上下文，以及同一组案例中的 group 输出
保持既有值；还必须分别验证 detached batch 属性、公开 helper 和资源解析后的 pipeline
输出不会因入口不同而恢复普通消息 header。主规范和 `ARCHITECTURE.md` 在实现交付并完成
验证后再同步为新的稳定契约。

## Risks / Trade-offs

- [dm 历史不再显示 sender、message ID 或 reply 关系，Agent 失去部分可追溯信息] → 这是私聊降噪的明确取舍；canonical、当前消息文本和 Hermes 内部 reply metadata 仍保留这些事实。
- [renderer 入口选择错误可能把 group 误渲染成 body-only] → 只使用已验证 chat namespace/scene，并增加 group regression assertions，禁止从展示文本推断。
- [body-only 私聊与事件文本混排时可读性下降] → system event 继续保留 `<event <event_type>>` 标识，并测试混排顺序。
- [旧规范与实现短暂不一致] → 在实现和聚焦测试完成后同步 `chat-session-buffer`、`hermes-message-pipeline` 与 `ARCHITECTURE.md`，未验证前不宣称交付。

## Migration Plan

1. 补充脱敏 dm wait/trigger 和 dm/system context fixture/test，并加入 group 输出不变断言；覆盖 detached batch 属性和公开 helper。
2. 在共享历史 renderer/有序合并边界接入 chat-aware dm renderer，并同时连接 detached batch 属性、公开 helper 和资源解析后的 pipeline 路径；保持当前 `MessageEvent.text` 和 group renderer 原路径。
3. 运行聚焦入站测试、Ruff、format、build、diff 检查及 OpenSpec strict validation；按失败分类修正。
4. 同步稳定契约文档；若需要回滚，移除 dm renderer 选择并恢复统一历史 header，不涉及远端状态或数据迁移。
