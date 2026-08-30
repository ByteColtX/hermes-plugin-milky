## Context

See `proposal.md` for the motivation. 当前插件已经能把出站普通文本和显式结构化 segment
转换为 Milky Action 请求，但 `format_message()` 对字符串只生成一个 text segment，且
Hermes 的普通回复路径会把当前入站消息 ID 作为隐式 `reply_to` 传入。结果是模型无法可靠
控制是否引用，模型也不能用文本表达 Milky mention。

NapCat 的消息格式文档列出了 text、face、image、record、video、at、rps、dice、shake、poke、
share、contact、location、music、reply、forward、node、json、mface、file、markdown 和
lightapp 等 CQ 类型，并额外列出 anonymous、redbag、gift、cardimage、tts、xml 等扩展。
本变更要求 parser 识别这些类型；识别不代表每个类型都具有已确认的 Milky 原生 segment。

当前 `channel_context` 和 `MessageEvent.text` 已经使用稳定的消息头格式提供 sender `uid`
和 message `msg_id`。这些值是逐轮变化的，不能放入会被缓存的平台 system prompt；
`platform_hint` 只适合承载稳定的语法和安全规则。

Hermes 支持插件通过 `ctx.register_skill()` 提供命名空间隔离的只读 bundled skill。仓库中
现有 `.agents/skills/` 是 Codex/OpenSpec 工作流目录，不应与 Hermes Agent 的插件 skill
混用。

## Goals / Non-Goals

**Goals:**

- 让模型独立选择普通文本、@、引用或 @ 与引用的组合。
- 使用 CQ-compatible 文本作为 Agent-facing 语法，并逐项尝试转换成 Milky 原生 segment；
  不可转换或转换失败的 CQ 片段原样形成 text segment。
- 在平台提示中提供最小的稳定语法说明，在 bundled skill 中承载完整 CQ 类型矩阵、映射状态
  和 QQ 参考资料。
- 取消普通 Agent 回复的隐式当前消息引用，避免未被模型选择的 reply segment。
- 保留真实 ID 来源、缺失 ID、非法目标和原样 fallback 的安全语义；CQ 本身的未知或转换
  失败不阻止整条消息发送。

**Non-Goals:**

- 不实现 OneBot v11 传输协议、CQ 码入站协议、OneBot Action、echo、WebSocket RPC 或任意
  Action catalog。
- 识别全部文档 CQ 类型不等于为每一种类型发明 Milky 原生能力；Milky 没有确认等价 segment
  的类型、显式 file message segment 以及需要额外 Action 的能力，必须使用原始 text fallback。
- 不把实际 uid、msg_id、正文、媒体 URL 或凭证写入 `platform_hint` 或 skill 文件。
- 不修改 `channel_context` 的历史记录格式，不创建插件侧 Agent 队列，也不改变 Hermes 的
  busy/follow-up/interrupt 归属。

## Decisions

### 1. 将 CQ 码限定为 Agent-facing compatibility syntax，并建立完整类型 registry

本变更只在 Hermes Agent 输出文本与 Milky formatter 之间增加一个窄接口：

```text
Agent text
  -> CQ-compatible parser
  -> Milky outgoing segments
  -> send_group_message / send_private_message
```

解析器采用通用 CQ 形态 `[CQ:<name>,<key>=<value>,...]`，由 registry 按 name 选择转换器。
registry 至少覆盖 NapCat 文档中的 `text`、`face`、`image`、`record`、`video`、`at`、`rps`、
`dice`、`shake`、`poke`、`share`、`contact`、`location`、`music`、`reply`、`forward`、
`node`、`json`、`mface`、`file`、`markdown`、`lightapp`、`anonymous`、`redbag`、`gift`、
`cardimage`、`tts` 和 `xml`。每个转换器成功时生成已确认的 Milky outgoing segment；没有
确认映射、字段不完整或转换器失败时，转换结果是一个包含原始 CQ 字符串的 text segment。

`[CQ:at,qq=<uid>]` 成功时映射为 Milky `mention` segment，`qq=all` 若没有另行确认的
转换契约也按原始 text fallback；`[CQ:reply,id=<msg_id>]` 成功时映射为 Milky `reply`
segment。CQ 码不会直接进入 Milky HTTP body，也不会使插件拥有 OneBot 协议兼容能力。这样
可以借用 QQ Agent 已熟悉的表达方式，同时继续以 Milky v1.3 OpenAPI 作为网络协议唯一依据。

转换按单个 CQ 片段原子进行：一个片段失败只能回退该片段，不能丢失或改写其他文本和 CQ
片段。未知 name 同样保留完整原文，保证未知协议扩展向前兼容且不会假装执行。

备选方案是继续使用 XML-like `<at>`/`<quote>` 标签，或新增独立 Agent 工具参数。前者与
用户指定的 QQ/CQ 习惯不一致，后者无法覆盖 Hermes 自动交付的普通最终文本，因此采用
CQ-compatible 文本语法。

### 2. 只在 `platform_hint` 放稳定的基础规则

注册入口的 `platform_hint` 使用以下固定文案：

```text
你正在通过 Hermes 的 Milky QQ 平台通信。

发送消息时，默认不要自动 @ 用户，也不要自动引用当前消息。只有确实需要时，使用以下 CQ 码：
[CQ:at,qq=<uid>]：@指定用户。uid 必须取自当前消息或 channel_context 消息头中的 uid。
[CQ:reply,id=<msg_id>]：引用指定消息。msg_id 必须取自当前消息或 channel_context 消息头中的 msg_id。
同时 @ 和引用时，将两个 CQ 码连续放在正文前，例如：[CQ:reply,id=9001][CQ:at,qq=101]你好 Alice。
不要从昵称、正文或记忆猜测 uid/msg_id；没有对应真实字段时不要生成该 CQ 码。
需要完整 CQ 码或 QQ 工具说明时，可按需加载插件 skill `hermes-plugin-milky:qq-reference`。
```

平台提示是静态 system-prompt 层，不能包含本轮真实 ID。当前消息和历史消息仍分别通过
`MessageEvent.text` 与 `channel_context` 提供真实消息头；模型复制这些值即可生成控制码。

备选方案是将完整 CQ 表格放入每个 `channel_context`，但这会重复污染历史数据、增加每轮
上下文长度，并混淆“消息事实”和“系统规则”，因此不采用。

### 3. 采用通用 CQ 语法和原样 fallback

解析器接受通用 CQ 形态，并对文档中的全部类型进行识别：

```text
[CQ:<name>,<key>=<value>,...]
```

解析时保留控制码前后的普通文本和控制码出现顺序；同一条消息可以包含任意数量的 CQ
片段。对需要数值的字段，转换器复用既有 outbound ID 边界；转换失败时不得改写原始
字符串。当前代码中的 `101` 仅作为合成示例；真实转换成功仍必须使用 Milky 提供的合法
QQ ID。

未知 name、malformed 参数、字段缺失和转换器异常均返回原始 text segment；它们不产生
CQ 专用错误，不静默删除，不伪造其他 segment，也不要求额外 HTTP Action。对于普通文本中
出现的 CQ-like 内容，若 parser 无法安全确认边界，也必须保留对应原文。

备选方案是对未知 CQ 码返回 `unsupported`。该方案会丢失用户希望原样发送的协议扩展，
因此本变更采用逐片段 text fallback；skill 必须明确 fallback 文本不代表 CQ 语义已执行。

### 4. 在适配器出站边界忽略隐式 reply anchor

Hermes 仍可把当前事件的 message ID 作为通用 `reply_to` 参数传给平台适配器，但 Milky
adapter 的普通 Agent 回复路径不把它转成 reply segment。只有解析后的显式
`[CQ:reply,id=...]` 能产生引用；显式引用的目标只使用模型指定的 ID，不与隐式 anchor
合并。

这项处理必须发生在 adapter 的一次性发送边界，保持既有“不调用宿主通用 retry/fallback”的
契约。文本发送、显式媒体 sender 和未来结构化输入都不能再隐式添加当前消息引用。

备选方案是让 formatter 同时接收隐式 `reply_to` 并尝试去重，但这样仍由插件内部决定
引用，并且无法区分模型选择与宿主默认行为，因此不采用。

### 5. bundled skill 使用插件命名空间和只读文件

新增：

```text
skills/
└── qq-reference/
    └── SKILL.md
```

根入口在注册阶段检查该文件并调用 `ctx.register_skill("qq-reference", path)`。Hermes
自动派生插件命名空间，Agent 按需通过 `skill_view("hermes-plugin-milky:qq-reference")`
加载；文件保持插件只读，不复制到 `~/.hermes/skills/`，也不放入当前 `.agents/skills/`
工作流目录。

模板包含四块：基础 CQ 码、Milky segment 映射、当前三个 QQ ToolSpec 的使用边界、未来
扩展待办。skill 的文字说明不能替代真实 ToolSpec；只有实际注册且通过参数/目标校验的
工具才可执行。

### 6. 用契约和 fake transport 验证，不依赖真实写入

测试分为四组：

1. 平台提示包含稳定文案且不含逐轮 ID、凭证或正文。
2. formatter 覆盖文档 CQ 类型矩阵；可转换类型生成准确 Milky segments，未知、malformed
   和转换失败片段原样生成 text segment。
3. adapter 在 Hermes 提供隐式 anchor 时仍只发送模型显式选择的 segment，且只调用一次
   send 边界。
4. 插件入口登记 `qq-reference` skill，不联网、不创建后台任务，不改写用户全局 skill；
   skill 内容包含完整类型矩阵、当前 native/fallback 状态和真实工具边界。

Milky 写入 Action 的真实 smoke 不属于本次设计必需证据；fake client 足以验证请求 body
形状，后续若执行 live smoke 必须使用运行时凭证和明确授权。

## Risks / Trade-offs

- [去除默认引用后，部分用户可能习惯每条回复都显示为引用] → 在 `platform_hint` 明确
  默认行为，并由模型在确有必要时输出 reply CQ 码。
- [模型可能复制错误或过期的 ID] → 只接受消息头中可见的真实值；出站严格校验，无法确认时
  不生成或本地拒绝，不通过昵称查找 ID。
- [CQ-compatible 术语可能被误解为 OneBot 支持] → 在 platform hint、skill 和架构文档中
  明确它只是 Agent-facing compatibility syntax，Milky wire protocol 仍只使用 native
  segments。
- [未知或转换失败的 CQ 码会以原文显示而不是执行语义] → 这是明确的兼容性 fallback；在
  skill 中区分 native conversion 与 text fallback，避免 Agent 将原文发送误解为操作成功。
- [某些 CQ 码的字段含义与 Milky schema 不一致] → converter 只使用已确认的字段映射，
  其余类型保留完整原文，不根据 OneBot 字段猜测 Milky Action。
- [插件 skill 默认按需加载，模型可能不知道何时加载] → platform hint 只提供 skill 的
  命名空间入口；skill 仍不进入每轮系统 prompt，避免扩大基础 prompt。
- [当前架构非目标段落明确写有不复制 CQ 码] → 实现时更新架构边界，注明本变更的
  Agent-facing 兼容语法例外，不改变 Milky/OneBot 协议边界。

## Migration Plan

1. 先实现并测试 `platform_hint`、通用 CQ parser/registry、逐片段原样 fallback、隐式 reply
   anchor 忽略和 bundled skill 注册；在此期间保持现有 native structured segment 输入可用。
2. 发布后，普通 Agent 回复从“默认可能引用”切换为“默认不引用”；需要引用的模型输出改用
   `[CQ:reply,id=...]`，需要 @ 的输出改用 `[CQ:at,qq=...]`。
3. 观察本地 request body；只在确认某个 CQ 码的 Milky segment、参数边界和测试证据后，才
   将该类型标记为 native conversion，否则保持原文 fallback。
4. 回滚时恢复旧的发送策略和 platform hint；但不得通过宿主通用 retry 重新发送已经进入
   网络边界的消息。

## Open Questions

无。各 CQ 类型的具体 native 映射仍必须以 Milky OpenAPI 和测试 fixture 确认为依据；无法
确认的类型按本设计的 text fallback 处理。
