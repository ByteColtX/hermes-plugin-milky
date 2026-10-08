# Tasks

## 1. Hermes 目标合同与依赖声明

- [x] 1.1 将运行时直接导入的 httpx、python-multipart、Pillow 和 jieba 纳入项目运行依赖，并使 manifest 依赖声明与安装器解析结果一致；用 `uv sync`、干净依赖环境安装和目标 Hermes 依赖校验确认无缺包或多余声明。
- [x] 1.2 按指定 Hermes checkout 设置插件最低版本约束并保留 `requires_env.password` 凭证语义；用该 checkout 的 manifest validator 验证字段和版本下限，不把版本范围当作精确 commit 锁定。
- [x] 1.3 用目标安装流程验证依赖准备被拒绝或失败时插件不会以缺依赖状态启用；以安装器/插件加载测试确认原有已发布环境不会被半成品替换。
- [x] 1.4 更新 README 安装说明中的 Hermes 最低版本、依赖准备和升级要求；逐项对照指定 checkout 的安装文档与 validator 输出。

## 2. Milky Gateway 平台与 Agent 工具注册

- [ ] 2.1 在 `codex/milky-tools-entry` 分支新增根级 `tools.py` 注册入口，只暴露 manifest 声明的固定 QQ Action 与贴纸 ToolSpec；用 manifest/注册表一致性测试确认名称、数量和 schema 一一对应。当前 `main` 暂保留根入口调用作为 Hermes user-installed loader 修复前的过渡。
- [ ] 2.2 待新版入口并回 `main` 后，从根 `register(ctx)` 平台入口移除 client tool 重复注册，保持工具模块导入和注册无网络、无媒体读取、无 SSE；用 fake context 测试断言无重复工具和无连接副作用。
- [ ] 2.3 通过指定 Hermes 的 PluginManager/Gateway 验证 Milky Agent session toolset 包含 manifest 工具且各注册一次，并验证平台注册独立完成；确认工具注册不依赖 adapter 已连接，且注册过程不请求 Milky。官方第三方平台合同要求用户插件声明 `provides_tools` 并使用独立 `tools.py::register_tools(ctx)`；Milky 已遵循该合同。指定 SHA 仅在 bundled deferred platform 分支调用该 loader，user-installed platform 的实际 toolset 缺少工具。保持未完成，直到 Hermes 对官方合同的实现通过目标 Gateway toolset 实测；不得通过把 Milky 伪装为 bundled 或在 `register()` 重复登记来绕过，见 `evidence.md`。
- [x] 2.4 验证 Milky Agent toolset 中的工具只调用既有固定 operationId，并通过当前 adapter 的授权和错误边界；用工具执行测试确认未知 Action、正文触发和失败重试均不可用。

## 3. 平台注册、隔离与生命周期

- [x] 3.1 将根 `register(ctx)` 收敛为目标 Hermes 平台注册入口，并对必需的平台和 prompt 注册 API 缺失明确失败；用目标 PluginManager 与 fake context 测试确认不静默降级或走旧兼容分支。
- [x] 3.2 按平台能力要求在 `host` isolation 下报告 unsupported，在 `in_process` 下完成平台注册；通过目标 Hermes 启动测试确认 host 模式没有部分注册、连接或伪 ready 状态。
- [x] 3.3 保持首次消息开放前的登录、群列表和 Bot 群成员状态同步门槛；用连接生命周期测试确认同步未完成时普通消息和 SSE 事件不会进入处理流程。
- [x] 3.4 停止与重连时取消并等待插件任务，释放 SSE、pipeline、sender、MuteTracker 和 client；用活动任务停止及重复连接测试确认无遗留任务或重复资源。
- [x] 3.5 在 README 平台部署说明中解释 `in_process` 是 Hermes 在自身进程中运行 adapter 的隔离模式，并说明 `host` adapter 不受支持；对照目标平台指南核实术语，明确 Dashboard host proxy 不改变此要求。

## 4. Profile 配置、凭证与插件数据

- [x] 4.1 将普通设置改为按 adapter 创建时传入的 profile 配置解析，不捕获注册阶段默认配置；用 profile A/B 不同设置的测试确认各 adapter 只读取自己的值。
- [x] 4.2 通过目标 profile-aware secret/environment helper 读取 token，不从其他 profile 的进程环境回填；用双 profile 凭证测试确认隔离，并断言日志与错误结果不含凭证。
- [x] 4.3 使贴纸图库、维护任务和其他插件数据跟随 adapter 所属 profile 的数据边界；用双 profile 文件系统测试确认读写不会跨 profile。
- [x] 4.4 更新 README 配置说明中的 profile 归属与凭证行为；按双 profile 测试场景逐项核对示例和默认值。

## 5. 目标事件与普通消息映射

- [x] 5.1 将消息事件导入迁移到目标 Hermes 的公开事件模块并删除旧 import fallback；用目标事件 fixture 测试确认旧路径不再被引用。
- [x] 5.2 按目标事件字段构造已确认的 Milky DM/group 来源和 canonical 消息身份；用 DM、群聊、缺少序号及非法来源测试确认不拼造稳定 ID 或备用会话目标。
- [x] 5.3 将 `reply_expected` 映射为 true、false 或 unknown：只在身份与 mention/quote 证据充分时作确定判断；用普通私聊、已提及、未提及和不完整事件测试三态结果。
- [x] 5.4 保持普通流程只处理 `message_receive`，并按 canonical、dedup、资源补全、Gate、Will 和 Hermes turn 的既有边界处理；用 pipeline 测试确认顺序及同一 chat 串行性。
- [x] 5.5 验证 slash command 与其他非普通消息继续走各自目标入口，不被改写成普通消息；用命令、系统事件及未知事件 fixture 检查路由和副作用。

## 6. Gateway handoff 与去重状态

- [x] 6.1 保留 canonical key、缺少 `message_seq` 时不合成 ID，以及资源补全和 Will 前去重；用重复消息和副作用计数测试确认重复事件不触发后续处理。
- [x] 6.2 将活动 canonical 去重状态交给目标 Gateway adapter replacement 可继承的边界，并保留 10,000 条容量与 300 秒 TTL；用 replacement、容量和过期测试验证旧 key 与新序号行为。
- [x] 6.3 在指定 Hermes SHA 上读取普通 MessageEvent 的内部 `_gateway_accepted` receipt，且仅严格为 `True` 时分类为 Gateway accepted；用目标基类测试确认 handler 返回值不作为回执。
- [x] 6.4 将 receipt 为 `False`、字段缺失/不可读、值无法识别或 handler 异常分类为未接收/unknown 且不重提；用字段缺失 fixture 与 Gateway 集成日志断言确认无假 accepted、无重复 turn。

## 7. 系统事件与群成员即时通知

- [x] 7.1 以目标公开的 profile-scoped `inject_message(origin=...)` 路由成员即时通知，并移除 runner 私有 session resolver/store 探测；用事件测试确认 origin 来自已验证来源且不拼造 session key。
- [x] 7.2 注入前遵守当前 profile 的 `allow_gateway_injection` 和宿主来源路由检查；用同步拒绝/异常、未授权、来源不完整及宿主不可用测试确认拒绝时保留 context，且授权不扩大到 Action。
- [x] 7.3 将 `inject_message()` 的 `True` 仅分类为 scheduled，并在同步排队后 drain 一次；用目标 SHA 测试模拟排队后异步授权/路由拒绝，确认插件无法收到该拒绝、不重试、不声称 turn 成功且不承诺恢复已 drain context。
- [x] 7.4 保持成员事件开关默认关闭、非法值启动失败，并确认其他 system event 仍按原 context-only 规则工作；更新 README 配置段并用大小写、缺省、非法值及其他事件测试核对。

## 8. 媒体、视觉维护与提示指引

- [x] 8.1 通过目标 Hermes 入站媒体 helper/materialization 填充消息，并使用 Gateway 已 re-home 到当前 profile 的本地资源；用目标双 profile Gateway 测试确认插件不下载、不缓存、不复制跨 profile 文件。
- [x] 8.2 对没有当前 profile 可用本地路径的媒体保留安全占位和分类诊断；用缺失、拒绝和 malformed 结果测试确认不构造远端 URL、不泄露路径或媒体 URL。
- [x] 8.3 按目标 adapter 出站结果及 `SendResult` 契约映射发送结果，保持可能有副作用的发送最多调用一次；用失败与不确定结果测试确认不盲目重试或报告送达。
- [x] 8.4 将贴纸视觉分析切换到目标 profile-local Hermes 视觉能力，同时保留受控候选校验、元数据校验和图库提交边界；用双 profile、拒绝、超限及 malformed 结果测试确认不写入伪成功条目。
- [x] 8.5 更新 Milky prompt section 及其测试，准确表达三态回复预期、`[SILENT]` 的 core fallback 与 Milky 精确过滤边界、固定工具和 `MEDIA:`；用渲染快照确认不承诺 fallback 会投递到 QQ。

## 9. Dashboard host proxy、凭证与上传

- [ ] 9.1 使每个 Dashboard proxy 请求使用宿主确认的请求 profile 解析启用状态、配置、凭证、图库和任务；用目标 host proxy 的双 profile 请求测试确认不回退启动 profile。
- [x] 9.2 将托管凭证明确拒绝映射为 `blocked`，结果无法确认时映射为 `unknown`；用 API 与前端测试确认拒绝正文、凭证和路径不会回显，也不会误报 saved。
- [x] 9.3 保持单文件、批次、字节和暂存配额，并确保超限上传在视觉分析或图库写入前失败且不跨 profile；用合法/超限双 profile 上传测试确认各自边界。
- [ ] 9.4 更新 Dashboard 使用说明以区分非流式 API host proxy 和不支持 host isolation 的平台 adapter；用目标 proxy 接口测试核实路径、profile 选择和上传限制。

## 10. 项目事实来源与交付说明

- [x] 10.1 更新 AGENTS.md 与 `openspec/config.yaml` 中入口、工具发现、运行依赖及 profile 事实；通过检索确认不再声称根 `register(ctx)` 是唯一公开入口或 `pyproject.toml` 只服务开发。
- [x] 10.2 更新 ARCHITECTURE.md 中平台与工具入口、profile 所有权、adapter replacement、handoff receipt 和资源归属；逐项对照通过的测试与目标 Hermes API。
- [x] 10.3 校准 README 当前能力、最低 Hermes 版本、breaking migration 和验证边界；只写已由实现及测试证明的行为，并分别标明 fake host、目标 Hermes/Gateway 和真实 Milky 证据。

## 11. 目标环境集成与质量门禁

- [x] 11.1 运行受影响测试与 `uv run pytest -q`，再运行 `uv run ruff check .`、`uv run ruff format --check .` 和 `uv build`；记录通过项与明确 skip。
- [ ] 11.2 在指定 Hermes commit 上验证插件 manifest、干净依赖准备、Milky Gateway 平台注册及 Milky Agent toolset。官方第三方插件文档是 Milky 实现合同；指定 SHA 的 user-installed tool loader 实测不符合该合同，因此本项保持未完成，直到兼容实现的目标 PluginManager/Gateway 结果确认 28 个工具均可用且各注册一次；不得以 bundled 安装或源码声明代替通过结果。
- [ ] 11.3 在目标 Gateway 上验证双 profile、adapter replacement 去重、私有 receipt 缺失降为 unknown、事件注入排队与异步拒绝边界、媒体 re-home 和 Dashboard proxy；没有真实 Gateway 运行结果的项目保持 unknown。
- [x] 11.4 运行 `uv run scripts/milky_smoke.py --help`、`openspec validate --changes --strict` 与 `git diff --check`；标准验证不发送或上传消息，任何写入 smoke 继续服从显式授权和运行时 allowlist。
- [x] 11.5 在本 change 的 `evidence.md` 记录目标 Hermes SHA、实际命令、结果、skip、外部阻塞与仍 unknown 的边界；确认 fake host 证据没有被写成目标 Gateway 或真实 Milky 验证。
