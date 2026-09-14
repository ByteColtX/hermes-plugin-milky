## 1. 契约、配置与测试夹具

- [ ] 1.1 定义 friend/group `RelationshipTarget`、六段 stage、overlay、event code、severity、source、taste tag、commitment status 和稳定错误分类；用参数校验单测验证非法 scene、ID、事件、来源和范围均 fail-closed
- [ ] 1.2 增加 `MILKY_RELATIONSHIP_POLICY` 启动配置及内置 neutral profile，校验 liked/neutral/disliked、权重范围、schema version 和未知字段；用配置单测覆盖缺省、合法、自定义、空值、非法 JSON 和越界配置
- [ ] 1.3 建立不含真实 QQ 号、正文、token、路径或媒体 URL 的 friend/group/nudge/event fixture；验证 fixture 可表达群成员隔离、Bot-directed nudge、重复事件和缺失 Hermes session context

## 2. 持久化与迁移

- [ ] 2.1 使用 Hermes `plugin_db("hermes-plugin-milky")` 建立独立 schema_meta、relationship_state、relationship_events、relationship_counters、relationship_commitments 和 relationship_flags 表及必要索引；用 fake storage 验证数据目录不落入插件安装目录且注册阶段不打开数据库
- [ ] 2.2 实现 schema version 初始化和事务迁移，未知未来版本、损坏数据和迁移失败均返回稳定分类且不清空旧数据；用旧版本库、未来版本库和中途失败 fixture 验证 rollback/fail-closed
- [ ] 2.3 实现短事务 repository，原子完成懒衰减、event_id 去重、状态更新、counter、账本和 commitment/flag 变更；用重复提交、并发写入、SQLite busy/IO 失败测试验证无部分状态和无伪造成功
- [ ] 2.4 实现 repository 的 profile 变化、disconnect close 和重复 close 行为；用连接计数和重启/重连测试验证关系数据保留、关闭后拒绝写入且不创建第二个隐式连接

## 3. 关系算法与服务

- [ ] 3.1 实现 activity_ema 的 36 小时半衰期、10 分钟 burst 边际递减、逆序时间保护和 `[0,100]` clamp；用首条/重复消息、36 小时衰减、时钟回拨和长期刷屏测试验证只影响 activity
- [ ] 3.2 实现固定事件目录、severity multiplier、preference multiplier、7 天 novelty、scene/source modifier、每日维度上限和 Decimal/等价确定性舍入；用设计表的 normal/critical、liked/neutral/disliked、friend/group、scheduler/agent_tool 组合测试验证精确 delta
- [ ] 3.3 实现 affection/trust/mood/resentment 独立更新、12 小时 mood 衰减、阶段指数、六段门槛、5 点降级滞回和 overlay 优先级；用 trust 门槛、special 缺 flag、wary/repair_required/cold 及长期历史保留测试验证
- [ ] 3.4 实现 commitment 的 pending→kept/broken/repaired/expired 合法迁移、due/neglect_debt 一次性处理和 apology/repair_action 的债务上限修复；用普通沉默、重复 scheduler tick、无债务修复和匹配债务修复测试验证
- [ ] 3.5 实现 scheduler 受信事件与 Agent Tool 事件共享的服务门面，并记录 policy/event 版本和安全 effect 摘要；用不同来源权限测试验证 Agent 不能使用 major/critical、清空 resentment 或设置 milestone

## 4. Milky 入站与生命周期接线

- [ ] 4.1 在 adapter/注册实例中绑定已确认 `self_id` 和懒加载关系服务，不在 `register()` 联网、开库、建主体或创建长期任务；用 plugin entry fake host 验证注册阶段无外部副作用和未确认身份拒绝读写
- [ ] 4.2 在现有 pipeline 的 canonical、dedup、Gate 之后、命令/Will 分流之前接入用户 activity observer；用 ingress sequence 断言验证 wait 计入一次、trigger 不重复、Gate deny/self/temp/重复消息不计入且既有 reply cost/handoff 不变
- [ ] 4.3 在系统事件 observe 路径接入仅限合法 Bot-directed `friend_nudge`/`group_nudge` 的 activity observer；用 nudge 方向、chat key、allowlist/malformed、重复事件和其他系统事件测试验证不创建 canonical、buffer、Will 或 Hermes turn
- [ ] 4.4 将关系旁路存储失败、schema 不兼容、busy 和短事务超时映射为安全 diagnostics，并保持消息主流程继续；用 fake repository 注入异常验证不回滚 canonical/Gate/Will/资源/mapper/handle_message 结果且不报告假成功
- [ ] 4.5 在 disconnect/reconnect 中释放 repository 和可取消维护任务而不清理持久关系；用重复停止、SSE 重连和进程重建 fake 集成测试验证不恢复未知断线事件、不重置关系、不重复执行事件

## 5. Agent Tool 与 scheduler 权限

- [ ] 5.1 在固定 ToolSpec 中注册 `get_relationship_state` 和 `record_relationship_event`，只声明事件目录允许字段和结构化返回；用 manifest/registry 测试验证不开放 raw SQL、任意 delta、stage/flag setter 或 Action catalog
- [ ] 5.2 实现 Tool handler 对 `HERMES_SESSION_PLATFORM`、`HERMES_SESSION_CHAT_ID`、`HERMES_SESSION_USER_ID`、`HERMES_SESSION_MESSAGE_ID`、`HERMES_SESSION_ID` 和已确认 self_id 的校验；用 friend/group 合法 context、缺失 context、伪造 target、冲突 user/chat 和未同步身份测试验证安全拒绝
- [ ] 5.3 实现 Agent Tool 的 `session_id + message_id + operation` 幂等键、minor/normal/source cap 和无 evidence 持久化；用模型重复调用、缺少 message ID、重复 taste tag、critical/milestone/clear_resentment 参数测试验证 duplicate/forbidden/invalid 分类
- [ ] 5.4 暴露 scheduler 的显式 target/event_id/occurred_at 服务调用，并限制 commitment、major/critical 和 milestone 只由 scheduler 使用；用跨 session 目标、缺 event_id、重复 event_id 和其他 Bot self_id 测试验证不借用当前 Agent context

## 6. 测试、文档与主规范

- [ ] 6.1 增加关系纯算法、repository、迁移、并发、幂等和隐私边界测试；运行 `uv run pytest -q` 的关系聚焦测试并记录精确公式、阶段和失败分类结果
- [ ] 6.2 增加 fake Hermes/adapter 集成测试，覆盖私聊、群成员隔离、Bot 隔离、activity-only、nudge、Gate/Will 顺序、Tool context、scheduler 和关系旁路失败；验证既有入站/出站行为无回归
- [ ] 6.3 更新 `ARCHITECTURE.md` 和 `README.md`，说明关系主体键、状态维度、活跃度只统计用户行为、事件/修复规则、Tool/scheduler 授权、Hermes `plugin_db()` 持久化、配置和降级边界；审阅确认不写入真实个人 QQ、正文、凭证或未验证能力
- [ ] 6.4 将稳定行为同步到 `openspec/specs/relationship-system/spec.md`，并把本 change 对 `hermes-message-pipeline`、`qq-action-tools`、`plugin-lifecycle` 和 `security-boundaries` 的 delta 纳入主规范；运行 OpenSpec strict validation 验证 delta 与主规范一致

## 7. 质量门禁与受控验证

- [ ] 7.1 运行关系相关 pytest、`uv run ruff check .`、`uv run ruff format --check .` 和 `git diff --check`，修复实现、测试、文档和规范问题并把命令结果写入 evidence ledger
- [ ] 7.2 运行完整 `uv run pytest -q`、`uv build` 和 `openspec validate --changes --strict`，分类记录真实 Hermes 未覆盖、fake-only 通过和外部阻塞，不把 skip 当成集成通过
- [ ] 7.3 在获得明确写入授权且目标命中运行时 `MILKY_ALLOWED_CHATS` 后，使用 `uv run scripts/milky_smoke.py` 做关系只读/写入 smoke；没有真实服务或未获授权时记录 skip，不发送或修改外部 QQ 状态
