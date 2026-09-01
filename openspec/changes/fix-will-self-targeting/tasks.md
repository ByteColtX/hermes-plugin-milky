## 1. 契约与脱敏 fixture

- [ ] 1.1 增加 self mention、他人 mention、`mention_all`、引用 Bot、引用他人和 `reply.data.sender_id` 缺失的合成消息 fixture；验证 fixture 保留协议字段且不包含凭证、真实 QQ、媒体 URL 或敏感正文
- [ ] 1.2 增加 group/friend self-poke、poke 他人、Bot 发出 poke、方向字段缺失/非法/冲突的合成事件 fixture；验证字段来源限于已确认协议字段且未知目标不被标记为 self-poke
- [ ] 1.3 扩展 routing case fixture，覆盖 quote/mention/poke 单信号、与 `allMessage`/关键词的 OR 合并和多信号组合；验证非 Bot 目标不会触发对应自身规则

## 2. 规范化目标特征

- [ ] 2.1 在消息规范化结果中增加独立的 self-quote 特征；验证 `reply.data.sender_id == self_id` 时为真，引用他人或 `reply.data.sender_id` 未知时为假，同时保留 reply 存在性与目标 ID，并确认当前 `message.sender_id` 不参与判断
- [ ] 2.2 保持 self mention 与 all mention 的独立判断；验证只有 `mention.user_id == self_id` 产生 self mention，名称、正文和 `mention_all` 不会替代目标 ID
- [ ] 2.3 在 nudge 观察结果中生成受协议字段约束的 self-poke 特征；验证 group 按 `receiver_id`、friend 按自身接收/发送方向判断，字段缺失或冲突时保持 unknown/非命中且不执行网络 I/O
- [ ] 2.4 将 self-quote 和 self-poke 特征安全传递到 Will 输入；验证未确认目标不被转换为 true，既有正文、reply ID、raw、系统 context 和普通消息 event_type 不变

## 3. Routing 决策与系统边界

- [ ] 3.1 将 `routing.quote` 改为只消费 `reply.data.sender_id == self_id` 的 self-quote 特征；验证引用其他用户或 `reply.data.sender_id` 未知时不命中 quote，self-quote 为真且动作是 `trigger` 时仍可触发
- [ ] 3.2 将 `routing.mention` 和 `routing.poke` 固定为 Bot 自身目标语义；验证他人提及、poke 他人、Bot 发出的 poke 和未知方向不命中，并保持 `mentionAll`、`allMessage`、关键词及 OR 合并行为
- [ ] 3.3 保持 nudge 的 observe-only 生命周期；验证 self-poke 的 routing 信号不会绕过 Gate、创建普通 `MessageEvent`、Agent turn、reply cost 或隐式 Action 调用
- [ ] 3.4 增加 willingness 回归测试；验证本 change 不改变 willingness 的独立数值公式、force、增益、随机抽样和系统事件边界

## 4. 集成、文档与安全回归

- [ ] 4.1 增加 normalizer、routing、system event 和 fake Hermes pipeline 集成回归；验证 friend/group、self/other/unknown 三类目标与 wait/trigger 结果、context-only 结果一致
- [ ] 4.2 更新 `ARCHITECTURE.md`、`README.md` 及必要的测试说明，明确 `quote`、`mention`、`poke` 均表示关于 Bot 自身的信号，并注明 nudge 仍为 observe-only；验证文档不引入旧字段或未确认协议语义
- [ ] 4.3 增加副作用安全断言；验证目标判断不联网、不读文件、不调用 reply/resource Action，不输出 token、Authorization、完整 raw、URL、路径或敏感正文
- [ ] 4.4 运行聚焦测试 `uv run pytest -q tests/test_will_routing.py tests/test_will_willingness.py tests/test_normalizer.py tests/test_inbound_context_rendering.py tests/test_hermes_pipeline.py`；记录失败分类与修复结果
- [ ] 4.5 运行完整质量门禁 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`；记录 Hermes host、协议或测试基础设施缺失等 skip/blocked 证据
- [ ] 4.6 运行 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`；验证本 change 的 proposal、三份 delta spec、design 和 tasks 一致，未获明确授权时不执行真实 Milky 写入或发送 smoke

## Evidence ledger

| 阶段 | 命令/证据 | 结果 | 反馈分类与下一步 |
|---|---|---|---|
| 规划 | 已读取 `AGENTS.md`、`ARCHITECTURE.md`、README、相关主 specs、全部未归档 change artifacts、Will/入站源码与测试，并创建本 change 的 proposal、delta specs、design | 已完成 | 目标语义固定为 self mention、self quote、self-poke；等待 apply workflow 实现 |
| fixture/实现 | 待 apply：消息/nudge/routing 合成 fixture 与目标特征测试 | 待执行 | 通过后继续 routing 与 pipeline 回归；不写入真实协议响应 |
| 集成与安全 | 待 apply：`uv run pytest -q tests/test_will_routing.py tests/test_will_willingness.py tests/test_normalizer.py tests/test_inbound_context_rendering.py tests/test_hermes_pipeline.py` | 待执行 | 失败按目标分类、协议、Hermes API、并发或安全归类 |
| 质量门禁 | 待 apply：全量 pytest、Ruff、format、build、diff check | 待执行 | skip/blocked 只记录实际原因，不视为真实 Milky 或 Hermes host 通过 |
| OpenSpec | 待 apply：`npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict` | 待执行 | 未授权时不执行真实 Milky 写入、发送或其他外部状态 smoke |
