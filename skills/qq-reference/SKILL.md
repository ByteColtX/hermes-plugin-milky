---
name: qq-reference
description: Milky QQ Agent 出站 CQ-compatible 语法和工具边界参考
---

# Milky QQ reference

本 skill 是 `hermes-plugin-milky:qq-reference` 的只读参考资料，按需加载。这里的
CQ-compatible 语法只供 Agent 出站适配层使用，不是 OneBot v11 传输协议，也不会让
Milky 支持任意 OneBot Action、WebSocket RPC 或未注册工具。

## 基础消息控制

平台提示中已经提供最小规则：

- `[CQ:at,qq=<uid>]`：提及一个用户。`<uid>` 必须原样来自当前消息或
  `channel_context` 消息头中的 `uid`。
- `[CQ:reply,id=<msg_id>]`：引用一条消息。`<msg_id>` 必须原样来自当前消息或
  `channel_context` 消息头中的 `msg_id`。
- 默认不自动提及，也不自动引用当前消息。没有真实 ID 时不要猜测、补造或从昵称和正文
  推断控制码。
- 多个控制码可以连续放在正文前；它们会按出现顺序形成同一条消息的结构化 segment。

## NapCat CQ 类型矩阵

“native”表示当前 formatter 有确认的 Milky outgoing segment 映射；“fallback”表示
系统会识别该 CQ 片段，但把完整、未修改的 `[CQ:...]` 原文作为 text fallback segment 发送。
fallback 只表示原文放行，不表示 CQ 语义已经执行。

| CQ 类型 | 当前状态 | Milky 映射或限制 |
| --- | --- | --- |
| `text` | native | `text` segment；需要 `text` 参数 |
| `face` | native | `face` segment；使用 `id`，可选 `large=0/1` |
| `image` | native | `image` segment；使用 `file`，仅确认 `type=normal/sticker` |
| `record` | native | `record` segment；使用 `file` |
| `video` | native | `video` segment；使用 `file` |
| `at` | native | `mention` segment；使用十进制 `qq`，`qq=all` 保持 fallback |
| `rps` | fallback | 没有确认的 Milky native segment |
| `dice` | fallback | 没有确认的 Milky native segment |
| `shake` | fallback | 没有确认的 Milky native segment |
| `poke` | fallback | 需要独立 Action，不进入 message segment |
| `share` | fallback | 没有确认的 Milky native segment |
| `contact` | fallback | 没有确认的 Milky native segment |
| `location` | fallback | 没有确认的 Milky native segment |
| `music` | fallback | 没有确认的 Milky native segment |
| `reply` | native | `reply` segment；使用十进制 `id` |
| `forward` | fallback | CQ 的转发 ID 不能直接映射为已确认的出站消息结构 |
| `node` | fallback | 没有确认的 Milky native segment |
| `json` | fallback | 不根据 CQ 内容猜测 Action 或 segment |
| `mface` | fallback | 没有确认的 Milky outgoing market-face 映射 |
| `file` | fallback | 文件不得进入 message segment；必须使用独立 file upload |
| `markdown` | fallback | 没有确认的 Milky native segment |
| `lightapp` | fallback | 没有确认的 Milky native segment |
| `anonymous` | fallback | 没有确认的 Milky native segment |
| `redbag` | fallback | 没有确认的 Milky native segment |
| `gift` | fallback | 没有确认的 Milky native segment |
| `cardimage` | fallback | 没有确认的 Milky native segment |
| `tts` | fallback | 没有确认的 Milky native segment |
| `xml` | fallback | 没有确认的 Milky native segment |

未知类型、控制码边界不完整、字段缺失、ID 不是无前导零的十进制值、数值超出范围或
转换器异常时，只回退当前完整 CQ 原文，继续处理同一条消息中的其他内容。空白消息和
非法出站目标仍按 adapter 的本地校验失败处理。

## 当前三个 QQ ToolSpec

skill 的文字说明不注册、不执行也不扩大工具能力。工具可用性和参数校验始终以 Hermes
实际发现的 ToolSpec 为准：

1. `milky_profile_like`：`user_id` 必须是整数 `10001..4294967295`；可选 `count` 必须是
   整数 `0..9007199254740991`，不接受字符串伪装。
2. `milky_nudge`：`target` 必须是完整 `dm:<十进制QQ号>` 或 `group:<十进制群号>`。
   群目标必须另给 `user_id`，私聊目标可以给布尔 `is_self`，两种目标都不接受不适用的
   参数。
3. `milky_recall_group_message`：`target` 必须是 `group:<十进制群号>`，
   `message_seq` 必须是整数 `0..9007199254740991`。

这三个工具只调用各自绑定的已确认 Milky Action。工具清单之外的 Action、CQ fallback
语义、临时会话目标和缺失参数都不因本 skill 的文字描述而变得可用。

## 后续待办

- 在取得 Milky OpenAPI 和脱敏测试 fixture 证据后，再评估 `markdown`、`xml`、`mface`
  等类型是否存在 native 映射。
- 若某个 CQ 类型需要独立 Action，先新增独立 OpenSpec 契约、参数边界和 ToolSpec，再更新
  本矩阵；不要把 fallback 直接升级为执行能力。
- 继续保持 fixture、日志、异常和提示中的 ID、凭证、媒体地址与敏感正文脱敏。
