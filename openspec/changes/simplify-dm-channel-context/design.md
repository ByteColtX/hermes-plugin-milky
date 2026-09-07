## Context

当前 `channel_context` 的普通历史记录和当前 `MessageEvent.text` 共用普通消息 renderer。实际
流水线会在 detached batch 的资源解析完成后，把历史消息与 context-only system event 合并为
有序文本；历史消息已有 `chat_key`、scene、sender、ID、reply 和正文，但现有上下文输出没有
按 friend/group 区分。主规范也将所有普通历史统一描述为带 header 的格式。

本 change 只改变 dm 历史普通消息的 Agent-facing 展示。group 历史、当前消息文本、canonical
身份、reply metadata、system event、资源 materialization、buffer 顺序和空值语义都保持原状。

## Goals / Non-Goals

**Goals:**

- 将 dm 普通历史记录从 group 普通消息 header 中解耦。
- 让 dm `channel_context` 每条普通记录只输出已解析正文，并保持单行、顺序和安全转义边界。
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

### 1. 只在历史上下文边界选择 dm renderer

保持现有普通消息 renderer 负责当前 `MessageEvent.text`，并继续负责 group 历史记录。新增的
context renderer 只在构造 `channel_context` 的路径使用；它根据已验证的 dm/group chat
namespace 选择普通历史模板。这样 dm 的 body-only 规则不会意外改变当前触发消息，也不会
改变 group 输出。

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

### 3. chat 类型来自已确认的会话身份

renderer 必须使用 canonical/detached batch 已确认的 chat namespace 或等价 scene 信息，
不得从正文、sender 名称、header 文本或 raw payload 猜测。一个 detached batch 只对应一个
chat，因此普通历史记录与当前 system context 可以共享该上下文选择；system event 的固定
事件格式不受选择影响。

### 4. 保留现有编码、排序和空值语义

dm body 继续使用既有 body 编码，尤其将回车和换行编码为字面量 `\\n`；多条记录继续按
ingress sequence 使用单个换行拼接。没有普通历史和 system event 时仍返回 `None`，不返回
空字符串或伪造标题。group header 的尖括号、反斜杠和换行转义完全不动。

### 5. 以行为测试保护不变边界

测试应覆盖 dm wait/trigger 的 body-only 输出、dm reply 被省略但内部 metadata 保留、dm
与 system event 按顺序混排、dm 正文换行转义、空上下文，以及同一组案例中的 group 输出
保持既有值。主规范和 `ARCHITECTURE.md` 在实现交付并完成验证后再同步为新的稳定契约。

## Risks / Trade-offs

- [dm 历史不再显示 sender、message ID 或 reply 关系，Agent 失去部分可追溯信息] → 这是私聊降噪的明确取舍；canonical、当前消息文本和 Hermes 内部 reply metadata 仍保留这些事实。
- [renderer 入口选择错误可能把 group 误渲染成 body-only] → 只使用已验证 chat namespace/scene，并增加 group regression assertions，禁止从展示文本推断。
- [body-only 私聊与事件文本混排时可读性下降] → system event 继续保留 `<event <event_type>>` 标识，并测试混排顺序。
- [旧规范与实现短暂不一致] → 在实现和聚焦测试完成后同步 `chat-session-buffer`、`hermes-message-pipeline` 与 `ARCHITECTURE.md`，未验证前不宣称交付。

## Migration Plan

1. 补充脱敏 dm wait/trigger 和 dm/system context fixture/test，并加入 group 输出不变断言。
2. 在历史 `channel_context` 组装边界接入独立 dm renderer，保持当前 `MessageEvent.text` 和 group renderer 原路径。
3. 运行聚焦入站测试、Ruff、format、build、diff 检查及 OpenSpec strict validation；按失败分类修正。
4. 同步稳定契约文档；若需要回滚，移除 dm renderer 选择并恢复统一历史 header，不涉及远端状态或数据迁移。
