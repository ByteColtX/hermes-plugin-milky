## 1. 契约与脱敏 fixture

- [ ] 1.1 建立 friend/group 的内置命令、插件命令、未知命令和普通正文 event fixture，覆盖前导空白、参数、重复 message ID、Gate 拒绝、temp 与系统事件；使用合成身份和中性正文，运行 fixture 安全断言确认不含 token、Authorization、真实 ID、路径或 live 响应
- [ ] 1.2 建立 `get_impl_info` 成功原始 JSON、未知扩展字段、缺失字段、rejected、非 JSON、HTTP 错误和 transport_unknown fixture；验证成功 fixture 可检查完整 envelope 原样交付，失败 fixture 只能暴露安全分类

## 2. 入站命令通道

- [ ] 2.1 实现只针对纯文本斜杠正文的命令识别，拒绝把带媒体、reply、forward、未知 segment 或普通正文误判为命令；用 friend/group、前导空白和混合 segment 单元测试验证边界
- [ ] 2.2 将命令分支接入 canonical → TTL dedup → per-chat admission → Gate 之后、Will 之前的流水线；测试确认 Gate deny、temp 和系统事件不会调用命令 handler，合法命令不会增长 buffer、修改 Will、补全资源或扣 reply cost
- [ ] 2.3 为命令建立专用 Hermes MessageEvent 映射，保留 `/command args` 正文、Milky source、`dm:`/`group:` chat key、sender 和 message ID，并设置宿主 command 类型与 `allow_gateway_control=True`；回归普通消息仍使用 header、channel context 和 `allow_gateway_control=False`

## 3. `/milky` 注册与协议调用

- [ ] 3.1 为 `get_impl_info` 增加受统一 Milky HTTP 边界保护的原始响应 seam，验证请求使用 prefixed `/api/get_impl_info`、POST、Bearer 和 `{}`，成功 data 包含五个已确认字符串字段，未知顶层/data 字段保持不变，且 response/client 资源正确释放
- [ ] 3.2 通过根入口的 `ctx.register_command()` 注册唯一首批插件命令 `/milky`，验证命令元数据、宿主内置命令冲突规则和不注册任意 Action catalog；额外参数在网络访问前返回 usage/`invalid_input` 且 Action 调用次数为零
- [ ] 3.3 实现 `/milky` 成功回复的直接原始 JSON 交付，验证没有字段摘要、说明前缀、Markdown code fence 或后缀，并覆盖包含扩展字段的完整 envelope；失败时验证只返回 `rejected`、`malformed`、`transport_unknown` 或 `unsupported` 等安全分类

## 4. 生命周期与 Hermes 交接

- [ ] 4.1 将同一个命令 service 注入 adapter factory，并在 connect 成功后绑定生命周期拥有的 Milky client、在连接失败/disconnect 后解除绑定；验证注册阶段无网络/后台任务，未连接或停止后不创建旁路 client、不访问网络且不报告假成功
- [ ] 4.2 覆盖多个活动 client 无 source/profile 选择能力时的 fail-closed `unsupported` 行为，并验证不会随机选择凭证或泄露其他 profile 信息；用生命周期单元测试和安全日志断言固定该边界
- [ ] 4.3 用 fake Hermes 验证内置 `/status`、带参数内置命令、`/milky` 和未知斜杠命令分别进入 Hermes 既有分发、插件 handler 或 unknown-command 路径，不进入 Agent 普通正文；验证 Agent 忙碌时不由插件复制 Hermes busy/follow-up/interrupt 队列，并记录宿主即时执行语义的实际结果
- [ ] 4.4 用 fake Milky transport 和 fake Hermes 组装 friend/group 端到端回归，验证 dedup/Gate/命令分支/handler/Action/回复串联正确，普通消息 Will 行为不回归，日志和异常不含凭证、完整响应、路径或正文

## 5. 文档、质量门禁与交付证据

- [ ] 5.1 更新 `ARCHITECTURE.md`、`README.md` 和能力矩阵，说明命令通道位置、Hermes 内置/插件命令所有权、`/milky` 原始 JSON 行为、single-client/多 client `unsupported` 边界和不支持任意 Action catalog；验证文档不把未实现能力写成已交付
- [ ] 5.2 运行相关单元/集成测试以及 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check`；将真实结果、失败分类和未解决风险记录在本 change 证据台账，不把未执行项标记为通过
- [ ] 5.3 运行 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`，检查 proposal、spec、design、tasks 和现有架构边界一致；若需要 Milky 实机核验，只执行不产生写入副作用的 `get_impl_info`，并记录脱敏的 Action、响应分类、时间和 runtime-unknown/unsupported 结论

## 6. Execution evidence

| 任务 | 自动化证据 | Milky 只读证据 | 反馈分类与回归 | 未解决风险 |
|---|---|---|---|---|
| 1.1–5.3 | 待 apply 阶段逐项填写；未执行前不得标记通过 | 待 apply 阶段按需填写；不执行写入 Action | 待 apply 阶段记录协议字段/路径、Hermes API、并发/顺序、权限/安全、真实环境差异或测试基础设施分类 | 当前变更只完成 planning；运行时代码、fixture、测试和文档均待实现 |
