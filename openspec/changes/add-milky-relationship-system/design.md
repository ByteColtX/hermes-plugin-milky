## Context

当前 Milky 插件的普通入站顺序已经固定为 canonical、TTL dedup、per-chat admission、Gate、
buffer/Will 和 Hermes detached handoff；同一 chat 的入站事件按 sequence 串行。插件目前没有
关系状态或关系事件账本。

Hermes 已提供两种不同的插件持久化能力：`ctx.state` 是带跨线程/跨进程锁和单插件 10 MiB
配额的原子 JSON KV，适合少量配置；`plugins.plugin_storage.plugin_db()` 提供位于独立
`plugin-data/<plugin-name>/` 下的 SQLite/WAL 数据库，调用方负责连接和事务。关系系统需要
状态、事件账本、计数器、flags 和 commitments 的原子更新，因此选择后者，不进入 Hermes
core 的 `SessionDB.state_meta`。

Hermes Tool handler 可以通过 `gateway.session_context.get_session_env()` 读取
`HERMES_SESSION_PLATFORM`、`HERMES_SESSION_CHAT_ID`、`HERMES_SESSION_USER_ID`、
`HERMES_SESSION_MESSAGE_ID` 和 `HERMES_SESSION_ID`。当前 `model_tools.handle_function_call()`
虽然可接收 `task_id`、`session_id` 和可选 `tool_call_id`，但插件 handler 不能把
`tool_call_id` 视为一定可得的幂等输入；关系 Tool 使用 session context 的稳定字段，并要求
scheduler 显式提供自己的 event ID。

本设计吸收了 Galgame 中可迁移的机制，而不复制任何一部作品的数值：Tokimeki Memorial
Girl's Side 的六段关系和 Bomb/道歉修复映射为阶段、pending commitment 和 resentment；
Persona 5 的 Rank、选择偏好、时间机会成本和能力解锁映射为固定事件目录、主观偏好、重复
递减和 milestone flag；LovePlus 的 Feeling Gauge 与低落状态映射为 mood/activity 的时间
衰减；CLANNAD 的路线条件和 Light Orb 映射为独立的 flags，而不是把所有关系压成一个分数。
参考资料：

- [Tokimeki Memorial Girl’s Side General Game Guide](https://tokimemogirlsside.fandom.com/wiki/General_Game_Guide_%26_Tips)
- [Persona 5 Royal Confidant Guide](https://www.rpgsite.net/feature/5479-persona-5-royal-confidant-guide-conversation-answers-romance-options-gifts-skill-unlocks)
- [LovePlus Friend Mode](https://love-plus.fandom.com/wiki/Friend_Mode)
- [CLANNAD Walkthrough](https://strategywiki.org/wiki/CLANNAD/Walkthrough)

## Goals / Non-Goals

**Goals:**

- 建立 `self_id + scene scope + subject_id` 的稳定关系主体，确保群聊以成员为维度。
- 让长期 affection/trust、短期 mood、关系债务 resentment、用户 activity 和 flags 各自有
  清晰生命周期和来源。
- 用固定事件目录、主观偏好、事件新鲜度、来源权重、场景修正、频率上限和事务幂等替代
  固定 `+3/-5`。
- 同时支持入站用户行为观察、插件 scheduler 受信事件和 Agent Tool 受限事件。
- 在不修改 Hermes core、Agent 队列、Will 规则和 Milky 协议的情况下接入持久化与工具。

**Non-Goals:**

- 不由关系系统决定是否发言；Will 仍是回应概率/时机决策，关系状态只作为后续策略输入。
- 不从普通正文做自由文本情感分析，不把每条消息、Bot 回复、scheduler tick 或工具调用
  自动换算成 affection。
- 不让 Agent Tool 查询或操作任意 QQ 用户、群成员、Bot 身份、milestone 或任意分数。
- 不为入站媒体建立第二套下载、缓存、SSRF 或权限系统。
- 不回填历史消息、猜测断线期间事件、跨 Bot 合并关系，也不实现作品级剧情、语音或 UI。

## Decisions

### 1. 关系主体和状态模型

关系服务以不可变 `RelationshipTarget` 表达目标：

```text
friend: scene=friend, scope_id=null, subject_id=user_id
group:  scene=group,  scope_id=group_id, subject_id=member_id
```

`self_id` 由 adapter 的已确认登录身份绑定到服务实例，不从请求参数覆盖。关系状态至少
包含：

| 字段 | 范围/语义 | 生命周期 |
| --- | --- | --- |
| `affection` | 0..100，长期亲近程度 | 只由受支持事件改变，不被普通沉默衰减 |
| `trust` | 0..100，可靠性与安全感 | 正向增长慢，失约/越界负向更重 |
| `mood` | -100..100，短期感受 | 12 小时半衰期，受近期事件影响 |
| `resentment` | 0..100，未修复关系债务 | 不因普通时间自动清零，只被匹配修复降低 |
| `activity_ema` | 0..100，用户近期行为活跃度 | 36 小时半衰期，消息窗口内递减 |
| `stage` | 六段长期阶段 | 由 index、trust、resentment、flag 和滞回计算 |
| `overlays` | `repair_required`/`wary`/`cold` | 覆盖当下互动策略，不抹除长期历史 |

不保存“好感度总分”作为唯一真相；`relationship_index = 0.6 * affection + 0.4 * trust`
只作为阶段候选值。默认阶段、晋级门槛和 special 资格与关系 spec 保持一致，`stage` 作为
缓存字段保存以便查询和审计，但每次状态变更后都重新计算。

普通群消息的主体一定是发送者，不是群本身。群元数据可以作为事件的 `scope_id`，但不得
有一个共享的“群好感度”影响成员关系。

### 2. 活跃度只观察用户行为，且不产生自动长期好感

普通消息接入点放在 canonical、dedup 和三个 Gate 通过后、命令/Will 分流前。这样 wait 消息
可以统计一次，trigger 不会重复统计，Gate deny 不会污染状态。系统事件仍保持 observe-only；
其中经过现有 parser 验证、明确由用户戳向 Bot 的 `friend_nudge`/`group_nudge` 可作为一次
用户活跃样本，但不创建 Agent turn、Will、reply cost 或主观长期 event。其他 nudge 方向、
recall、成员变动和未知事件不计入 activity。

每次行为的算法为：

```text
decayed = previous * 2 ** (-max(0, now - last_activity_at).hours / 36)
burst_n = counted_user_events(target, now - 10 minutes, now)
impulse = min(8, 8 / (1 + 0.5 * burst_n))
activity_ema = clamp(decayed + impulse, 0, 100)
```

`last_activity_at` 之后的逆序时间使用 last 值而不是产生负衰减。查询和写入都可以懒惰计算
衰减，但只有经过门禁的用户行为才能产生 impulse。activity 允许反映持续聊天，但不把它
转化为 affection/trust；Agent 需要一个主观判断时必须提交固定事件。

### 3. 事件目录和主观偏好采用“类型 + profile”，不接受任意 delta

事件注册表是代码内的有限目录，策略文件只调整有限 taste tag 的喜欢程度，不增加新事件
语义。默认 normal severity 的 effect 基线如下；实现中使用 Decimal 或等价的确定性数值
运算，并在每次写入后 clamp：

| event code | affection | trust | mood | resentment | 说明 |
| --- | ---: | ---: | ---: | ---: | --- |
| `preference_match` | +3 | +1 | +6 | 0 | 用户行为符合 Bot 的 liked taste tag |
| `preference_mismatch` | -2 | -1 | -5 | +2 | 明确不符合或反复触碰不喜欢的行为 |
| `kindness` | +2 | +2 | +4 | 0 | 有可靠来源的善意行为 |
| `rudeness` | -3 | -4 | -10 | +6 | 一般失礼，不等同于 critical 越界 |
| `boundary_respected` | +1 | +4 | +3 | -1 | 经过确认的边界尊重 |
| `boundary_violation` | -4 | -8 | -18 | +12 | 触碰明确边界 |
| `promise_kept` | +2 | +7 | +5 | -1 | 已登记 commitment 的履行 |
| `promise_broken` | -4 | -12 | -16 | +18 | commitment 失约 |
| `apology` | +1 | +2 | +8 | -6 | 只匹配已有债务，不是清零按钮 |
| `repair_action` | +1 | +3 | +10 | -8 | 有实际补救结果的修复 |

severity multiplier 固定为 `minor=0.5`、`normal=1.0`、`major=1.5`、`critical=2.0`。
事件效果计算顺序为：

```text
raw = base_effect
    * severity_multiplier
    * preference_multiplier
    * novelty_multiplier
    * scene_modifier
    * source_multiplier
applied = apply_dimension_daily_cap(round_half_even(raw))
```

其中：

- preference profile 为 `liked=+1`、`neutral=0`、`disliked=-1`。对正向事件，
  `preference_multiplier = 1 + 0.25*p`；对负向事件，`preference_multiplier = 1 - 0.25*p`，
  因而 Bot 更喜欢的正向行为更有价值，更讨厌的负向行为更严重；neutral 不改变基线。
- `novelty_multiplier = max(0.2, 1 / (1 + 0.35*k))`，`k` 是该主体最近 7 天相同
  `event code + taste tag` 已应用的次数。事件账本保存计数依据，不使用“连续调用次数”猜测。
- friend 的 `scene_modifier` 为 1.0；group 对 affection/trust 的 modifier 为 0.75，mood 和
  resentment 不降权，表达公开群聊互动与一对一互动的亲密度不同，但不减轻明确越界债务。
- scheduler 的 `source_multiplier` 为 1.0；agent_tool 为 0.5，且 agent_tool 不能使用
  major/critical。自动 inbound 只产生 activity 和有限的 direct attention mood，不使用这张
  长期事件表。
- 每个主体按 UTC 日切分维度限额：affection 正向 `+8`、负向 `-12`；trust 正向 `+6`、
  负向 `-20`；resentment 增加 `+30`、修复减少 `-12`。mood 只做范围 clamp。限额防止
  scheduler 重复 tick 或 Agent 反复调用在一天内重塑关系，同时保留 critical 负向事件明显
  大于普通正向互动的非对称性。

这套规则把“主观喜恶”放在 profile，把“事件客观类型”放在目录，把“重复行为价值”放在
novelty，把“可被利用的入口强度”放在 source multiplier，四者不混为一个神秘分数。

### 4. 阶段、overlay、commitment 和 flag 分开实现

阶段使用 `relationship_index`、trust、resentment 和 flag 的资格门槛；从当前阶段向下变更
使用 5 点滞回，避免在阈值附近来回闪烁。`repair_required` 优先于 `wary`，`wary` 优先于
`cold`；overlay 影响关系感知/回复策略，但不会删除 affection/trust 历史。

commitment 是单独的结构化表，不用一条普通事件模拟“未来应该发生什么”。due 检查可由插件
scheduler 定时调用，也可在下一次关系读写时按明确操作懒惰触发；只有 pending commitment
逾期且没有 kept/repair 才创建一次 neglect debt。普通沉默永远不产生 debt。

flags 是独立的、来源受限的事实。`bond_milestone` 只能由 scheduler 或项目内确定性业务规则
设置，Agent Tool 只能读取。这样模拟 CLANNAD/Persona 的路线条件，同时防止模型靠刷分直接
跳到 special。

### 5. SQLite/WAL schema 和事务边界

关系 repository 通过 `plugin_db("hermes-plugin-milky")` 懒开连接并在短事务内完成以下表的
读写；不缓存跨 profile 的数据库路径：

```text
schema_meta(
  key PRIMARY KEY, value
)

relationship_state(
  self_id, scene, scope_id, subject_id,
  affection, trust, mood, resentment, activity_ema,
  stage, last_activity_at, last_mood_at, version,
  created_at, updated_at,
  PRIMARY KEY(self_id, scene, scope_id, subject_id)
)

relationship_events(
  event_id PRIMARY KEY, self_id, scene, scope_id, subject_id,
  event_code, taste_tag, severity, source, occurred_at,
  effect_json, state_version, created_at
)

relationship_counters(
  self_id, scene, scope_id, subject_id, counter_key, bucket_start, count,
  PRIMARY KEY(self_id, scene, scope_id, subject_id, counter_key, bucket_start)
)

relationship_commitments(
  commitment_id PRIMARY KEY, self_id, scene, scope_id, subject_id,
  kind, due_at, status, resolved_event_id, created_at, updated_at
)

relationship_flags(
  self_id, scene, scope_id, subject_id, flag, source, set_event_id, created_at,
  PRIMARY KEY(self_id, scene, scope_id, subject_id, flag)
)
```

实现可调整列类型或索引，但不得改变这些数据的原子性和唯一性。每次 `apply_event` 的事务
顺序为：校验 target/source → `BEGIN IMMEDIATE` → 读 state 并懒惰衰减 mood/activity → 检查
event_id → 检查 commitment/novelty/daily caps → 计算 effect → 写 state、counter、events 和
必要的 commitment/flag → commit。重复 event_id 返回第一次的持久化结果，不重新计算。
SQLite busy/IO/迁移错误只返回稳定分类；不删除库、不重置空状态、不回滚入站消息。

每次短事务创建并关闭自己的连接，或使用按线程/进程隔离的等价连接工厂；`check_same_thread`
和 WAL 只解决连接/读写并发，事务纪律仍由 repository 负责。数据库初始化和 migration
必须在事务内执行并写 `schema_meta`，未知未来版本只能只读失败，不得静默降级成空库。

### 6. Pipeline、Tool 和 scheduler 的边界

#### 入站

`InboundPipeline` 在 Gate 成功后调用 `observe_user_activity(canonical)`。关系旁路使用与
canonical 相同的稳定 message ID 做幂等，短事务失败通过安全 diagnostics 分类，不改变命令、
wait、Will、reply cost、资源、mapper 或 Hermes handoff。合法 Bot-directed nudge 在系统事件
观察路径中调用专门的 activity observer；其它系统事件不进入关系服务。

#### Agent Tool

工具固定为：

- `get_relationship_state`：只读当前 Milky session 对应发送者的快照；
- `record_relationship_event`：只提交事件目录允许的 minor/normal 事件。

handler 从 `get_session_env()` 读取 platform/chat/user/message/session 字段，使用 adapter
确认的 `self_id`；不提供 target override。写入幂等键为
`agent_tool:<session_id>:<message_id>:record_relationship_event`，所以不依赖可选的
`tool_call_id`。返回只包含 `applied|duplicate|error`、安全 delta、新 stage/overlay 和
版本，不回显 evidence。

#### scheduler

scheduler 通过内部服务 API 直接调用，显式传入 `RelationshipTarget`、event_id、source 和
occurred_at。它可执行 commitment due/resolve、major/critical 事件和受信 milestone，但
仍须经过同一事件目录、主体校验、日上限和事务。插件不在 `register()` 创建 scheduler；如
需要周期 tick，必须使用宿主已经提供的调度机制或连接后可取消任务，且每次 tick 只调用
幂等 due 检查。

### 7. Hermes 能力边界和失败策略

`ctx.state` 保留给少量配置/feature metadata，不保存关系 event ledger；关系数据库不写
Hermes core session state，也不修改 Hermes core。
关系 Tool 不依赖 Milky HTTP Action，缺失 session context 时安全返回错误；未同步 self_id
时即使存在历史关系也拒绝新的关系读写，避免把错误 Bot 归因到用户。

关系存储故障与 Milky 故障分离：Tool/scheduler 返回 `storage_unavailable`、
`persistence_error`、`schema_incompatible` 或参数分类；普通入站关系旁路记录有限诊断并
继续原有 pipeline。日志不写异常正文、SQL、路径、token、正文和完整 evidence。

## Risks / Trade-offs

- **[Risk]** 默认事件目录和 profile 仍然是人为建模，无法覆盖所有用户关系。→ 把事件类型、
  effect、偏好和 source 明确落账，保留版本和事件审计；未来扩展必须新增受控 event code，
  不允许开放任意 delta。
- **[Risk]** Agent Tool 可能主观误判 `kindness`/`rudeness`。→ agent_tool 使用 0.5 来源
  系数、只能 minor/normal、每日上限和 novelty；critical、commitment、milestone 留给受信
  scheduler。
- **[Risk]** SQLite 锁竞争可能让 activity observer 失败。→ WAL、短事务、有限 busy timeout、
  幂等事件和旁路失败隔离；消息管线不把关系存储当成消息交接前提。
- **[Risk]** 关系数据库 schema 演进可能破坏旧安装。→ 使用 schema_meta 和事务迁移；未知
  版本 fail-closed，不删除旧数据或静默重建。
- **[Risk]** group 活跃度可能被刷屏维持很高。→ 10 分钟 burst 递减和 36 小时半衰期只影响
  activity，不直接换算 affection/trust；长期关系仍需受控事件。
- **[Risk]** Galgame 的 Bomb/低落机制如果惩罚普通沉默会造成反直觉关系。→ 只有明确
  pending commitment 才能产生 neglect debt，普通沉默不扣长期分；overlay 与长期阶段分离。
- **[Risk]** 当前 Hermes 宿主可能没有完整 session context。→ Agent Tool 在缺失字段时拒绝
  写入，scheduler 使用显式目标；不回退到默认 chat 或最近 session。

## Migration Plan

1. 首次启用新版本时只创建插件独立关系表，不回填历史消息、不推断既有用户关系，所有主体
   从中性状态开始。
2. 启动时解析可选 `MILKY_RELATIONSHIP_POLICY`；缺失使用内置中性 profile，语法、范围或
   未知 event preference 不符合 schema 时启动失败，不静默采用不一致规则。策略版本随
   event ledger 保存，后续修改策略不重写历史事件。
3. 先上线 repository/service、迁移和纯算法测试，再接入入站 activity；随后注册只读查询
   Tool，最后打开受限写入 Tool 和 scheduler 事件。每一步都可通过配置关闭写入，但不删除
   已有数据库。
4. 回滚到不认识关系表的旧插件时，旧版本忽略独立表，既有 Milky 消息行为恢复；回滚不会
   执行“降级迁移”。重新升级时按 schema version 继续读取。若迁移失败，关系功能保持
   fail-closed，消息管线仍按既有行为运行。

## Open Questions

无。事件目录、阈值、来源权限、幂等字段和失败语义已在本 change 中固定；未来新增事件或
策略字段应以新的 OpenSpec change 变更契约，而不是在实现阶段自行扩大输入。
