## 1. OpenSpec setup

- [x] 1.1 Initialize the spec-driven OpenSpec structure for Codex and verify the generated skills are present under `.agents/skills/`
- [x] 1.2 Add project context, artifact rules, operation guidance, and the active-change policy to `openspec/config.yaml` and `openspec/README.md`, then verify OpenSpec instructions expose the updated guidance

## 2. Capability contracts

- [x] 2.1 Create one delta `spec.md` for each capability listed in `proposal.md` and verify every path matches exactly
- [x] 2.2 Cover observable success, failure, boundary, unknown, privacy, and degradation behavior from `ARCHITECTURE.md`, then verify the capability review has no uncovered contract category
- [x] 2.3 Verify every requirement has a scenario with exactly four-hash `#### Scenario:` headings and explicit WHEN/THEN outcomes

## 3. Review and validation

- [x] 3.1 Review proposal, specs, design, and tasks in OpenSpec order and verify the change remains under `openspec/changes/` because the runtime is still a skeleton
- [x] 3.2 Run OpenSpec strict validation and inspect the generated status for missing artifacts or capability mismatches
- [x] 3.3 Run repository documentation/whitespace checks and record any unavailable runtime quality gates without claiming them as passed

## 4. Protocol foundation

- [x] 4.1 **T01 包布局与唯一入口**：建立目标 Python 包布局，实现根 `__init__.py::register(ctx)` 的安全外壳，并在根 `tools.py::register_tools(ctx)` 提供 Hermes 工具发现入口；保持导入和注册阶段无网络与长期后台任务；验证入口测试、工具发现、缺失配置错误和包布局检查通过
- [x] 4.2 **T02 配置与 manifest**：实现 URL/prefix 派生、Bearer 认证配置、allowlist、嵌套 Will policy、buffer size 和脱敏摘要；验证配置边界、HTTPS、空参数 `{}`、旧 schema 拒绝及 manifest 契约测试通过
- [ ] 4.3 **T03 Milky 协议 fixtures**：建立登录、群列表、成员信息、friend/group/temp 消息、全部 segment、系统事件及成功/失败 envelope 的脱敏 fixtures；验证每个 fixture 都有预期 parser 结果并覆盖 malformed、缺字段和协议失败
- [ ] 4.4 **T04 DTO 与 tolerant parser**：实现 Milky envelope、event、message、friend/group/entity、forwarded-message 和每个已知 segment DTO；temp 解析后返回 `ignored_temp`，不建立 canonical；保留安全 raw/未知扩展；验证 T03 全部 fixtures 可确定解析、非法身份分类失败且 parser 无网络 I/O
- [ ] 4.5 **T05 HTTP Action client**：实现统一 POST JSON、Bearer、响应解码、超时、连接关闭、错误分类和最小 data 校验，并覆盖状态同步、消息、资源和上传所需接口；验证 fake transport 覆盖 timeout、非 JSON、HTTP/retcode 错误、缺少 `message_seq` 和不盲目重试
- [ ] 4.6 **T06 SSE `/event` 事件流**：实现 SSE GET、event/data 边界、多行 data、handler 隔离、断线重连、退避、取消和资源释放，不引入 WS echo/pending 模型；验证 fake stream 覆盖 malformed/unknown event、handler 异常、重连、取消和 receive loop 不阻塞
- [ ] 4.7 **T07 canonical、chat key 与 TTL dedup**：实现 `group:`、`dm:` 规范化、temp 忽略、canonical record、无稳定 ID 降级、有界 TTL 去重和 per-chat admission 边界；验证同号隔离、重复帧在资源/Will/Hermes 前停止、同文不同 ID 独立处理及非法目标本地失败

## 5. Inbound strategy and state

- [ ] 5.1 **T08 normalizer、extractor 与 WillInput**：实现 text、mention、quote、image、file、record、video、forward 和未知 segment 的无网络规范化，并生成策略特征和延迟媒体引用；验证 friend/group、temp 忽略、全部 segment、空内容丢弃及 normalizer 无外部副作用
- [ ] 5.2 **T09 Gate registry 与 per-chat admission**：实现 Self、allowlist、mute 三道门禁的固定顺序、ingress sequence 和同 chat 短暂 admission 串行；验证 Gate 无网络/随机/发送副作用，deny 不增长 buffer 或修改 Will，并验证 admission 不覆盖 Agent 执行
- [ ] 5.3 **T10 wait buffer 与 detached trigger batch**：实现默认 20、可配置上限、0 禁用历史、历史 FIFO 溢出、原子 drain、历史/current 分离和交接失败策略；明确 wait buffer 只保存 Will 历史上下文而不是 Agent 执行队列；验证 wait 不调用 Hermes，trigger 不重复消息，buffer 隔离且失败不无条件回填
- [ ] 5.4 **T11 routing Will engine**：实现 direct、mention、mentionAll、mentionHere、quote、image、poke、group 的 nested routing 和固定优先级；验证多信号优先级、mention 类型独立、poke observe-only 及 routing 无网络副作用
- [ ] 5.5 **T12 willingness engine**：实现本项目定义的 YesImBot-inspired 默认值、嵌套配置、weighted silence、阈值衰减、marginal/dynamic gain、概率、force、关键词、poke 和提交即 reply cost；验证确定性向量、浮点容差、时钟回拨、ratio 分段、概率 clamp、独立 chat 状态和提交失败不扣费
- [ ] 5.6 **T13 MuteTracker**：实现 login → group list → self member 查询顺序、`shut_up_end_time`、二态 whole/member mute、初始 fail-closed、离群清理、事件更新和有锁冷却刷新；验证初始化前不放行、查询失败保持 muted/unmuted 原状态、`duration=0` 取消、私聊失败不刷新群状态

## 6. Hermes mapping and outbound

- [ ] 6.1 **T14 媒体与 reply resolver**：仅在 trigger 阶段查询资源/reply，使用 Hermes 公共 media helper，生成失败占位并保留安全诊断；验证 wait 阶段零资源调用、无插件缓存/下载目录/本地路径拼接及 reply 失败降级
- [ ] 6.2 **T15 Hermes MessageEvent 与入站流水线**：编排 message_receive → normalize → dedup → admission → Gate → buffer → Will → drain → detached resolver/mapper → Hermes `handle_message()`，并实现 friend/group、temp 忽略和系统事件边界；验证 fake Hermes 中 transcript、channel_context、资源 helper、handle_message 快速提交、Agent 忙碌不阻塞 admission 且由 `busy_input_mode` 接管，以及提交/异常扣费次数
- [ ] 6.3 **T16 出站 formatter、sender、文件上传与首批工具**：实现 group/dm 路由、Milky segments、空消息拒绝、长文本分块、文件 upload、SendResult、错误分类，以及名片点赞、戳一戳、撤回群消息三个显式 ToolSpec；验证 group/dm Action、temp/非法目标本地 unsupported、工具参数本地校验、撤回不自动重试、`message_seq` 稳定 ID、文件不进入 message segments 及群失败刷新

## 7. Lifecycle and release

- [ ] 7.1 **T17 standalone/cron sender（可选）**：仅在确认 Hermes standalone sender 扩展点后复用出站边界，不共享 live adapter、buffer 或 Will；验证签名、目标校验、脱敏和未确认时保持 unsupported，不阻塞 v0.1 核心
- [ ] 7.2 **T18 adapter 生命周期与 register 组装**：在 register 中组装依赖，在 connect 中完成初始同步后启动事件消费，在 disconnect 中释放全部 task/request/timer；验证无导入网络、初始化顺序、重复停止、重连不复制 handler/状态、不重新扫描禁言及停止后无继续发送
- [ ] 7.3 **T19 本地 Milky 集成与故障演练**：使用运行时环境变量执行只读同步、SSE、受控 group/dm、mute refresh 和文件 upload smoke；验证请求/响应脱敏、路径/Bearer/body、message_seq、重连和真实差异均有可复现记录，或明确记录外部阻塞
- [ ] 7.4 **T20 质量门禁与文档发布**：运行 pytest、ruff、format、build、lock 和 diff 检查，审查依赖方向、秘密脱敏、媒体所有权、能力矩阵并更新实现状态；验证所有完成定义都有自动化或真实证据，未实现能力仍明确标记且提交信息符合中文 Conventional Commits

## 8. Dependency and delivery order

依赖关系如下；同一阶段内没有依赖的任务可以并行，但后续任务必须等待其前置任务的代码、测试和证据完成：

```text
T01 ──┬── T02 ──┬── T05 ──┬── T06 ──┐
      └── T03 ──┴── T04 ──┴── T07 ──┼── T08 ──┬── T09 ──┬── T10 ──┐
                                     │         ├── T11 ──┤         │
                                     │         └── T12 ──┴───────────┤
                                     └──────────── T13 ─────────────┤
                                                                   ▼
                              T14 ───────────────────────────────► T15
                              T16 ───────────────────────────────► T18 ─► T19 ─► T20
                                └──────────────────────────────────► T17（可选）
```

- T01 无依赖；T02 依赖 T01；T03 无依赖；T04 依赖 T03。
- T05、T06 依赖 T02、T03；T07 依赖 T04、T06；T08 依赖 T04、T07。
- T09 依赖 T07、T08；T10 依赖 T09；T11、T12 依赖 T08；T13 依赖 T02、T05、T06。
- T14 依赖 T04、T05、T10；T15 依赖 T09–T14 的相关任务；T16 依赖 T02、T05、T13。
- T17 依赖 T16 且为可选；T18 依赖 T05、T06、T13、T15、T16；T19 依赖 T18；T20 依赖 T01–T16、T18、T19。
- 四个交付阶段依次为：T01–T07 协议基础、T08–T13 入站策略与状态、T14–T16 Hermes 映射与出站、T18–T20 生命周期与发布。T17 不阻塞核心交付。
- 每个阶段应能单独回滚；同时修改协议、Will 算法和 Hermes mapper 时应拆分提交，以便区分协议、策略和框架契约回归。

## 9. Execution evidence

任务勾选状态以上述 checkbox 为唯一来源；本表只记录证据、实机反馈和风险，不能替代任务状态。

| 任务 | 代码/fixture 与自动化证据 | 本地 Milky 证据 | 反馈/回归 | 风险或阻塞 |
|---|---|---|---|---|
| T01 | `tests/test_plugin_entry.py`：根 `__init__.py::register(ctx)`、namespaced 加载、工具发现、无网络/长期任务、启动配置边界和八个源码 package 布局测试通过（7 项）；全套 `uv run pytest`（37 passed）、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check` 通过 | — | 已确认 Hermes directory plugin 使用根目录 `plugin.yaml`、`__init__.py` 和 `tools.py`；配置缺失的具体解析行为由 T02 覆盖 | T01 的入口安全外壳和目标源码 package 布局已完成；完整适配器和工具业务仍未实现 |
| T02 | `config/__init__.py`、根 `register(ctx)` 与 `tests/test_config.py`：必需配置、URL/prefix、Bearer、allowlist、嵌套 Will 默认/校验、buffer、旧 schema、凭证脱敏和 manifest 工具契约测试通过；`uv run pytest`（37 passed）、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check`、OpenSpec strict validation 通过 | — | 反馈分类：测试基础设施；T01 旧测试曾断言 manifest 不得有 `provides_tools`，与 T02 delta spec 冲突，已改为验证根入口唯一且工具声明受限；复核后补上根入口启动配置缺失回归 | T02 配置解析尚未接入后续 T18 的完整依赖组装；真实 Milky smoke 留待 T19 |
| T03 | — | — | — | — |
| T04 | — | — | — | — |
| T05 | — | — | — | — |
| T06 | — | — | — | — |
| T07 | — | — | — | — |
| T08 | — | — | — | — |
| T09 | — | — | — | — |
| T10 | — | — | — | — |
| T11 | — | — | — | — |
| T12 | — | — | — | — |
| T13 | — | — | — | — |
| T14 | — | — | — | — |
| T15 | — | — | — | — |
| T16 | — | — | — | — |
| T17（可选） | — | — | — | — |
| T18 | — | — | — | — |
| T19 | — | — | — | — |
| T20 | — | — | — | — |

## 10. Completion gates and feedback loop

- 每个任务都必须经历：契约或 fixture → 最小实现 → 单元/集成测试 → ruff/build/diff 质量门禁 → 必要的本地 Milky smoke → 反馈分类 → 最小复现和回归测试 → 修复/重构 → 重新验证。
- 反馈至少分类为协议字段/路径、Hermes API、并发/顺序、策略算法、权限/安全、媒体资源、真实环境差异或测试基础设施；每条反馈必须绑定 fixture、回归测试或可复现命令。
- T05、T06、T13 和 T16 完成后分别执行对应的最小 smoke；T19 汇总完整生命周期和受控出站验证。真实 token、个人 QQ、完整正文、媒体本地路径和不可复现状态不得写入本 change。
- 只有对应代码、自动化证据和必要的真实环境证据齐全，才能勾选任务并在未来同步/归档对应 delta spec；未完成能力继续留在 active change。
- 关键停止条件包括：无法确认 Hermes 是否成功接受 turn、无法证明 willingness 与参考实现一致、无法确认媒体安全边界或无法区分远端发送是否执行。
