# will-willingness Specification

## Purpose

借鉴 YesImBot 设计的状态和数值语义决定每个聊天何时愿意回复，保留完整嵌套配置、
可注入时钟与随机源，以及只有 Hermes trigger 提交成功才扣除回复成本的策略边界。

## Requirements

### Requirement: willingness 状态按 chat 独立维护

每个 chat MUST 独立维护 `score`、`lastMessageAt` 和 `lastDecayAt`，初始分数 SHALL 使用 `initialScore`；一个 chat 的消息、衰减或扣费 MUST NOT 改变另一个 chat 的状态。

#### Scenario: 两个 chat 互不影响

- **WHEN** group A 增加 willingness 分数
- **THEN** group B 和 dm C 的分数、时间戳 SHALL 保持各自状态

#### Scenario: 时钟回拨

- **WHEN** 当前时间早于某 chat 的 `lastDecayAt`
- **THEN** 该 chat 的 score SHALL 保持不变
- **AND** SHALL 不因负静默时间产生额外增益或衰减

### Requirement: willingness 使用完整静默衰减公式

willingness MUST 按 hot/warm 窗口权重计算 weighted silence，并在阈值以上先以阈值半速衰减、跨过阈值后按完整 half-life 衰减；结果 SHALL clamp 为不小于 0，低于 0.01 SHALL 归零。

#### Scenario: 热窗口与温窗口重叠

- **WHEN** 消息后的时间同时落在 hot 和 warm 窗口
- **THEN** weighted silence SHALL 分别乘以 `hotDecayWeight` 和 `warmDecayWeight` 后相加
- **AND** 衰减结果 SHALL 使用配置的 half-life 和 probability threshold

#### Scenario: 分数超过概率阈值

- **WHEN** score 高于正的 probability threshold 且静默时间跨过到达阈值所需时间
- **THEN** 系统 SHALL 先按阈值计算前半段衰减，再按完整 half-life 计算剩余部分

### Requirement: 消息增益和概率遵循本项目定义的参考语义

每次消息 SHALL 按 text、mention、quote、image、direct 的属性增益、关键词 multiplier、`max(0, 1-ratio²)` marginal gain 和分段 dynamic gain multiplier 更新 score；概率 SHALL 在阈值以下为 0，以上按 amplifier 计算并 clamp 到 0..1。

#### Scenario: 关键词命中

- **WHEN** 所有可用 content 按顺序拼接后包含关键词
- **THEN** 增益 SHALL 使用 `keywordMultiplier`
- **AND** 空关键词列表 SHALL 不命中

#### Scenario: ratio 位于中间分段

- **WHEN** score/maxScore 位于 0.2（含）到 0.8（不含）之间
- **THEN** dynamic gain multiplier SHALL 使用规范定义的抛物线公式

#### Scenario: 概率 clamp

- **WHEN** amplifier 计算出的概率小于 0 或大于 1
- **THEN** 对外抽样概率 SHALL 分别 clamp 为 0 或 1

### Requirement: force 顺序和提交 reply cost 不得改变

force 判断 MUST 按 directForce、mentionForce、quoteForce 顺序语义处理；任一满足即 trigger，否则才使用 `random < probability` 抽样。只有 Hermes `handle_message()` 正常返回、表明 trigger 已提交后，系统 SHALL 扣除一次 `replyCost`。

#### Scenario: direct force

- **WHEN** direct 消息且 `directForce` 为 true
- **THEN** Will SHALL 直接返回 trigger
- **AND** SHALL 不依赖随机抽样

#### Scenario: Gate deny 或 wait

- **WHEN** 消息被 Gate 拒绝或 Will 返回 wait
- **THEN** score SHALL 不执行成功 reply cost 扣除

#### Scenario: Hermes trigger 提交失败

- **WHEN** mapper 或 `handle_message()` 抛出异常
- **THEN** 系统 SHALL 保留未扣费状态
- **AND** SHALL 不伪装成已提交

### Requirement: poke 增益不混入普通消息属性

受支持的 poke 观察 SHALL 只使用 `pokeGain`、marginal gain 和 dynamic multiplier 参与 Will 概率，不得额外增加 text、mention 或 direct gain。

#### Scenario: poke 事件计算

- **WHEN** poke 事件进入 Will 观察
- **THEN** score SHALL 按 poke 专用增益更新并按概率抽样
- **AND** SHALL 不创建普通消息正文
