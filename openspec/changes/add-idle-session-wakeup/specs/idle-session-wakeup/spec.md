## Purpose

定义插件侧对已存在、已授权 Milky 会话进行低频闲置检测和一次性主动唤醒的行为，
在不创建 Hermes session、不修改 Hermes Core 队列且不越过白名单的前提下恢复长期沉默的对话。

## ADDED Requirements

### Requirement: 仅扫描已存在且命中白名单的 Milky session

主动唤醒 watcher MUST 只考虑 Hermes session store 中已经存在、origin platform 为 `milky`、
chat key 为合法 `group:<十进制群号>` 或 `dm:<十进制 QQ 号>` 且已有 Hermes session key 的会话。
候选 chat key MUST 命中 `MILKY_ALLOWED_CHATS` 的完整条目或对应命名空间通配符；白名单为空时，
主动唤醒 MUST 没有候选。watcher MUST NOT 创建 session、从 Milky chat key 推导 Hermes session key、
扫描 temp/未知场景或触达白名单之外的会话。

#### Scenario: 已存在的白名单群会话

- **WHEN** session store 已有 `milky` 的 `group:<id>` 会话，且该 chat key 命中 `group:<id>` 或 `group:*`
- **THEN** watcher SHALL 将其作为主动唤醒候选
- **AND** SHALL 使用 Hermes 已确认的 session key 交接，不创建新的 session

#### Scenario: 已存在的白名单私聊会话

- **WHEN** session store 已有 `milky` 的 `dm:<id>` 会话，且该 chat key 命中 `dm:<id>` 或 `dm:*`
- **THEN** watcher SHALL 将其作为主动唤醒候选
- **AND** SHALL 跳过群禁言检查

#### Scenario: session 不存在或 session key 未确认

- **WHEN** 白名单包含某个 chat key，但 Hermes session store 没有该会话，或没有已确认的 Hermes session key
- **THEN** watcher SHALL 跳过该 chat
- **AND** SHALL NOT 调用 session 创建接口或猜测 session key

#### Scenario: 白名单为空或命名空间不匹配

- **WHEN** `MILKY_ALLOWED_CHATS` 为空，或候选 chat key 未命中具体条目及其对应命名空间通配符
- **THEN** watcher SHALL 不触达该 chat
- **AND** 普通入站消息既有的空白名单放行语义 SHALL 不被本能力改变

### Requirement: 闲置周期只触发一次并由人工活动重新武装

当 `enabled` 为 `true` 且会话自最近一次人工活动起的闲置时间达到 `idleSeconds` 时，watcher
MUST 最多接受一次该 inactivity epoch 的主动注入。主动注入自身、Agent 的 `[SILENT]` 回复、
回复发送失败或 watcher 重扫 MUST NOT 被视为新的人工活动；新的合法人工消息 MUST 开始新的
inactivity epoch。被宿主拒绝的注入不算已触发，但 MAY 在后续 watcher 周期重新判断，直到宿主接受、
人工活动重置或其他策略条件阻止。

#### Scenario: 达到闲置阈值

- **WHEN** 白名单内已有 session 的最近人工活动距当前时间至少 `idleSeconds`，且其他主动策略均允许
- **THEN** watcher SHALL 提交一次主动注入
- **AND** 同一 inactivity epoch SHALL 不再提交第二次已接受的注入

#### Scenario: 未达到闲置阈值

- **WHEN** 最近人工活动距当前时间小于 `idleSeconds`
- **THEN** watcher SHALL 不注入、不计入每日次数且不修改 Hermes session

#### Scenario: 新人工消息重新武装

- **WHEN** 一次主动注入已被宿主接受后，同一 chat 收到新的合法人工消息
- **THEN** watcher SHALL 将该消息视为新的 activity epoch
- **AND** 下一次达到 `idleSeconds` 后 MAY 再次主动唤醒，但仍受当日次数上限约束

#### Scenario: Agent 回复或扫描不能重新触发

- **WHEN** 主动 turn 返回 `[SILENT]`、正常回复、出站失败，或 watcher 再次读取同一个 session
- **THEN** watcher SHALL 不把这些结果当作人工活动
- **AND** SHALL 不因它们重复触发同一 inactivity epoch

### Requirement: 夜间免扰和每日接受次数

watcher MUST 使用 `MILKY_PROACTIVE_POLICY.maxAttemptsPerDay` 限制每个 chat 在 Hermes 当前本地日期
内被宿主接受的主动注入次数，默认值为 `1`。只有 `inject_message()` 明确返回接受才消耗一次；
拒绝、异常、白名单拒绝、未达到闲置阈值、禁言、busy 和 quiet hours 跳过均不消耗次数。
`quietHours` 为 `null` 时不启用免扰；配置的 `start` 与 `end` 使用 Hermes Core 当前时区的本地时间，
允许跨午夜区间。免扰结束后，仍满足闲置条件且当日仍有次数时，watcher SHALL 可以在下一轮检查触发。

#### Scenario: 默认每日只接受一次

- **WHEN** 未显式配置 `maxAttemptsPerDay`，且当天第一次主动 `inject_message()` 返回 `true`
- **THEN** 该 chat 当日计数 SHALL 变为 `1`
- **AND** 当日后续闲置 epoch SHALL 不再主动注入

#### Scenario: 注入被拒绝不计数

- **WHEN** `inject_message()` 返回 `false` 或抛出异常
- **THEN** 该 chat 的每日计数 SHALL 保持不变
- **AND** watcher SHALL 记录安全失败分类，不得声称主动 turn 已创建

#### Scenario: 免扰期间

- **WHEN** 当前 Hermes 本地时间处于配置的 `quietHours`
- **THEN** watcher SHALL 不调用 `inject_message()`
- **AND** SHALL 不消耗每日次数或标记该 inactivity epoch 已触发

#### Scenario: 免扰跨午夜

- **WHEN** `quietHours.start` 晚于 `quietHours.end`，且当前时间位于起点至次日终点之间
- **THEN** watcher SHALL 将当前时间视为免扰时间
- **AND** 离开该区间后仍可按闲置条件进行一次主动唤醒

### Requirement: 主动事件使用固定英文内容

每次主动注入 MUST 使用以下固定、简短的英文内容，并以事件前缀保留事件名
`idle_session_wakeup`：

~~~text
<event idle_session_wakeup> System message: This conversation has been quiet for a long time. If appropriate, liven things up with a brief message, meme, or image. If you have nothing worthwhile to add, reply exactly [SILENT].
~~~

注入 MUST 通过 Hermes 已有 `inject_message` 作为 user-role synthetic message 交接；插件不得直接
调用 Milky Action 生成内容。Agent 没有有价值内容时，回复 MUST 精确为 `[SILENT]`，其余回复继续
进入现有 Hermes/Milky 出站流程。

#### Scenario: 接受主动事件

- **WHEN** 候选 session 通过闲置、白名单、每日次数、免扰、busy 和禁言检查
- **THEN** 插件 SHALL 使用确认的 Hermes session key 调用 `inject_message()`
- **AND** 注入正文 SHALL 与本 requirement 的英文事件内容完全一致

#### Scenario: 宿主不接受主动事件

- **WHEN** Hermes 没有注入能力、session key 不再有效、注入权限不可用或 `inject_message()` 返回拒绝
- **THEN** 插件 SHALL 保留本地 epoch 和每日计数的未接受状态
- **AND** SHALL 不调用 Milky 发送 Action、不创建替代 session 或伪造成功

### Requirement: 主动 turn 遵守 busy 和群禁言安全边界

插件 MUST 在确认当前 chat 没有正在运行的 Hermes Agent turn 后才提交主动注入；busy 状态未知时
MUST 按 busy/unsupported 跳过。group session 还 MUST 要求 `MuteTracker` 明确显示 Bot 当前为
`unmuted`；初始化未完成、维护失败、member mute、whole mute 或状态为 `unknown` 时 MUST 跳过。
dm session MUST 不查询群禁言状态。

#### Scenario: Hermes session 正在处理

- **WHEN** 候选 session 当前已有运行中的 Agent turn
- **THEN** watcher SHALL 跳过本轮
- **AND** SHALL 不通过主动注入打断、复制或重排 Hermes Agent 队列

#### Scenario: 群禁言状态未知或已禁言

- **WHEN** group session 的 member/whole mute 任一状态不是明确的 `unmuted`
- **THEN** watcher SHALL 跳过本轮
- **AND** SHALL 不发送主动消息或改变 `MuteTracker` 状态

#### Scenario: 私聊不读取群状态

- **WHEN** 候选为合法 dm session
- **THEN** watcher SHALL 不调用群禁言查询
- **AND** SHALL 只依据 session、白名单、闲置、免扰、次数和 busy 条件决策

### Requirement: watcher 生命周期和失败诊断可控

主动 watcher MUST 由插件侧在连接完成初始同步、恢复已有 session route 且普通消息入口开放后启动，
使用固定的低频扫描周期，不新增用户配置项。每个 adapter 实例最多运行一个 watcher；disconnect、
重连切换和插件卸载 MUST 取消旧 watcher 并释放其等待状态。watcher 单轮失败 MUST 使用安全的
固定分类记录并继续保护普通入站/出站流程；插件重启不承诺恢复进程内 epoch 或每日计数状态。

#### Scenario: 连接尚未就绪

- **WHEN** 登录、群列表或自身禁言状态初始同步尚未完成
- **THEN** watcher SHALL 不启动
- **AND** SHALL 不读取 session store 或提交主动注入

#### Scenario: 重连不复制 watcher

- **WHEN** 已连接 adapter 发生重连
- **THEN** 旧 watcher SHALL 先停止，随后最多启动一个新的 watcher
- **AND** SHALL 不因重连创建重复定时器或并行扫描同一 chat

#### Scenario: 停止时清理 watcher

- **WHEN** adapter disconnect 或插件卸载
- **THEN** watcher SHALL 被取消并等待清理
- **AND** 清理完成后 SHALL 不再调用 Hermes 或 Milky

#### Scenario: 单轮扫描失败

- **WHEN** session 列表读取、时间读取或某个候选的状态判断失败
- **THEN** 插件 SHALL 记录不包含 token、正文、URL、路径或异常正文的固定失败分类
- **AND** SHALL 继续处理其他 chat，普通消息流程 SHALL 不因该失败被阻断
