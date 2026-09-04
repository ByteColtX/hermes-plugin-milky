## Context

详见 `proposal.md` 的 Why。当前 Milky v1.3 `reply` segment 已解析出
`message_seq`、`sender_id` 和完整性状态；normalizer/canonical 已将首个可用 reply ID
作为 `quote_message_id`，并另外保存整体 `is_self_quote`。当前 renderer 只接收引用 ID，
因此无法在 header 中区分 Bot 引用和他人引用。当前消息和历史消息最终都经过同一套单行
header renderer，但 current/history 使用不同的安全视图。

## Goals / Non-Goals

**Goals:**

- 在 Agent-facing 的当前消息 `text` 和历史 `channel_context` 中，将已确认指向 Bot 的
  实际 header 引用目标显示为 `your_previous_msg`。
- 保留 header 中当前消息自己的真实 `msg_id`，以及 Hermes event 内真实的
  `reply_to_message_id`、reply author 和 `reply_to_is_own_message`。
- 以被 header 实际展示的 reply 目标为判断依据，覆盖 malformed、未知发送者和多 reply
  边界，避免整体聚合的 self-quote 信号误改其他目标。
- 保持普通他人引用、无引用、字段顺序、转义、历史/current 分离和现有资源/Will 行为不变。

**Non-Goals:**

- 不修改 Milky 协议解析、`reply` Action 查询、消息正文、canonical/dedup、Gate、Will 或
  出站发送参数。
- 不把 `your_previous_msg` 写入 Hermes 的真实 reply ID 字段，也不修改 Hermes core 或
  Gateway 的 reply prompt 注入逻辑。
- 不从 sender name、reply 正文、嵌套 mention、历史猜测或最近一次出站消息推导 Bot 身份。

## Decisions

### 1. 在展示边界替换 label，不改 canonical 身份

保留 `quote_message_id` 和 `ReplyReference.message_seq` 的真实数字值。renderer 的安全
消息视图额外携带“header 选中的 quote target 是否为当前 Bot”的布尔事实；当该事实为真
时只把 header 的展示值替换成固定字面量 `your_previous_msg`。Hermes mapper 继续使用
真实 `quote_message_id` 构造 `MessageEvent.reply_to_message_id`。

备选方案是直接把 canonical 的 `quote_message_id` 改成字符串 `your_previous_msg`，但
这样会破坏 Hermes reply metadata、真实消息定位和可能依赖数字 ID 的边界，因此不采用。

### 2. 只判断实际展示的第一个可用 reply 目标

当前 header 的 `reply_to` 来自第一个具有可用 `message_seq` 的 reply。自引用判断也只
读取同一个目标的 `sender_id`，并与当前消息的 `self_id` 比较。不能直接复用已有的
`is_self_quote`，因为它表示消息中是否存在任意自引用；在多个 reply 或前一个 malformed
reply 后，聚合值可能对应另一个未展示的目标。

发送者 ID 缺失、非法或无法与 `self_id` 确认相等时，保持真实数字 ID展示（若 ID存在），
不使用 `your_previous_msg`。这样延续未知能力 fail-closed，也不依赖 sender name。

### 3. current、history 共享判定规则但不共享上下文状态

current MessageEvent 的文本和 detached history 的 `_HistoryRecord` 都在构造 renderer
视图时提供同一项 quote-target ownership 信息。`DetachedTriggerBatch.current_text` 直接
渲染 current 时，canonical/normalized 消息自身也应能提供该事实；不能只在 pipeline 的
history 分支补字段，否则当前消息与历史消息会出现不一致。

context-only 系统事件不含 reply target，不添加该字段；无引用时保持现有 header，不伪造
`reply_to`。

### 4. 以契约测试锁定显示/内部双轨结果

测试同时断言：Bot 自引用的 Agent-facing `text`/`channel_context` 使用
`reply_to your_previous_msg`，而 fake Hermes 收到的 `reply_to_message_id` 仍为真实数字
字符串。另以他人引用、未知 sender、多个 reply、无引用和历史消息场景验证不误改。

## Risks / Trade-offs

- [聚合 `is_self_quote` 被错误用于展示会误改多个 reply 中的他人目标] → 只依据产生当前
  `quote_message_id` 的同一个 reply reference，并增加多 reply 回归测试。
- [真实 ID 被替换后下游无法定位引用消息] → 替换只发生在 Agent-facing header；保留
  canonical、ResolvedReply 和 `MessageEvent` 的真实 ID，并断言两条路径同时正确。
- [测试 fake message 没有完整 reply reference] → renderer 的视图字段提供显式安全默认值；
  协议路径必须由 typed reference 计算，不能读取 raw 或猜测。
- [协议端 reply.sender_id 缺失或 malformed] → 不使用自引用文案，保留可用数字 ID和既有
  malformed/安全诊断。

## Migration Plan

1. 在 renderer 使用的 current/history 安全视图中增加 quote target ownership 信息，并保持
   现有兼容字段和默认无引用行为。
2. 先增加脱敏 fixture/单元断言，再接入 current mapper 与历史 context 的集成断言。
3. 运行相关 inbound、context、pipeline 测试及项目要求的 Ruff、format、build 和 diff 检查。
4. 若回滚，移除展示 label 的替换并继续保留真实 ID；不涉及远端数据或配置迁移。

归档条件是实现、回归测试和质量门禁均通过，并在 evidence 中明确实机 Milky/Hermes 未
覆盖的边界；OpenSpec 归档或 validate 通过本身不代表真实环境认证。

## Open Questions

无。
