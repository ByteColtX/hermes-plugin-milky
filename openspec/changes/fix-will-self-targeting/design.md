## Context

当前 `message_receive` 规范化已经能按 `self_id` 识别 self mention，但 reply 只向 Will 暴露
“存在引用”和引用序号，`routing.quote` 因此无法区分 Bot 的消息与其他用户的消息。nudge
事件则保留在系统事件观察路径，现有 Will 输入没有一个可复用的 self-poke 目标特征。详见
`proposal.md` 的 Why；三个 delta spec 固定了目标未知时的保守行为。

本设计必须保持以下边界：normalizer 和目标分类器不执行网络 I/O；Gate 仍先于 Will；系统
nudge 不变成普通 `message_receive`、Hermes turn 或隐式授权；正文、显示名称、动作图片 URL
和未知 raw 扩展不参与 Bot 身份推断；现有 routing 的 OR 合并、关键词和 `allMessage` 语义不变。

## Goals / Non-Goals

**Goals:**

- 在同一组规范化特征中独立表达 self mention、self quote 和 self-poke，避免把“有该类型信号”
  与“信号指向 Bot”混为一谈。
- 让 routing 只使用已确认的 Bot 目标：mention 比较 `user_id`，quote 比较 `reply.data.sender_id`，group
  nudge 比较接收者，friend nudge 使用协议自身接收方向字段。
- 对缺失、非法或不一致的目标保持 false/unknown，不以名称、正文、展示文本或网络补全替代。
- 用合成 fixture 锁定单信号、组合信号、非目标信号和系统事件 observe-only 行为。

**Non-Goals:**

- 不增加或重命名 `routing` 配置字段，不改变 `wait`、`trigger`、关键词、`direct`、
  `mentionAll` 或 `allMessage` 的既有规则。
- 不改变 willingness 的独立数值公式、增益或 force 配置；本 change 只修复 routing 及其
  所需的目标特征契约。
- 不把非 Bot nudge 丢弃出观察/既有上下文路径，也不因为 self-poke 命中而直接创建普通
  MessageEvent、Agent turn 或回复发送。
- 不查询 reply 原文、群成员或其他远端数据来确认目标，不改变 Milky Action、SSE、媒体和
  出站边界。

## Decisions

### 1. 为 reply 增加独立的 self-target 特征

提取 reply 时继续保留 `has_reply`、目标序号和原始 reply 引用，同时计算独立的 self-quote
特征。遍历 `message.segments` 中的 `reply` segment，只有该 segment 的
`reply.data.sender_id == self_id` 时，消息才拥有 self-quote；当前消息的
`message.sender_id` 只是引用者，不参与判断。引用他人或 `reply.data.sender_id` 未知时
self-quote 为 false，但不抹掉 reply 存在性。多个 reply 按输入顺序检查，任一已确认指向
Bot 的 reply 即可命中；`reply.data.segments` 中的 mention 只属于被引用内容，不参与判断；
不通过 `get_message` 或嵌套正文补全作者。

备选方案是让 routing 直接读取 reply raw 或把所有 reply 都视为 Bot 相关。前者绕过规范化
边界并增加敏感字段风险，后者正是当前误触发来源，因此不采用。

### 2. 保持 mention 的 self/all 分离并禁止名称推断

沿用现有 `mention.user_id == self_id` 的 self 判断；`mention_all` 仍只产生 all 信号，
其他用户的 mention 只保留 segment 和展示内容，不产生 self 信号。routing 只读取结构化
mention 特征，不读取 `name` 或渲染后的 `@文本`。

备选方案是根据 mention 名称匹配 Bot 昵称。昵称可变且属于不稳定业务文本，会造成误命中，
因此不采用。

### 3. 用协议方向字段形成 self-poke

group nudge 只有 `receiver_id` 与事件 `self_id` 一致时标记为 self-poke。friend nudge
只有 `is_self_receive` 明确为 true 且没有 `is_self_send == true` 的冲突时标记为 self-poke。
字段缺失、类型错误、目标不是 Bot 或方向冲突均保持未知/非命中；`display_action`、
`display_suffix`、图片 URL 和其他未确认字段不参与判断。

备选方案是把 friend nudge 的 `user_id` 或群 nudge 的 `sender_id` 默认当作 Bot 目标，或
仅按事件类型命中。两者都无法区分 Bot 被戳与 Bot 戳人，会把观察事件扩大为触发信号，因此
不采用。

### 4. 在 routing 层使用目标特征，保留事件边界

routing 继续对普通消息执行所有适用规则的 OR 合并，但 quote 条件改用 self-quote，mention
条件继续使用 self mention。对于明确携带 self-poke 特征的 Will 观察，poke 条件才可命中；
没有该特征时不把事件类型本身当作 poke 命中。系统事件处理仍保持 observe-only；如果当前
宿主没有可确认的 Will 观察交接点，self-poke 只保留为安全观察特征，不新增隐式 Agent 路径。

备选方案是让 pipeline 为每个 nudge 建立普通消息或绕过 Gate 直接调用 Hermes。这会改变
系统事件和普通消息的生命周期边界，也违反当前架构基线，因此不采用。

### 5. 以脱敏 fixture 和纯函数回归固定边界

fixture 覆盖 Bot self mention、他人 mention、`mention_all`、引用 Bot、引用他人、
`reply.data.sender_id` 缺失、group/friend self-poke、poke 他人、方向缺失/冲突及多个信号合并。测试同时断言
routing 不联网、不读文件、不使用正文名称推断，并确认非目标系统事件仍不创建 Hermes turn。

## Risks / Trade-offs

- [部分 Milky reply 事件可能只提供目标序号而没有作者] → 只保留 reply 存在性，
  `reply.data.sender_id` 缺失时 self-quote 保持 unknown/false，宁可不触发也不猜测目标。
- [不同 Milky nudge 场景提供的方向字段不完全一致] → group 使用已确认的接收者 ID，friend
  使用明确的自身接收字段；未覆盖的字段形状返回 observe-only/unsupported，并等待协议
  fixture 或实机证据，不补默认语义。
- [增加 self-poke 特征但系统事件仍不创建 Agent turn，调用方可能误解 `trigger`] → 在
  routing 与 system-events spec、测试和文档中同时声明：poke 命中只表示 Will 信号命中，
  不改变 nudge 的 observe-only 生命周期。
- [共享 `WillInput` 特征可能被 willingness 误用] → 明确不改 willingness 计算；实现测试
  保证新目标字段只影响 routing 命中，既有 willingness 公式保持原有输入契约。
- [旧测试把“任意 reply/poke”视为命中] → 先更新脱敏 fixture 和断言，再运行完整回归；不
  通过兼容别名恢复宽泛语义。

## Migration Plan

1. 先补充消息、nudge 和 routing 的合成 fixture，锁定 self/other/unknown 三类目标状态以及
   组合 OR 结果。
2. 扩展规范化结果和 Will 输入的目标特征，保持 reply ID、mention kind、正文、raw 和既有
   system context 不变。
3. 调整 routing 的 quote、mention 和 poke 命中判定，并验证普通 pipeline 的 Gate、buffer、
   Will、Hermes 提交顺序没有变化。
4. 更新 `ARCHITECTURE.md`、`README.md` 和测试证据，明确 routing 信号是 Bot 自身目标语义，
   同时保留系统 nudge 的 observe-only 边界。
5. 运行聚焦测试、fake Hermes 集成、Ruff、format、build、diff 和 OpenSpec strict 校验；真实
   Milky nudge 或消息 smoke 只有在用户明确授权且拥有脱敏运行环境时执行。
6. 回滚时移除新增目标特征和对应 routing 条件即可；没有远端状态、本地持久化或配置迁移。

## Open Questions

无。group/friend self-poke 的协议字段、未知目标的 fail-closed 行为、reply 多目标的任一命中
规则和系统事件边界已在 delta specs 中固定；若实机协议出现不同字段形状，应另立兼容 change。
