# Proposal

## Why

Hermes 从 `463980c0e4c565ee6426e0be127a6da97fcb1314` 演进到 `0e37a439bda15ef3c28a4d20593964d7c6a527a6` 后，Milky Gateway 平台插件入口、client tools、profile 路由和 handoff 边界都有实际变化。本插件仍依赖旧宿主假设；只迁移单个事件 import，可能让 Milky Gateway 出现固定 QQ 工具缺失、读取错误 profile 配置或无法安全交接。

## What Changes

- **BREAKING** 保留 Hermes 原生 `plugin.yaml` 与根 `__init__.py::register(ctx)` 平台入口，同时将 manifest 声明的 outbound client tools 移到根 `tools.py::register_tools(ctx)`，由目标 Hermes 按 `provides_tools` 契约注册到 Milky Gateway Agent toolset；平台入口不重复登记这些工具。依赖 Hermes 当前的 manifest 声明和 loader，不保留旧加载方式。
- **BREAKING** 平台 adapter 明确要求 `plugins.isolation: in_process`。在 `host` 模式下由 Hermes 报告平台能力不支持；Dashboard API proxy 的 host 支持不代表 Milky adapter 可以在 host 内运行。
- 将 Hermes 平台运行依赖声明与当前安装器的依赖解析规则对齐。所有实际运行导入的包进入 `pyproject.toml` 的运行依赖并与 manifest 声明核对；目标 Hermes 版本约束作为版本下限，部署验证仍绑定用户指定的 commit。
- **BREAKING** 删除旧事件 import、私有 runner/session-store 探测和静默兼容分支。adapter 按目标 Hermes 的 profile-scoped source 与消息事件契约运行；配置、凭证和插件数据从创建 adapter 的当前 profile 解析。
- 群成员即时通知改用 Hermes 公开的 `inject_message(origin=...)` 路由，并遵守当前 profile 的 `allow_gateway_injection` 授权和宿主路由检查。同步返回 `False` 或抛错时保留事件上下文；返回 `True` 只表示请求已排入 Gateway 调度，不表示分发或 Agent turn 已被接收。排队后的异步拒绝不会回传给插件，插件不保证恢复已 drain 的上下文，也不重复创建 turn；本 change 不修改 Hermes core。
- 保持 Milky canonical 去重 key 和资源补全前判重顺序，并让 Gateway 替换 adapter 后活动去重状态延续。映射当前三态 `reply_expected`；普通消息只有目标 SHA 的进程内 admission 字段 `_gateway_accepted` 明确为 `True` 才记为 Gateway accepted，字段缺失、值非 `True` 或调用异常均为 unknown。该字段是目标 SHA 的内部实现，不是稳定插件 API；manifest 最低版本不保证未来版本仍提供它，未来目标须重新验证。
- 继续让 Hermes 拥有入站资源下载、缓存、SSRF 和 profile media re-home；核验出站结果、贴纸视觉 helper、Dashboard 托管凭证拒绝、host API proxy 和上传约束与目标 checkout 一致。
- 更新 README、ARCHITECTURE、AGENTS.md 与 OpenSpec 上下文，区分 fake host、目标 Hermes/Gateway 集成和真实 Milky 外部验证；不改 Milky v1.3 协议、QQ Action 目录、存储格式或现有安全策略。

本 change 不搬运整个 Hermes 上游区间、不修改 Hermes core，也不为旧 Hermes 版本保留双路径兼容。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `plugin-lifecycle`：原生平台注册与 client tool 注册分离；平台 host isolation 明确拒绝；安装依赖遵守目标 loader/PM 契约。
- `qq-action-tools`：固定 QQ client tools 在 Milky Gateway Agent toolset 中可用，并遵守固定 operationId 与当前 adapter 授权边界。
- `configuration`：平台配置、环境凭证和插件数据只从当前 Hermes profile 解析。
- `system-events-and-safety`：群成员即时通知用已授权、profile-scoped 的公开 origin injection；拒绝时保留 context-only 行为。
- `canonical-messages`：adapter replacement 后延续活动去重状态，同时保留稳定身份和副作用前判重边界。
- `hermes-message-pipeline`：目标消息事件的 reply expectation 与 Gateway admission receipt 语义。
- `milky-platform-prompt-guidance`：提示词遵守目标 reply expectation 与 Hermes `[SILENT]` 处理边界。
- `adapter-observability`：handoff 观测只表达有证据的 Gateway 接收状态。
- `media-and-reply-resolution`：入站 media materialization 与多 profile Gateway 的本地资源归属一致。
- `milky-web-dashboard`：托管凭证写入拒绝、profile proxy 和上传行为对齐目标宿主。
- `qq-sticker-maintenance`：视觉维护继续使用当前 profile 的 Hermes helper 与结果边界。

## Impact

影响根目录入口及新增的 `tools.py`、`plugin.yaml`、`pyproject.toml`、adapter/source mapper、profile 配置与凭证读取、系统事件注入、去重与 handoff、媒体解析、贴纸视觉调用、Dashboard API 和前端，以及 README、ARCHITECTURE、AGENTS.md、`openspec/config.yaml` 和相关测试。目标 Hermes 的主要证据面为平台插件开发指南、deferred platform tool loader、PluginContext injection、平台事件/adapter lifecycle、profile secret helper、媒体 materialization、插件依赖解析和 Dashboard host proxy。

验收覆盖插件 fake host 与单元测试、目标 Hermes Milky Gateway 插件加载/配置测试、目标 Gateway 多 profile 生命周期集成。未连接真实 Milky 服务的验证不能声称 QQ 端到端通过。
