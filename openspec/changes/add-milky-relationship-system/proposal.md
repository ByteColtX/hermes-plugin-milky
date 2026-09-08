## Why

当前插件没有跨进程、按 QQ 用户隔离的关系状态，Agent 只能把每次互动当作无状态消息处理。简单地对每条消息固定加减分既无法表达 Bot 对不同互动类型的主观喜恶，也会让群聊中的一个成员影响其他成员；同时，Hermes 已经提供了插件级持久化和当前会话上下文，可以在不修改 Hermes core 的前提下建立可审计的关系状态。

本 change 把 Galgame 中较稳定、可迁移的机制映射到 Milky：分阶段的关系 Rank、按角色偏好的事件选择、短期情绪与长期关系分离、忽视/失约形成的可修复负面状态，以及事件 flag 和一次性/递减收益。普通活跃度只作为用户行为信号，不把刷屏直接等同于好感度。

## What Changes

- 新增按 Bot `self_id` 隔离的关系状态；私聊以 `self_id + user_id` 为键，群聊以 `self_id + group_id + member_id` 为键，群成员之间互不共享好感度。
- 新增长期 `affection`、`trust`，短期 `mood`、未修复 `resentment`、用户行为 `activity_ema`、关系阶段、负面覆盖状态和受限 flags；关系阶段不再由单一分数直接决定。
- 新增固定事件目录和 Bot 主观偏好配置。事件只能使用事件类型、严重程度和来源等受限输入，服务根据偏好权重、事件新鲜度、重复递减、当前阶段和频率上限计算影响，调用方不能提交任意 delta。
- 将经过 canonical、TTL dedup 和 Gate 的用户消息接入活跃度统计；只统计用户行为，不把 Bot 回复、Agent Tool 调用、scheduler tick 或主动消息算作用户活跃度。普通消息不会自动持续增加长期 affection。
- 新增失约、越界、侮辱等负面事件和 `repair_required`/`wary`/`cold` 覆盖状态；普通沉默不扣分，只有存在明确 pending commitment 时才产生 neglect debt；道歉、补救和连续可靠行为按受限规则修复关系。
- 允许插件内部 scheduler 通过服务接口记录经过校验的事件，并允许 Agent 通过显式 Milky Tool 查询当前关系或记录受限互动事件；两条入口共享同一事务、幂等和授权边界。
- 使用 Hermes 官方 `plugin_db()` SQLite/WAL 持久化关系状态、事件账本、计数器、flags 和 commitments；不使用 Hermes core 的 session state，不在注册阶段联网、启动长期任务或初始化未授权的外部存储。
- 更新入站流水线、ToolSpec、生命周期/安全契约、文档和测试；关系持久化失败不得伪造成功、不得阻塞或回滚已通过 Gate 的 Hermes 消息交接。

## Capabilities

### New Capabilities

- `relationship-system`: 定义私聊与群成员关系键、关系状态维度、活跃度统计、偏好驱动的事件规则、阶段/负面覆盖、修复、持久化、scheduler/API 与 Agent Tool 的可观察行为。

### Modified Capabilities

- `hermes-message-pipeline`: 明确关系观察发生在 canonical、dedup 和 Gate 之后，并与 wait/trigger、命令、系统事件和 Hermes handoff 保持边界；关系更新失败不得改变既有消息管线结果。
- `qq-action-tools`: 增加固定、可审计的关系查询和受限事件 ToolSpec，不开放任意关系字段或任意 Milky Action。
- `plugin-lifecycle`: 明确关系数据库和维护状态的懒加载、连接关闭、重连不重置持久化关系，以及注册阶段不得产生外部副作用。
- `security-boundaries`: 明确 Agent Tool 只能访问当前已确认 Milky 会话对应的关系主体，scheduler 必须显式提供经过校验的目标和 event ID，且事件输入不得携带原始敏感正文。

## Impact

- 影响 `inbound/pipeline.py`、`adapter.py`、`__init__.py`、`plugin.yaml`、`outbound/tools.py` 以及新增的 relationship repository/service、事件模型和配置模块。
- 新增 Hermes `plugins.plugin_storage.plugin_db("hermes-plugin-milky")` 依赖边界，使用独立 SQLite/WAL 表保存关系状态和事件账本；Hermes core 与 `/Users/bytecolt/PythonProjects/hermes-agent` 不修改。
- 需要补充关系算法、SQLite 事务/迁移、群成员隔离、Tool 授权、幂等、异常降级和 fake Hermes 集成测试，并同步 `ARCHITECTURE.md`、`README.md` 与主规范。
- 这是新增持久化行为和 Agent 工具能力；未配置关系策略或旧 Hermes 宿主缺少必要 session context 时，系统必须保持安全的只读/不变更降级，而不是猜测目标或写入默认关系。
