## Context

当前规范化层已经为 WillInput 提供独立的目标特征：`mention_kinds` 用 `self` 表示直接提及
当前 Bot，`is_self_quote` 表示至少一个 reply 明确指向当前 Bot，`is_self_poke` 表示
协议确认 Bot 为 poke 接收者；同时 `has_reply` 仍表示是否存在任意 reply。现有
willingness force 和 gain 判定却把 mention 的所有类型、任意 reply 和任意 poke 都纳入，
造成输入特征与目标语义不一致。相关目标识别已在 normalizer 边界内完成，design 不引入
网络查询、raw 重解析或新的协议字段。

## Goals / Non-Goals

**Goals:**

- 让 `mentionForce`、`quoteForce`、`mentionGain`、`quoteGain` 和 `pokeGain` 消费已确认的 Bot 目标特征。
- 保持 `directForce`、`mentionForce`、`quoteForce`、`forceKeywords` 的判断顺序和 trigger
  reply cost 时机不变。
- 让未知或非 Bot 目标安全地落入其他 force 条件或概率抽样路径，并且不产生对应目标增益。
- 用针对性测试同时锁定 Bot、非 Bot、未知目标、多 reply 和 self-poke 的结果。

**Non-Goals:**

- 不修改 normalizer 的 Milky 字段解析、`WillInput` 数据模型或 routing 规则；这些目标特征
  已存在且由现行 self-targeting 契约定义。
- 不改变 `textGain`、`imageGain`、`directGain`、关键词 multiplier、衰减、概率、reply cost
  或 routing 规则。
- 不改变 Gate、system event observe-only 边界、Hermes 交接、Milky Action 或出站行为。

## Decisions

### 1. 所有目标相关 force/gain 使用 self-target 特征

`mentionForce` 和 `mentionGain` 使用 `mention_kinds` 中的 `self` 信号；`all` 和 `here` 不属于
直接提及当前 Bot。`quoteForce` 和 `quoteGain` 使用 `is_self_quote`；普通 `has_reply` 只
说明存在 reply，不能代替目标确认。`pokeGain` 使用 `is_self_poke`，非 self 或未知 poke
只将该专用增益视为 0。规则依赖结构化目标信息，而不读取渲染后的正文、昵称或 raw。

备选方案是修改 `has_reply` 的含义，或在 willingness 内重新遍历 segments 判断目标。前者
会破坏已有上下文语义，后者会重复 normalizer 逻辑并绕过特征边界，因此不采用。

### 2. 保持 force 短路顺序和成本反馈边界

继续按 `directForce`、`mentionForce`、`quoteForce`、`forceKeywords` 的既有顺序判断；任一
命中即跳过随机抽样。未命中时保持原概率计算。trigger 决策完成后由现有流程负责一次性
扣除 `replyCost`，本 change 不把扣费移动到资源解析、Hermes 交接或 QQ 发送之后。

备选方案是把 force 统一改成同时评估后再排序，或让 `decide()` 自行处理交接和扣费。前者
会扩大本次行为变化，后者会违反 Will 与 Hermes 生命周期边界，因此不采用。

### 3. 用行为测试覆盖 force/gain 目标状态矩阵

更新 willingness 测试输入构造，使测试能分别表达 self mention、all/here/他人 mention、
self quote、他人 quote、未知 quote、多个 reply 中任一 self quote、self-poke 和非 self-poke。
测试 SHALL 同时验证 gain 只计算一次、未知目标不增加对应 gain；随机源在应当 force 的场景
中设置为不可调用，在不应 force 的场景中设置为稳定返回 wait 的值，以证明目标条件确实
控制了是否绕过抽样。

### 4. 同步事实来源

实现完成后同步 README 和 `openspec/specs/will-willingness/spec.md`：说明三个目标增益和
对应 force 只消费明确指向 Bot 的结构化特征，同时保留 `has_reply` 的独立存在性语义。主
spec 的 delta 由本 change 提供，归档时覆盖现行 requirement。

## Risks / Trade-offs

- [部分 reply 只有序号没有发送者 ID] → 保留 `has_reply` 作为上下文事实，但将
  `is_self_quote` 视为 false/unknown，不产生 `quoteGain` 或 `quoteForce`。
- [现有调用方可能把 all/here 当成 mention force] → 这是本 change 明确收紧的可观察行为，
  用非 Bot mention 回归测试固定，避免恢复宽泛兼容。
- [收紧目标增益可能降低部分消息的 score 和 trigger 率] → 保留 text/image/direct 等非目标
  增益及原概率公式，并用分离的目标矩阵测试固定降级边界。

## Migration Plan

1. 先更新 willingness force/gain 单元测试和必要的测试输入构造，覆盖目标状态矩阵。
2. 将 force/gain 判定改为只读取现有 self mention/self quote/self poke 特征，并保持既有 force
   顺序和 poke 观察边界。
3. 同步 README 与主 willingness spec，确认文档不再把任意 mention、reply 或 poke 描述为
   对应目标 gain。
4. 运行聚焦测试，再运行完整 pytest、Ruff、format、build、diff 检查和 OpenSpec strict 校验。
5. 如需回滚，只恢复 force 条件和对应文档/测试；不涉及配置迁移、远端状态或数据迁移。

## Open Questions

无。现有 `WillInput` 已提供本 change 所需的 self mention、self quote 和 self poke 特征，
未知目标的处理方式由 delta spec 固定为不触发对应 force 或 gain。
