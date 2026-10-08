# 验证证据

## 目标与证据分层

- 指定目标 Hermes SHA：`0e37a439bda15ef3c28a4d20593964d7c6a527a6`；本地目标 checkout 的 HEAD 与其一致。
- fake host、fixture 和本地插件测试证明插件边界行为，不代表目标 Hermes Gateway 或真实 Milky 已通过集成。
- 已检查目标 SHA 中的平台 tool loader、profile-scoped secret/config helper、adapter replacement 去重、message admission receipt、媒体 re-home 与 Dashboard host proxy 源码。源码核对不替代运行时集成。
- 用户提供配置后，从 OrbStack Debian 13 VM 对真实 Milky 基址执行一次只读 `POST /api/get_login_info`。仅记录 HTTP 200，响应正文被丢弃；这只能确认 endpoint 返回 HTTP 成功，不能证明 Milky envelope、凭证有效性或账号身份，仍保持 `unknown`。未连接 SSE、读取群列表或上传文件；没有发送写入类 Action、QQ 消息或文件，QQ 投递状态保持 `unknown`。

## 官方第三方插件合同与当前 Hermes 发布源码

- Hermes [用户插件指南](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins)将 `~/.hermes/plugins/platforms/` 下的平台列为 user-installed platform，并说明第三方平台通过 `plugins.enabled` 显式启用；Hermes [平台 adapter 指南](https://hermes-agent.nousresearch.com/docs/developer-guide/adding-platform-adapters)明确推荐社区/第三方平台使用插件路径、无需修改 core，并要求 `kind: platform` 的 client tools 通过 manifest `provides_tools` 和独立 `tools.py::register_tools(ctx)` 注册。该文档合同是 Milky 的实现依据。
- 截至 2026-10-08，官方 release 页面列出的最新版本为 Hermes `v0.21.5`（`v2026.9.24`）。其 [manifest gate](https://github.com/NousResearch/hermes-agent/blob/v2026.9.24/hermes_cli/plugins_discovery.py) 仅对 `manifest.source == "bundled"` 且 `kind == "platform"` 返回 deferred；user source 在 opt-in 后走普通 `load`。其 [plugin loader](https://github.com/NousResearch/hermes-agent/blob/v2026.9.24/hermes_cli/plugins_loader.py) 只在 `_register_deferred_platform()` 成功发布 deferred loader 后调用 `_register_deferred_platform_tools()`。因此此 release 的 user-installed platform `provides_tools` 路径与官方文档不一致。此处是官方源码静态核对，不代替 VM/Gateway 运行验证。
- Milky 保持第三方 `kind: platform`、`provides_tools` 和 `tools.py::register_tools(ctx)` 布局；不把插件改成 bundled，也不在平台 `register(ctx)` 中重复登记 tools。对照官方合同后，剩余缺陷归属于 Hermes host 的 user-installed platform loader；在实际 Agent session toolset 验证通过前，任务 2.3 和 11.2 仍未完成。`requires_hermes` 版本下限不是某个 commit 的兼容性保证。

## 社区已知问题与跟踪状态

- Hermes 社区此前已经报告同一类 deferred platform client-tool 缺失：[#78050](https://github.com/NousResearch/hermes-agent/issues/78050) 和 [#81163](https://github.com/NousResearch/hermes-agent/issues/81163) 记录平台插件的 outbound tools 没有进入 CLI/TUI 或 agent catalog；[#86660](https://github.com/NousResearch/hermes-agent/pull/86660) 于 2026-08-15 合并，修复 bundled deferred platform 的 `provides_tools` 预注册、工具集配置过滤和 `hermes tools --platform` 识别。这解释了为什么官方文档合同和 bundled 示例看起来已经可用，但不能把该修复当作 user-installed Milky 已通过。
- 截至 2026-10-08，开放的 [#111643](https://github.com/NousResearch/hermes-agent/issues/111643) 与 [#111669](https://github.com/NousResearch/hermes-agent/pull/111669) 正在跟踪第三方 platform 的 discovery/deferred 生命周期；它们的范围是让第三方 adapter 在非 Gateway 进程延迟、在 Gateway 启动时及时加载。两项都没有提供 Milky 在目标 `0e37a439bda15ef3c28a4d20593964d7c6a527a6` 上 28 个工具各注册一次的结果，且不能替代本项目的目标 Gateway 验证。
- 2026-10-09 重新读取官方平台适配器指南和 GitHub `main`（`38880bd2f1e90dbc9a1aeec03af62539ee64719a`）：指南仍明确要求第三方 `kind: platform` 插件使用 `provides_tools` 与独立 `tools.py::register_tools(ctx)`，并将 adapter 保持 deferred；该 `main` 的 `gate_manifest()` 仍只对 `source == "bundled"` 的 platform 返回 `defer`，`_register_deferred_platform_tools()` 也只从该分支调用。最新 `main` 的源码状态仍不能证明 user-installed Milky 的 28 个工具会进入 Agent toolset，因此不改变 2.3/11.2 的未完成结论。
- 本项目的 OrbStack Debian 13 复现与上述问题相符，但安装来源是 user plugin：目标 SHA 的 `gate_manifest()` 只对 bundled platform 返回 `defer`，`_register_deferred_platform_tools()` 只从该分支调用；因此 user source 进入 eager `register()` 后仍不会自动调用独立 `tools.py`。当前跟踪结论是“上游已有同类修复和开放的第三方生命周期改进，但 Milky 所需的 user-installed client-tool loader 仍未被上游结果关闭”；在兼容 loader 和 28-tool session toolset 实测前，2.3/11.2 保持未完成。

## 插件与本地 Dashboard 验证

| 命令 | 结果 |
|---|---|
| `UV_CACHE_DIR=<temporary> uv run pytest -q` | 通过：1446 passed，5 skipped。运行完整套件时允许本机回环 HTTP/SSE fixture 绑定临时端口；未访问外部服务。 |
| `UV_CACHE_DIR=<temporary> uv run pytest -q -rs` | 通过：1446 passed，5 skipped。skip 原因为当前测试环境没有 Hermes host/目标 checkout，或真实 Hermes prompt 集成未显式启用。 |
| 入口、tool manifest、adapter lifecycle、pipeline、profile 隔离、Dashboard、prompt 与媒体聚焦测试 | 通过：126 passed，4 skipped；fake host 和 fixture 证据。 |
| Dashboard profile scope 与双 profile 上传边界测试 | 通过：19 passed；fake host/本地存储测试，覆盖独立 profile 根、各自暂存配额及超限清理。 |
| `tests/test_dashboard_settings.py` | 通过：13 passed；覆盖托管拒绝 `blocked`、其他未确认写入 `unknown`、凭证和拒绝详情脱敏。 |
| `npm test --prefix dashboard` | 通过：4 passed。 |
| `npm run build --prefix dashboard` | 通过；更新了预构建 Dashboard 资源。 |
| `UV_CACHE_DIR=<temporary> uv run ruff check .` | 通过。 |
| `UV_CACHE_DIR=<temporary> uv run ruff format --check .` | 通过：615 个文件已格式化。 |
| `UV_CACHE_DIR=<temporary> uv run scripts/milky_smoke.py --help` | 通过；只显示帮助，没有连接或写入。 |
| `openspec validate migrate-hermes-main-platform-contract --strict` | 通过：本 change 有效。 |
| `git diff --check` | 通过。 |

完整套件的 5 个 skip 分别是：adapter 生命周期的 Hermes host / target checkout 检查 2 项、Hermes pipeline target checkout 检查 1 项、需 `RUN_HERMES_INTEGRATION=1` 的 prompt 集成 1 项，以及当前环境不可用的 Hermes host 多媒体发送检查 1 项。

全仓 `openspec validate --changes --strict` 未通过：本 change 被列为有效；另有既存 `add-group-moderation-workflow` 的长 requirement 警告，以及 `fix-httpx-cross-event-loop-reuse` 缺少 delta 的错误。本次未修改这两个无关 change。

## 构建限制

- 标准 `uv build` 尝试失败：隔离构建需要 `setuptools>=75`，当前缓存没有该依赖，运行环境无法访问 PyPI。
- 离线 `uv build --no-build-isolation` 也未完成：当前项目环境没有 setuptools。未安装构建依赖或更改项目依赖来绕过环境限制；wheel/sdist 构建状态仍未确认。

## 目标 Hermes / Gateway 状态

- 目标 Hermes 在 OrbStack Debian 13.7 Trixie ARM64 VM 中安装并运行，版本 `v0.21.5+8508.g0e37a43`，checkout SHA 为 `0e37a439bda15ef3c28a4d20593964d7c6a527a6`。验证 home 与其他 Hermes 安装隔离；Milky 插件仅在该验证 profile 启用，`hermes plugins enable hermes-plugin-milky --no-allow-tool-override` 的 PM 依赖解析和安装均成功。
- 此前一次 validator 探索在包含 Dashboard 合成探针的副本上报告 `hardcoded_secret`；本轮排除测试/脚本的干净副本复验已返回 `ok: true`，详见下方 2026-10-08 结果。该 validator 仍只探测根 `register()`，不统计独立 `tools.py`。
- 启用插件后的 `hermes plugins doctor --ci <installed plugin>` 以 exit 0 通过 import 和 `register()` 检查，但报告 0 tool(s)，并警告 manifest 声明的 28 个工具没有由 `register()` 注册；Doctor 不验证独立 `tools.py` loader。
- 在 Hermes 原生 runtime 执行 `PluginManager.discover_and_load()` 后，用户安装来源的 Milky platform 已启用、无加载错误且平台注册存在；但 `_predeclared_tools` 与插件 tool registry 均为空，`resolve_toolset("milky")` 也没有 manifest 中的 28 个工具。目标 SHA 的 `gate_manifest()` 只把 bundled platform 设为 deferred，而 `_register_deferred_platform_tools()` 只从该分支调用；user-source platform 走 eager `register()`，没有触发 `tools.py`。
- Hermes[第三方平台指南](https://hermes-agent.nousresearch.com/docs/developer-guide/adding-platform-adapters)要求社区平台用 plugin 路径，不修改 Hermes core；对声明 `provides_tools` 的 platform，指南要求使用独立 `tools.py::register_tools(ctx)`，由 discovery 注册工具并保持 adapter deferred。目标 SHA 的[插件发现源码](https://github.com/NousResearch/hermes-agent/blob/0e37a439bda15ef3c28a4d20593964d7c6a527a6/hermes_cli/plugins_discovery.py)则只在 `manifest.source == "bundled"` 且 `kind == "platform"` 时返回 deferred，普通 user source 走 eager load；[目标 loader](https://github.com/NousResearch/hermes-agent/blob/0e37a439bda15ef3c28a4d20593964d7c6a527a6/hermes_cli/plugins_loader.py)仅在 deferred 注册成功后调用 `_register_deferred_platform_tools()`。因此 11.2 的差异来自指定宿主 SHA 的 loader，不是 Milky 应安装为 bundled plugin；本项目保留官方第三方插件结构，不修改或 monkey patch Hermes core。
- 用户提供的真实 Milky 配置只用于上文那次只读登录信息请求；完整 `scripts/milky_smoke.py` 未能在 Hermes 运行时执行。宿主环境缺少 Hermes host APIs，VM 的备用系统 Python 缺少 `ruamel.yaml`；这些 smoke 尝试均在网络请求前返回 `invalid_input`。已记录的 HTTP 200 来自单独的原始 HTTP 请求，不代表插件客户端或 Gateway 集成通过。
- `scripts/milky_media_profile_integration.py` 在 Hermes 原生 runtime 中通过：真实目标 helper 只接收本地合成 fixture；Gateway 将资源 re-home 到第二 profile 并从启动 profile 移除。未发起网络请求。8.1 已完成。
- `scripts/dashboard_host_probe.py` 在目标 Hermes ASGI 应用中通过：认证、静态资源、并发双 profile 配置和凭证隔离、伪造 profile 拒绝、插件禁用和路由生命周期检查均为 true。探针使用合成插件，证明通用 host proxy 行为，不证明 Milky API 联调。
- `scripts/dashboard_plugin_probe.py` 的早期尝试因隔离 home 缺少 `jieba` 未能执行；后续复验复用 PM 发布的依赖环境并通过 22 项 Milky API 检查。复验使用默认 `in_process`，不证明 `plugins.isolation: host` 的 Milky proxy，因此 9.1、9.4 仍为 `unknown`。
- 本轮没有启动常驻 Gateway 或创建 `MilkyClient`；除上述一次只读登录信息 HTTP 请求外，没有运行真实 Milky SSE、群列表、成员同步、媒体或 QQ 投递。不把合成 Gateway 结果写成真实 Milky 投递结果。
- 不把单次 HTTP 200 当作真实 Hermes Gateway 或完整 Milky 集成通过的证据。

## 2026-10-08 OrbStack Debian 13 复验

- OrbStack `milky-hermes-debian13` 当前运行于 Debian 13.7 Trixie ARM64；Hermes `v0.21.5+8508.g0e37a43` 的 checkout HEAD 为指定 SHA `0e37a439bda15ef3c28a4d20593964d7c6a527a6`。
- 当前工作区插件副本放在一次性 `HERMES_HOME=/tmp/hermes-milky-validation-20261008`，复制时排除 `.git`、开发环境、缓存、测试、`.env*` 和凭证文件。该路径已在收集结果后删除；`/home/bytecolt/.hermes` 的日常插件和配置未改动。
- `hermes plugins validate --json --install-deps <临时插件目录>` 退出码为 0、返回 `ok: true`：manifest、最低 Hermes 版本、配置 schema、凭证声明、四项运行依赖、capability probe、安全扫描及 core override 检查均通过。validator 仅检查 `register()`，因此同时警告 28 个 `provides_tools` 未由该函数注册；这不代表它加载或检查了独立 `tools.py`。
- `hermes plugins enable hermes-plugin-milky --no-allow-tool-override` 在临时 home 中启用为 `platforms/hermes-plugin-milky`，PM 依赖解析与发布成功。`hermes plugins doctor --ci <临时插件目录>` 退出码为 0、入口导入和 `register()` 通过，但报告 0 个 plugin tool，并对 manifest 的 28 项全部给出未注册警告。
- 在目标 Hermes 原生 Python runtime 调用 `PluginManager.discover_and_load()`：user-source 插件 `enabled=True`、`error=False`，`milky` 平台注册集合恰有 1 项；manifest 声明 28 个工具，插件已注册 0 个、deferred pre-registration 为 0 个，28 项均缺失。`resolve_toolset("hermes-milky")` 的结果只有 Hermes core 工具，Milky 插件扩展为 0；`resolve_toolset("milky")` 也为空。运行没有构造 adapter、创建 Gateway 或请求 Milky。
- 同一 VM 的 discovery 源码核对结果一致：`gate_manifest()` 只把 bundled platform 设为 deferred；`_register_deferred_platform_tools()` 只在该 deferred 分支调用。user-source platform 进入 eager `register()`，不会调用 `tools.py::register_tools(ctx)`。这复现了官方第三方平台指南与指定 Hermes SHA loader 的差异；Milky 仍保持官方 user-plugin 路径和工具分离，不改为 bundled，也不在平台 `register()` 重复登记。
- 为恢复先前失败的 Milky Dashboard API 探针，在 VM 临时副本中修正探针的导入顺序和可重复创建目录处理，并通过真实 Hermes ASGI app 执行合成 profile、凭证、图库、上传与维护场景；22 项断言均为 `true`。该探针配置没有设置 `plugins.isolation: host`，因此验证的是默认 `in_process` API 路径，不是宿主代理路径，不能完成 9.1 或 9.4。通用 `dashboard_host_probe.py` 的合成插件 host-proxy 结果仍只是宿主能力证据，不等于 Milky host 联调。
- 复用目标 checkout 的已发布依赖环境，并设置 `HERMES_DISABLE_LAZY_INSTALLS=1` 避免临时 home 触发整套依赖重建后，`plugins.isolation: host` 的 Dashboard 探针可通过 22 项断言；但只有增加临时 flat Dashboard alias（`plugins/<name>/dashboard`）时才挂载 Milky API。按官方第三方 platform 的原生安装位置 `plugins/platforms/<name>` 运行时，manifest 未被 Dashboard scanner 发现，`GET /api/plugins/hermes-plugin-milky/config` 返回 404，未执行 proxy 双 profile、上传和限制断言。该差异属于目标 Hermes Dashboard discovery 路径，不通过修改 Milky 成为 bundled 或伪造安装路径绕过；9.1、9.4 继续 `unknown`。
- 新增 `scripts/hermes_gateway_milky_probe.py`，在目标 Hermes SHA 的 Gateway API 上使用合成 profile 和凭证运行；命令使用目标 checkout 的 venv、已发布 Milky 依赖环境和 `--plugin-dependency-home`，没有网络请求。结果为 `status=passed`：`profile_config_isolated`、`gateway_profile_routing`、`adapter_replacement_dedup`、`receipt_missing_unknown`、`async_injection_rejection_not_visible`、`cross_profile_injection_refused`、`platform_registry_profile_scoped` 和 `replacement_adapter_unused` 均为 true。该结果只覆盖目标 Gateway 的合成边界；媒体 re-home 已由独立 helper probe 通过，Dashboard 原生 host proxy 仍被上述 discovery 404 阻塞，因此 11.3 保持未完成。
- in-process 探针复验时 Hermes 临时依赖更新曾因 `/tmp` 空间不足中止，但复用已发布依赖环境后 22 项断言仍通过。完成后已删除本轮创建的临时验证目录，VM `/tmp` 可用空间恢复到 2.5 GiB。没有启动常驻 Gateway、创建 Milky client、打开 SSE 或发送 QQ 消息；本轮未访问 Milky 服务。
- 因此 2.3 与 11.2 继续未完成，直到目标 Hermes 对官方第三方 `provides_tools` 合同的兼容 loader 将 28 个工具加载进 Milky Agent session toolset；9.1、9.4 仍需目标 Dashboard scanner 支持官方 platform 安装位置后的 Milky proxy 联测；11.3 已取得 Gateway 合成边界证据，但仍缺原生 Dashboard proxy，保持未完成。

## 尚未验证的任务

- 9.1、9.4：目标 Hermes Dashboard scanner 不发现官方 `plugins/platforms/<name>` 下的 Dashboard manifest；flat alias 下的通过结果不能替代原生路径联调。
- 11.2：Milky 符合官方第三方 platform `provides_tools`/`tools.py` 架构，但目标 SHA 只为 bundled deferred platform 调用工具 loader；user-installed platform 的 Milky Agent session toolset 缺少 manifest tools。
- 11.3：Gateway 合成 profile、replacement、receipt 和 injection 边界已通过；原生 Dashboard host proxy discovery 仍阻塞完整验收。
