# Design

## Context

动机和外部行为见 proposal.md；行为验收见本 change 的 11 份 delta specs。平台插件的公开合同以 Hermes 官方第三方平台文档为准；用户指定的 Hermes commit `0e37a439bda15ef3c28a4d20593964d7c6a527a6` 是兼容性实测基线，不能用该版本与文档不一致的实现覆盖公开合同。

平台 client tools 的设计遵循 Hermes 官方社区/第三方平台插件指南：manifest 声明 `kind: platform` 与 `provides_tools`，固定工具放在 `tools.py::register_tools(ctx)`，不要求把 Milky 并入 Hermes bundled plugins。指定目标 SHA 的 PluginManager 与 Gateway 实测确认，用户安装来源的平台注册成功，但 `tools.py` 没有进入工具注册表，Agent tool registry 和 `resolve_toolset("milky")` 都为空。

当前 `main` 暂保留旧的根入口调用 `outbound.tools::register_tools(ctx)`，确保目标 user-installed loader 不支持独立入口时仍能登记固定工具；官方独立入口和不重复注册的平台入口保存在 `codex/milky-tools-entry` 分支，待 Hermes core 修复后再合并。这个过渡不改变第三方插件的 manifest 合同，也不修改 Hermes core。

目标 SHA 的 loader 源码解释了差异：`gate_manifest()` 只对 `manifest.source == "bundled"` 的 platform 返回 deferred；user 来源 platform 进入普通 eager `register()` 路径。`_register_deferred_platform_tools()` 只从 deferred bundled loader 调用，因此目标 SHA 没有履行官方文档对第三方 platform `provides_tools` 的承诺。这不是 Milky 应安装成 bundled plugin 的理由，也不是插件目录布局问题；本项目继续保持第三方插件结构，不修改 Hermes core。目标 host 的 Agent toolset 集成仍未通过，见 `evidence.md` 与未完成任务 2.3、11.2。

其余初始接缝包括：manifest 已声明 `provides_tools`，插件根目录没有专用 `tools.py`；`pyproject.toml` 运行依赖只有 Pillow 与 jieba，实际导入的 httpx 和 Dashboard multipart parser 仍在 dev 依赖，而目标依赖解析会优先使用项目的 `project.dependencies`；当前 `register()` 把一次读取的配置闭包交给所有 adapter 实例，多 profile 下不能据此假定配置属于创建 adapter 的 profile。

此外，adapter 仍有目标版本之前的 MessageEvent 导入/测试 fallback，成员事件注入可探测 runner 私有 session resolver 和 session store，canonical TTL map 由插件单独持有；这些都需要依据目标公开 API 与 replacement 行为迁移。项目根 AGENTS.md 和 `openspec/config.yaml` 将根 `register(ctx)` 描述为唯一公开入口、把 pyproject 仅定位为开发工具，也必须与目标加载和依赖事实同步。

目标证据以 checkout 内平台 adapter 开发指南、deferred platform tools loader、插件上下文注入契约、平台事件和 Gateway 基类、profile secret helpers、media helper 与 Dashboard proxy 为准。平台指南保留原生 `plugin.yaml` 和根 `register(ctx)` 入口；client tools 另由 manifest opt-in 并从专用 `tools.py` 注册。目标文档明确平台 adapter 需要 `plugins.isolation: in_process`。

## Goals / Non-Goals

**Goals:**

- 分离平台 adapter 注册与 manifest 声明的 Milky Gateway Agent client tools 注册。
- 每个 adapter 使用 Hermes 创建它时对应的 profile 配置、凭证、session origin 和插件数据。
- 保留 Milky canonical identity、Gate/Will、顺序、资源和安全语义，同时遵循目标 Gateway 的 adapter replacement、reply expectation 和接收回执。
- 逐模块证明目标 checkout 中的插件加载、依赖、profile、媒体、注入和 Dashboard 契约；把缺少真实宿主运行的部分保留为未验证。

**Non-Goals:**

- 不在 Milky 插件中复刻 plugin manager、profile multiplexer、Gateway busy queue、session store、media re-home 或 Dashboard authentication。
- 不迁移与 Milky 直接集成无关的 Hermes 上游改动。
- 不改变 Milky v1.3 Action/SSE 协议、QQ Action 目录、状态存储格式或现有授权策略。
- 不恢复旧 Hermes import、私有 runner/session API、旧依赖声明路径或旧版宿主 fallback。

## Decisions

### 平台注册与 client tool 注册分开

目标形态保留根 `__init__.py::register(ctx)` 作为第三方 native platform 注册路径，并由根 `tools.py::register_tools(ctx)` 仅登记 `outbound.tools` 已定义的固定 ToolSpec；`plugin.yaml::provides_tools` 继续列出它们。这与 Hermes 官方平台插件指南一致。当前 `main` 暂由根 `register(ctx)` 调用同一固定工具注册函数，独立入口在 `codex/milky-tools-entry` 分支，待 loader 修复后合并。根包导入和工具导入都不得创建 client、登录、连接 SSE、读媒体或启动后台任务。不得为通过目标验证而将第三方插件伪装为 bundled plugin，或修改/monkey patch Hermes core。

用目标 `PluginManager` 和 Gateway 从隔离 Hermes home 加载插件，验证 manifest 声明的固定工具进入 Milky Agent session toolset 且各注册一次，并验证平台 adapter 注册独立完成；仅调用项目 fake context 不足以证明目标 loader 合同。若注册失败，目标验证需识别缺少或未注册的 manifest tool，不把 warning 当作能力已经存在。

替代方案：继续在 `register(ctx)` 中同时登记工具。目标 platform plugin 契约将 adapter 注册与 client tool 注册分开；混在一起会在 Milky adapter 物化时造成重复登记，因此不采用。

### 严格采用目标 Hermes 的平台和依赖合同

`register_platform`、system prompt section 和目标版本保证的必要能力必须真实存在；不再用 `getattr` 将其缺失解释成成功。optional command、skill 等能力按目标 API 的明确可选语义单独判断。adapter host isolation 由 Hermes 报告 unsupported；不由插件模拟一个 host adapter。

manifest 增加目标版本下限，并保持 Hermes 平台文档要求的 `requires_env.password` token 标记。运行依赖以目标安装器对项目 `pyproject.toml` 的解析结果为准；把直接运行导入的 httpx、python-multipart、Pillow 和 jieba 列入 `project.dependencies`，并核对 manifest `python_dependencies` 与之同集。httpx 与 multipart 分别覆盖 Milky HTTP/SSE 和 Dashboard upload 运行路径。锁定的目标 canary commit 记入集成矩阵；`requires_hermes` 只能表达版本范围，不能替代 commit pin。

替代方案：仅修 manifest 的包列表，继续把实际运行依赖留在 dev group。开发环境测试会通过，但干净插件环境缺少包；因此以 target PM 解析的运行集合做安装验证。

### 按 adapter profile 构造配置和来源

注册阶段只创建无网络的 adapter factory。adapter 构造时以 Hermes 传入的 `PlatformConfig` 和目标公开的 profile-aware secret/environment helper 解析 token 与普通设置；不捕获一次性的默认 profile `MilkyConfig`，不从另一个 profile 的进程环境回填。插件图库和任务目录通过当前 profile 的插件数据边界解析。

Session source 使用目标 `gateway.platforms.event` 与 platform adapter 合同提供的字段；插件不拼造 Gateway session key，不读取 runner 私有字段。群成员即时通知调用 `PluginContext.inject_message` 的公开 `origin` 路径，让当前 profile 的 Gateway 尝试建立或继续来源会话。同步返回 `False`、抛错或来源/授权预检失败时保留 system context；返回 `True` 只确认请求已排入调度。Gateway 随后还会重新检查授权和 adapter 路由，异步拒绝或实际 ingress admission 结果不会回传给插件；Gateway 可在自己的失败路径中记录诊断，但插件没有完成回执。目标 SHA 的 origin dispatcher 也不把传入 MessageEvent 的 `_gateway_accepted` 字段转交给注入调用方。插件在 `True` 后 drain 已排队内容，因此不承诺排队后的失败仍可恢复上下文，也不得把 `True` 记录为 Agent turn 已接收或完成；不改 Hermes core。注入授权不改变 Milky allowlist、Action 授权或普通消息 Gate/Will。

替代方案：保留 `async_session_store` 枚举或 `_session_key_for_source` 推导。它们不是插件合同，且跨版本或 profile 调度会失配；不保留。

### 保持 canonical 去重并继承 Gateway adapter replacement 状态

保留 canonical key `milky:<self_id>:<chat_key>:<message_seq>`、不合成缺失序号，以及 canonical/dedup 先于资源、Will 和 handoff 的顺序。用目标 Gateway 可继承的 `MessageDeduplicator` 作为活动缓存持有边界，并明确容量与 TTL 对齐现有的 10,000 条和 300 秒行为。replacement 测试需证明同一 key 在新 adapter 上仍被判重，而新序号和 TTL 过期消息仍被处理。该缓存仍为进程内状态，不扩展为重启持久化。

目标基类已有通用 redelivery 去重时，测试其 key 语义不会替代 Milky canonical 去重，也不会先执行资源或 Will 副作用；否则只使用目标 replacement 机制继承插件的 canonical helper 状态。

### 按目标事件和 Gateway 交接语义映射消息

事件类型从 `gateway.platforms.event` 导入。mapper 根据已确认的 Milky 私聊/群聊身份与 mention/quote 信息设置 `reply_expected` 的 `true`、`false` 或 `None`：普通私聊为 expected；群聊只有能证明指向 Bot 时才 expected，能证明未指向 Bot 时 not expected，其余 unknown。slash command 和非普通消息继续走各自既有路径。

`BasePlatformAdapter.handle_message` 返回 `None`，不能据其正常返回推断 Gateway 接收。目标 SHA 将普通 MessageEvent 的进程内 admission receipt 放在私有字段 `MessageEvent._gateway_accepted`；Milky 仅当该字段严格为 `True` 时记 Gateway accepted，字段为 `False`、缺失、无法读取或 handler 抛错时记 unknown/失败，不重试可能已有副作用的 trigger。此字段是目标 SHA 的内部实现而非稳定插件 API；`requires_hermes` 的版本下限不保证未来 Hermes 继续提供它，若未来版本移除字段则 handoff 只能保持 unknown，并须重新验证该版本。receipt 只表示 Gateway admission/排队，不表示 Agent turn 完成或 QQ delivery。`[SILENT]` 的处理由 Hermes core 按 reply expectation 决定：false 时保持静默，true/unknown 时生成固定 fallback；Milky 在 QQ 发送前精确过滤该 fallback，因此可能没有 QQ 消息，而 Gateway 仍可能按 `success` 结果记录 delivered。提示文案必须说明这段交付边界，不承诺 fallback 会显示在 QQ。

### 保持资源和 Dashboard 的宿主所有权

入站媒体只通过 Hermes 当前 helper/materialization 进入 MessageEvent。profile re-home 由 Gateway 完成；插件仅使用当前 profile 可访问的结果，不移动文件或自建缓存。出站结果和 `SendResult` 按目标基类契约映射，并保留一次 Action/发送边界。

贴纸视觉维护继续由 Hermes 当前视觉 helper 执行，输入和结果仍经插件现有候选筛选、字段校验与提交流程；不得因上游 helper 重组而绕过路径检查或改动图库事务。

Dashboard host proxy 和平台 adapter isolation 分开处理。API 每个请求采用宿主确认的 profile；profile secret、图库、任务和上传暂存跟随该 profile。托管 `.env` 的明确拒绝映射 `blocked`，不确定持久化状态映射 `unknown`。保持现有单文件、批次、字节和暂存配额，不把 host proxy 宣称为 streaming API，也不把它当作平台 adapter host 支持。

替代方案：由插件读取 raw process env、重建下载缓存或直接写托管 `.env`。这会绕开 profile/secret/media owner，因此不采用。

### 更新项目事实来源与验证证据

同步 AGENTS.md 和 `openspec/config.yaml` 中入口、依赖来源、工具路径描述；README 说明目标 Hermes 下限和 in-process 部署；ARCHITECTURE 记录当前入口、profile、Gateway handoff 与状态 owner。只在实现和目标验证通过后更新当前能力文案。验证分为 fake/unit、目标 Hermes loader/config、真实目标 Gateway multi-profile 三层；外部 Milky 登录/发送保持单独的授权 smoke，不列作默认自动化门禁。

## Risks / Trade-offs

- **Manifest 版本下限无法精确锁定目标 canary commit。** → 目标 checkout SHA 保存在集成矩阵和部署说明；兼容范围只以 Hermes 自身可解析的版本下限表达。
- **成员事件注入在排队后仍可能异步失败。** → 公开 API 只回传同步调度结果，后续失败不能由插件观察；同步拒绝保留上下文，排队后不承诺恢复、不重试，并将日志分类为 scheduled 而非 Agent turn accepted。若要保证异步拒绝后恢复，需另行修改 Hermes API/core。
- **普通消息 admission receipt 是目标 SHA 的私有进程内字段。** → 只对指定 SHA 验收，严格仅在 `_gateway_accepted is True` 时记 accepted；字段缺失或不明确一律 unknown。未来 Hermes 版本即使满足最低版本，也须重新验证此字段和语义。
- **注册工具失败可能导致目标 loader 仍保留部分登记结果。** → 工具模块在登记前完成静态 schema 与 manifest 名称核对；目标 `plugins validate`/PluginManager 测试覆盖完整数量、重复和缺项。
- **profile 环境/凭证需在 adapter factory 的作用域中读取。** → 两个真实 Gateway profile 分别使用不同 token、图库和 session origin；fake context 不作为此项通过证据。
- **Gateway receipt、replacement 和媒体 re-home 依赖真实宿主调度。** → 单元测试只覆盖插件边界；必须单独执行目标 Gateway 集成，未执行则在 evidence 中标 `unknown`。
- **host Dashboard proxy 支持可能被误读为 host adapter 支持。** → 独立运行 Dashboard proxy 与平台启动用例，并在 README 说明 `in_process` 要求。
- **尚未连接真实 Milky 服务。** → 本变更不以真实 QQ 投递为默认验收；发送或上传 smoke 仍受用户显式授权、`--allow-write` 与运行时 allowlist 限制。

## Migration Plan

1. 按目标 Hermes 文档与源码完成入口、工具、依赖和 profile factory 迁移；运行插件 validator，并在 Milky Gateway 验证 Agent toolset 与平台注册。
2. 迁移事件/source、public origin injection、reply expectation、admission receipt、canonical dedup replacement 与 adapter lifecycle；组内完成 mapper、system event 和 Gateway 的测试。
3. 迁移 profile media、出站结果、视觉 helper 和 Dashboard proxy/credential 处理；组内完成隔离 host 与 profile 测试及文档。
4. 更新 README、ARCHITECTURE、AGENTS.md 和 OpenSpec context，并核对所有当前能力描述有实现/测试证据。
5. 在指定 Hermes checkout 跑真实 Gateway 集成和插件质量门禁；部署只使用经验证的目标 Hermes commit。回滚通过恢复配套的插件版本与 Hermes checkout 完成，不在新代码里保留旧运行路径。

## Open Questions

无。用户已指定目标 Hermes commit，并确认以 Hermes 官方指导为准且不考虑旧兼容。`requires_hermes` 的版本下限不表示精确 commit pin；具体版本标识以目标 checkout 的读取结果写入验证矩阵。
