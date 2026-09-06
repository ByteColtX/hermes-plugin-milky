## Context

当前 `willingness.keywords` 在配置解析和 willingness 计算中只负责选择
`keywordMultiplier`；`directForce`、`mentionForce` 和 `quoteForce` 则负责跳过概率抽样。
`routing.keywords` 属于另一套 routing 配置，已经表示确定性触发。详见 proposal.md 和
本 change 的两份 delta spec。

`willingness` 已在通过 Gate 的普通消息上维护 per-chat score，并在 `trigger` 决策完成后
立即扣除一次 `replyCost`。本 change 只扩展决策条件和公开配置名称，不改变这些状态所有权
与扣费时点。

## Goals / Non-Goals

**Goals:**

- 让配置名称直接区分兴趣增益关键词和强制触发关键词。
- 让强制关键词在普通 friend/group 消息中提供可预测的 trigger，且不调用随机抽样。
- 保持兴趣关键词的既有增益倍率行为，并使两类关键词同时命中时语义可组合。
- 复用现有 Gate、WillInput、per-chat score 和 trigger reply cost 边界，不新增持久化状态。

**Non-Goals:**

- 不重命名或改变 `routing.keywords`。
- 不保留 `willingness.keywords` 的兼容别名或自动迁移。
- 不新增正则、词法分词、大小写折叠、关键词冷却、排除词或按场景配置。
- 不让强制关键词绕过 Gate、temp、命令、系统事件或普通消息的资源安全边界。

## Decisions

### 使用 `interestKeywords` 和 `forceKeywords` 作为公开键名

外部 JSON 使用 `interestKeywords` 和 `forceKeywords`，内部配置对应
`interest_keywords` 和 `force_keywords`。前者只选择 `keywordMultiplier`，后者只提供
force 条件；空数组或省略字段表示关闭对应行为。

采用这两个名称是为了把“兴趣”与“强制触发”直接写进 schema。继续使用通用的 `keywords`
会与 `routing.keywords` 及新增行为混淆；使用两个不同的兼容别名则会让同一份配置可能
产生两套来源，增加迁移和校验歧义，因此旧字段明确拒绝。

### 两类关键词都匹配规范化正文的直接子串

`interestKeywords` 和 `forceKeywords` 只消费现有 `WillInput` 的规范化正文，匹配规则为
任意配置项作为直接子串出现。配置项仍必须是非空字符串数组；空数组不产生命中。实现不得
重新读取 raw segment、媒体 URL、未知字段或敏感正文，也不引入网络 I/O。

这样保持现有兴趣关键词的匹配边界，并让 forced 行为可测试、可预测。正则、分词和隐式
大小写转换会改变命中契约，本 change 不采用这些替代方案。

### 强制关键词只改变决策，不改变普通分数公式

普通 `message_receive` 仍按现有消息属性计算 score；命中 `interestKeywords` 时使用
`keywordMultiplier`。`forceKeywords` 不额外提供 gain，也不替代兴趣关键词。若同一消息
同时命中两类关键词，score 使用兴趣关键词语义，最终 decision 由 force 命中直接得到
`trigger`。

强制关键词与现有 `directForce`、`mentionForce`、`quoteForce` 一样，只是绕过随机抽样的
额外条件；Gate 仍先于 Will，非普通消息仍返回 `wait`。这样不会复制 Gate 或系统事件的
决策入口。

### 复用现有 trigger 成本语义

强制关键词产生的 `trigger` 与概率抽样或既有 force 产生的 `trigger` 使用同一条 reply
cost 路径：通过 Gate 且完成 trigger 决策后扣一次 `replyCost`，后续 Hermes 或发送失败
不回滚。无需新增成本类型、pending 状态或交接确认。

## Risks / Trade-offs

- [旧配置无法继续启动] → 在配置校验中明确拒绝 `willingness.keywords`，并在 README 与
  迁移说明中给出 `interestKeywords` 替换方式。
- [直接子串可能产生误命中] → 保持当前确定性匹配边界，在规范和示例中明确不支持正则、
  分词或语义匹配；冷却和排除词留作后续独立 change。
- [强制关键词可能使消息更频繁进入 Agent] → 复用现有 per-chat admission 和 reply cost，
  不在本 change 中增加隐式限流，以免改变已确认的 trigger 语义。
- [routing 与 willingness 配置仍同时存在 `keywords` 类字段] → 文档明确限定
  `routing.keywords` 与 `willingness.interestKeywords` 的配置层级和行为，避免跨引擎
  迁移或静默合并。

## Migration Plan

1. 将部署配置中的 `willingness.keywords` 改为 `willingness.interestKeywords`；数值字段
   `keywordMultiplier` 保持不变。
2. 需要包含即触发时，在同一 `willingness` 对象新增 `forceKeywords`；不需要时省略或使用
   空数组。
3. 先通过启动配置校验和 willingness 回归测试，再启用新的策略配置。
4. 如需回滚实现，恢复上一版代码和配置；新字段不会被旧版本识别，回滚前须把
   `interestKeywords` 改回旧版本的 `keywords`，并移除 `forceKeywords`。

归档条件是实现、聚焦测试、完整质量门禁和 OpenSpec 严格校验均完成；实机未覆盖的协议
边界仍应保留在 evidence 中。
