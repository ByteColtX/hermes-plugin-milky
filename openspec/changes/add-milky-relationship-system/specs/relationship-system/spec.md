## Purpose

为 Milky 私聊用户和群聊成员提供按 Bot 身份隔离、可持久化且可审计的关系状态。该能力把长期亲近度、信任、短期情绪、未修复关系债务、用户活跃度和有限事件 flag 分开建模，使关系阶段和互动策略不依赖一个不可解释的固定加减分。

## ADDED Requirements

### Requirement: 关系主体必须按私聊用户和群成员隔离

系统 MUST 为每个关系使用包含 Bot `self_id` 的稳定主体键。friend 关系的主体键 MUST 是
`self_id + dm + user_id`；group 关系的主体键 MUST 是 `self_id + group_id + member_id`。
同一用户在不同 Bot、不同群或私聊与群聊之间 MUST 使用不同关系状态；群聊中一个成员的事件
不得读取、修改或推断另一个成员的状态。`temp` 会话和无法确认主体键的事件 MUST 不创建关系。

#### Scenario: 群聊成员状态互不影响

- **WHEN** 同一个群的成员 A 和成员 B 分别产生相同类型的正向事件
- **THEN** 系统 SHALL 分别更新 `group_id + A` 和 `group_id + B` 的关系状态
- **AND** 查询成员 A 的状态 SHALL 不包含成员 B 的 affection、trust、mood、resentment 或 activity

#### Scenario: 同一用户跨群隔离

- **WHEN** 用户 U 在群 G1 和群 G2 中分别产生事件
- **THEN** 系统 SHALL 使用两个不同的关系主体
- **AND** G1 的事件 SHALL NOT 改变 G2 的关系阶段、flags 或待处理 commitment

#### Scenario: Bot 身份隔离

- **WHEN** 两个 `self_id` 相同的关系目标收到同一用户事件
- **THEN** 系统 SHALL 将事件写入对应 `self_id` 的独立主体
- **AND** 更换 Bot 身份 SHALL NOT 复用原 Bot 的关系状态

### Requirement: 关系状态必须分离长期关系、短期情绪、关系债务和用户活跃度

每个关系主体 MUST 暴露下列有界状态：`affection`、`trust`、`mood`、`resentment`、
`activity_ema`、`stage` 和 `overlays`。`affection`、`trust`、`resentment` 和
`activity_ema` MUST 位于 `[0, 100]`；`mood` MUST 位于 `[-100, 100]`。初始主体的数值 MUST
为零，阶段为 `stranger`，且没有 overlay 或 flag。普通用户消息 MUST NOT 因为消息数量本身
直接增加长期 affection 或 trust。

#### Scenario: 新主体使用中性初始状态

- **WHEN** 首次查询一个合法 friend 或 group member 主体
- **THEN** 系统 SHALL 返回 affection、trust、mood、resentment、activity_ema 均为零
- **AND** SHALL 返回 `stage=stranger` 且没有负面 overlay

#### Scenario: 活跃度不等同于长期好感

- **WHEN** 用户在短时间内发送多条通过 Gate 的普通消息，但没有受支持的主观互动事件
- **THEN** 系统 SHALL 更新 activity_ema
- **AND** SHALL NOT 仅凭这些普通消息增加 affection 或 trust

#### Scenario: 短期情绪不改变历史亲近度

- **WHEN** 一个正向事件提高 mood 但没有达到长期维度的有效影响
- **THEN** 系统 SHALL 保留该主体原有 affection 和 trust
- **AND** 查询结果 SHALL 能区分 mood 的变化与长期阶段

### Requirement: 用户活跃度只统计经过入站门禁的用户行为

系统 MUST 只把经过 canonical、稳定去重和 Gate 的合法用户 `message_receive` 视为普通活跃度
样本，并且每个稳定 message ID 对对应关系主体最多计入一次。friend 消息的样本主体 MUST 是
发送用户；group 消息的样本主体 MUST 是发送成员。用户消息是否 wait 或 trigger 不得改变该
样本是否计入。经过现有系统事件 parser 验证、方向明确为用户戳向 Bot 的
`friend_nudge`/`group_nudge` 可以作为单独的用户行为样本，但不得触发普通 Agent turn。Bot
回复、Agent Tool 调用、scheduler tick、主动出站消息、其他系统事件、重复消息、Gate deny、
temp 消息和无法确认主体的消息 MUST NOT 增加 activity_ema。

#### Scenario: wait 消息仍计入一次用户活跃

- **WHEN** 一条合法用户消息通过 Gate 后被 Will 判定为 `wait`
- **THEN** 对应主体 SHALL 计入一次用户活跃度
- **AND** 该消息后续不因 trigger 或 Agent handoff 再次计入

#### Scenario: Bot 回复不增加用户活跃度

- **WHEN** Agent 发送一条 QQ 回复，或 scheduler 发送一条主动消息
- **THEN** 系统 SHALL NOT 为该消息的目标用户增加 activity_ema
- **AND** SHALL NOT 因该出站动作写入用户行为 event

#### Scenario: Gate deny 和重复消息不计入活跃度

- **WHEN** 用户消息被 allowlist/mute/self Gate 拒绝，或稳定 message ID 已在 TTL dedup 中出现
- **THEN** 系统 SHALL 不增加对应 activity_ema
- **AND** SHALL 不创建重复的 activity event

#### Scenario: 只统计明确戳向 Bot 的 nudge

- **WHEN** 合法的 `friend_nudge` 或 `group_nudge` 明确记录用户为 sender、Bot 为 receiver，且
  chat key 与主体字段可确认
- **THEN** 系统 SHALL 为该 sender 的对应关系主体计入一次 activity_ema
- **AND** SHALL 不创建普通 canonical、Will、reply cost 或 Agent turn
- **AND** sender 戳向其他用户、receiver 缺失或方向不明的 nudge SHALL NOT 计入活跃度

### Requirement: 活跃度必须时间衰减并对短时间重复行为递减

系统 MUST 使用半衰期为 36 小时的时间衰减计算 activity_ema：读取或写入时，先按
`value = value * 2^(-elapsed_hours / 36)` 衰减到当前时间。一次新的用户消息在同一主体最近
10 分钟内已有 `n` 条已计入消息时，增加量 MUST 为 `min(8, 8 / (1 + 0.5*n))`，更新后限制在
`[0, 100]`。因此首条消息贡献最大，刷屏的边际贡献递减；事件时间逆序或时钟异常时 MUST
使用不早于上次更新时间的时间计算，不得产生反向增长。

#### Scenario: 长时间不互动后活跃度衰减

- **WHEN** 主体上次活跃距当前 36 小时且没有新用户消息
- **THEN** 系统 SHALL 将 activity_ema 衰减到约为原值的一半
- **AND** SHALL 不改变 affection、trust 或 resentment

#### Scenario: 短时间重复消息边际递减

- **WHEN** 同一主体在十分钟窗口内连续发送三条合法消息
- **THEN** 第一条消息的活跃度增量 SHALL 大于第二条
- **AND** 第二条消息的增量 SHALL 大于第三条
- **AND** 三条消息 SHALL 仍只影响该主体的 activity_ema

#### Scenario: 时间戳异常不反向增加状态

- **WHEN** 新事件的 occurred_at 早于已持久化的 last_activity_at
- **THEN** 系统 SHALL 以 last_activity_at 作为衰减基准
- **AND** SHALL 不因异常时间戳额外增加 activity_ema 或回退其他状态

### Requirement: 长期关系变化必须来自固定事件目录和主观偏好

长期关系更新 MUST 通过固定 event code 进行，至少包括 `preference_match`、
`preference_mismatch`、`kindness`、`rudeness`、`boundary_respected`、
`boundary_violation`、`promise_kept`、`promise_broken`、`apology` 和 `repair_action`。
事件 MUST 经过来源、场景、严重程度和允许 taste tag 校验；调用方 MUST NOT 直接提交
affection、trust、mood 或 resentment 的任意数值 delta。Bot 的喜恶 MUST 由启动时加载的
有限偏好 profile 决定，至少能表达 liked、neutral 和 disliked；事件 code 不在 profile 中时
使用 neutral，不得从用户正文或昵称推断新的偏好规则。

#### Scenario: 固定事件产生可解释更新

- **WHEN** scheduler 或 Agent Tool 提交一个 schema 允许的 `kindness` 事件
- **THEN** 系统 SHALL 按该事件的固定 effect、来源权限、严重程度和偏好计算结果
- **AND** SHALL 返回应用后的维度变化与新阶段
- **AND** SHALL 不接受调用方附带的任意数值 delta

#### Scenario: 未知事件不改变关系

- **WHEN** 调用方提交未在事件目录中的 event code 或未允许的 taste tag
- **THEN** 系统 SHALL 返回 `unsupported_event`
- **AND** SHALL 不写入状态、事件账本、flags 或 commitment

#### Scenario: 普通正文不触发主观喜恶

- **WHEN** canonical 消息只包含普通文本，且没有可靠的结构化事件来源
- **THEN** 系统 SHALL 只执行活跃度观察
- **AND** SHALL 不使用 LLM 自由文本情感判断直接修改 affection、trust 或 resentment

### Requirement: 事件影响必须确定、递减、有来源上限并保持维度非对称

对相同主体、相同旧状态、相同 `event code`、severity、taste tag、source 和 occurred_at 的
事件，系统 MUST 产生相同的结果。事件影响 MUST 按固定顺序乘以 severity multiplier、Bot
preference multiplier、相同 event code+taste tag 在最近 7 天的 novelty multiplier、scene
modifier 和 source cap，并对每个维度应用每日上限。novelty multiplier MUST 使用
`max(0.2, 1 / (1 + 0.35*k))`，其中 `k` 是最近 7 天已经应用的同类事件数。正向 affection 和
trust 的增长上限 MUST 小于一次 critical 越界/失约对 trust 和 resentment 的负向影响；
agent_tool 来源 MUST 只能使用 `minor` 或 `normal` 严重程度，并且其长期维度有效影响不得
超过 scheduler 来源同类事件的 50%。

#### Scenario: 重复正向事件收益递减

- **WHEN** 同一主体在七天内重复提交相同 `event code + taste tag`
- **THEN** 后一次事件的 novelty multiplier SHALL 不大于前一次
- **AND** 关系系统 SHALL 在达到每日维度上限后停止该维度的继续增长

#### Scenario: 负面越界比普通正向互动更重

- **WHEN** 一个 `critical boundary_violation` 和一个 `normal kindness` 作用于相同旧状态
- **THEN** 越界事件对 trust/resentment 的绝对影响 SHALL 大于正向事件对 trust/affection 的影响
- **AND** mood、resentment 和长期 trust SHALL 仍分别记录，不得折叠成单一分数

#### Scenario: Agent Tool 不能绕过来源上限

- **WHEN** Agent Tool 反复提交同一主体的正向或负向事件
- **THEN** 每次事件 SHALL 受 agent_tool 的严重程度、来源系数、novelty 和每日上限约束
- **AND** Agent Tool SHALL 不能直接设置阶段、清空 resentment 或写入 milestone flag

### Requirement: 关系阶段必须由长期维度、门槛和 flag 共同决定

系统 MUST 使用 `relationship_index = 0.6 * affection + 0.4 * trust` 计算阶段候选，并按以下
晋级门槛选择最高满足项：`stranger` 为 `<15`，`acquaintance` 为 `15`，`familiar` 为
`35`，`close` 为 `55` 且 trust `>=40`，`trusted` 为 `70` 且 trust `>=60` 且 resentment
`<30`，`special` 为 `85` 且 trust `>=80`、resentment `<20` 且存在受信来源设置的
`bond_milestone` flag。阶段 MUST 有 5 分的降级滞回；负面 overlay 可以改变当前互动策略，
但不得偷偷抹除长期 affection/trust。`special` 不得仅靠刷消息或 Agent Tool 调用获得。

#### Scenario: 信任不足阻止亲近阶段晋级

- **WHEN** relationship_index 达到 close 的数值门槛但 trust 小于 40
- **THEN** 阶段 SHALL 保持在不高于 `familiar`
- **AND** 系统 SHALL 返回阻止晋级的可分类原因

#### Scenario: 特别阶段需要受信 milestone

- **WHEN** affection 和 trust 达到 special 数值门槛但没有 bond_milestone flag
- **THEN** 阶段 SHALL 保持在不高于 `trusted`
- **AND** 普通活跃消息和 Agent Tool SHALL 不能自行创建该 flag

#### Scenario: 负面状态覆盖但不抹除长期历史

- **WHEN** resentment 达到 `repair_required` 阈值而 affection 仍处于 close 范围
- **THEN** 查询 SHALL 同时返回原有阶段候选和 `repair_required` overlay
- **AND** 后续响应策略 SHALL 能以 overlay 为准降低亲密互动，但 SHALL NOT 将 affection 静默归零

### Requirement: 负面关系必须通过显式债务和受限修复处理

系统 MUST 将严重 `rudeness`、`boundary_violation`、`promise_broken` 和承诺逾期记录为
resentment 债务。普通沉默、没有 pending commitment 的长期不互动和 Bot 没有回复 MUST NOT
自动扣除 affection 或 trust。存在 pending commitment 时，只有经过 due 检查仍未有
`promise_kept` 或有效 `repair_action`，才可以创建一次 `neglect_debt`。当 resentment `>=20`
时 MUST 可出现 `wary`，当存在未修复重大事件或 resentment `>=50` 时 MUST 出现
`repair_required`；mood `<=-60` 且有近期负面事件时可出现 `cold`。overlay 的优先级 MUST
为 `repair_required`、`wary`、`cold`。

#### Scenario: 普通沉默不扣分

- **WHEN** 主体没有待履行承诺，且连续一段时间没有用户消息
- **THEN** 系统 SHALL 只衰减 activity_ema 和 mood（若 mood 非零）
- **AND** SHALL NOT 增加 resentment 或减少 affection/trust

#### Scenario: 逾期承诺产生一次关系债务

- **WHEN** 一个 pending commitment 超过 due_at，且尚未有 kept 或 repair 结果
- **THEN** 系统 SHALL 最多创建一次 `neglect_debt`
- **AND** SHALL 更新 resentment/overlay
- **AND** 同一 commitment 的重复 tick SHALL 返回 already_processed 且不重复扣分

#### Scenario: 修复逐步释放负面状态

- **WHEN** 用户或受信 scheduler 提交与未修复事件匹配的 `apology` 或 `repair_action`
- **THEN** 系统 SHALL 只按待修复债务的上限减少 resentment，并有限度恢复 trust/mood
- **AND** SHALL 保留修复前后的事件账本
- **AND** 没有对应债务时 SHALL 不允许调用方凭空清空 resentment

### Requirement: commitments 和 flags 必须是受限、可审计的关系事实

系统 MUST 将 pending commitment、bond_milestone 以及其他关系 flag 作为独立的结构化事实保存，
不得把它们编码在 affection 数字或任意 JSON 文本中。commitment MUST 有稳定 commitment_id、
due_at、主体键和状态；同一 commitment 只能从 pending 进入 kept、broken、repaired 或
expired 中的一条合法路径。`bond_milestone` 和其他晋级 flag MUST 只能由受信 scheduler
或明确的插件业务规则设置，Agent Tool 只能读取，不能设置、删除或改名。

#### Scenario: 同一承诺状态只前进一次

- **WHEN** scheduler 对同一 commitment_id 重复提交 `promise_kept`
- **THEN** 第一次提交 SHALL 进入 kept 并应用一次 effect
- **AND** 后续提交 SHALL 返回 duplicate/already_processed 且不再次改变关系

#### Scenario: Agent Tool 不能伪造 milestone

- **WHEN** Agent Tool 请求写入 `bond_milestone` 或把 commitment 直接标记为 repaired
- **THEN** 系统 SHALL 返回 `forbidden_source`
- **AND** SHALL 不改变任何关系维度或 flag

### Requirement: 所有关系写入必须具有事务性和幂等结果

系统 MUST 在一次原子操作中完成时间衰减、重复 event_id 检查、effect 计算、状态更新、
事件账本追加和必要 flag/commitment 更新。scheduler MUST 提供非空、稳定且在其域内唯一的
event_id；Agent Tool MUST 使用当前 Hermes session context 中的 `session_id + message_id +
operation` 形成幂等键，不得假设 handler 一定能取得 `tool_call_id`。同一幂等键重复调用 MUST
返回原始应用结果，不得重复计分。并发读写不得产生部分状态或丢失其他主体的更新。

#### Scenario: 重复事件只应用一次

- **WHEN** 同一 event_id 因网络重试被提交两次
- **THEN** 系统 SHALL 只写一条事件账本并只应用一次 effect
- **AND** 第二次调用 SHALL 返回 duplicate 及首次结果

#### Scenario: 并发更新保持完整

- **WHEN** scheduler 和 Agent Tool 同时更新同一主体
- **THEN** 系统 SHALL 串行提交两个完整事务或明确返回一个可重试的冲突结果
- **AND** SHALL 不产生半更新状态、负数越界或丢失任一已提交事件

#### Scenario: 持久化失败不伪造成功

- **WHEN** 关系数据库不可用、事务提交失败或 schema 版本不兼容
- **THEN** 写入方 SHALL 返回 `persistence_error` 或 `storage_unavailable`
- **AND** SHALL 不返回已应用的 delta、阶段变化或成功状态
- **AND** 入站消息 SHALL 按既有 pipeline 继续或完成其 Hermes 交接，不因关系旁路失败而回滚

### Requirement: 关系查询必须返回可解释的快照而非内部任意数据

关系查询 MUST 返回主体类型/范围、各维度当前值、阶段、overlay、最近衰减时间、可观察的
待修复摘要和安全的版本号；不得返回原始正文、凭证、媒体 URL、文件路径、数据库路径或
未授权主体的成员列表。查询时可懒惰应用 mood/activity 衰减，但查询不得产生主观事件、
增加 activity 或推进 commitment，除非调用方明确执行 due 检查操作。

#### Scenario: 查询当前主体快照

- **WHEN** Agent 在一个有合法 Milky session context 的私聊或群成员会话中调用查询
- **THEN** 系统 SHALL 返回当前会话发送者对应的关系快照
- **AND** SHALL 不查询同群其他成员或任意外部用户

#### Scenario: 缺少主体上下文时拒绝查询

- **WHEN** 查询缺少 `HERMES_SESSION_PLATFORM=milky`、合法 `HERMES_SESSION_CHAT_ID` 或
  group 场景的 `HERMES_SESSION_USER_ID`
- **THEN** 系统 SHALL 返回 `missing_session_context`
- **AND** SHALL 不创建默认关系或猜测目标

### Requirement: 关系记录必须遵守隐私和可观察性边界

事件账本 MUST 只保存结构化 event code、来源、严重程度、主体键、幂等键、时间、effect 摘要
和版本等必要字段；不得保存用户原始消息、Agent 完整 prompt/response、Authorization、
token、媒体 URL、文件路径或自由文本 evidence。日志 MUST 只记录安全分类、结果类型和必要的
业务 ID，不得输出敏感正文或完整数据库异常。

#### Scenario: 事件 evidence 不进入持久化

- **WHEN** Agent Tool 携带用于解释事件的自由文本 evidence
- **THEN** 系统 MAY 用其做本次调用的短暂诊断
- **AND** SHALL NOT 将该文本写入关系表、日志或错误响应

#### Scenario: 关系错误安全暴露

- **WHEN** 存储或参数校验失败
- **THEN** 调用方 SHALL 只收到稳定分类、字段名或安全 reason
- **AND** SHALL NOT 收到 token、路径、SQL、异常正文或其他关系主体的隐私数据
