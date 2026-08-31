## Context

本 change 只处理已确认的四条边界。当前代码中，观测层会掩码部分业务标识，Tool 层会重新组织远端结果，资源和出站代码仍包含本地读取、URL 转 bytes 或 `base64://` 方向的路径。项目已有 HTTP、SSE、Action allowlist 和生命周期契约，不在本 change 重新设计。

## Goals / Non-Goals

**Goals:**

- 保留日志中允许观察的业务值，不再通过通用掩码改写业务 ID、chat key、message ID、昵称或 Tool 业务数据。
- 对已注册 Tool 同时记录调用入参和远端结果，并把成功远端结果原样交付当前调用方。
- 删除插件侧资源下载、bytes 读取、缓存、路径拼接和 `base64://` fallback，只调用已经确认的 Hermes core 资源入口。
- 让源码、测试、fixture 和文档使用合成数据。

**Non-Goals:**

- 不新增凭证过滤器、通用脱敏器、数据分类类型或新的日志框架。认证 header 不作为 Tool 入参或 Tool 结果传入日志调用点。
- 不修改 HTTP/SSE 的错误分类、重试、重连和取消语义。
- 不修改 Tool allowlist、Action 授权模型、插件持久化模型、Hermes core 或 `pii_safe` 等宿主元数据。
- 不提前发明通用 Hermes media seam；未确认入口时只保留 `unsupported` 行为。

## Decisions

### 1. 日志只移除业务掩码，不建设新的过滤层

现有日志调用点中，业务关联字段直接保留原始值。已注册 Tool 使用专用调用日志记录 Tool 名称、调用入参和远端结果；这些字段不做摘要、改名、脱敏或未知字段过滤。认证 header 和 HTTP transport 上下文不是 Tool 入参/结果，调用点不把它们传入日志。

这样直接满足业务可观察性要求，也避免为了一个日志变化引入全局字段注册表或凭证扫描器。普通错误仍沿用现有固定错误分类和既有日志契约，不在本 change 扩展异常输出。

### 2. Tool 原始结果只做边界转发

合法已注册 Tool 收到远端成功结果后，调用方获得原始协议 envelope 和未知字段；插件不重新构造 DTO、不摘要、不改名、不删除字段。日志记录同一次调用的入参和结果，避免把 Tool 结果误当成插件状态或协议诊断。

参数错误、未注册 Action 和无远端响应的传输错误继续使用已有错误结果，不伪造远端结果。若远端结果包含业务扩展字段，插件不在 Tool 结果面修改它。

### 3. 资源处理只接入已确认的 Hermes core 入口

trigger 或出站阶段只把经过 Milky 协议校验的引用交给已确认的 Hermes core 入口。插件不下载 URL、不读取远端 bytes、不读取本地文件、不创建缓存或目录、不拼接 Hermes 路径，也不生成 `base64://` fallback。没有可确认的入口时返回 `unsupported` 并保留既有正文/占位。

实现阶段先以 Hermes 源码或已存在的 fake contract 确认具体入口，再针对该入口编写测试；不能先设计一个抽象 seam 再让实现适配它。

### 4. 仓库只验证合成资料

测试 helper 和 fixture 固定使用合成身份、保留协议字段形状的合成值、占位正文和占位资源。仓库检查覆盖源码、测试、fixture 和文档即可；不把运行时日志、CI artifact、未跟踪目录或提交历史变成插件运行契约。

## Risks / Trade-offs

- **[业务日志可见信息更多]** → 这是有意行为；不增加掩码层，使用现有日志访问和留存管理。
- **[Tool 结果或日志内容较大]** → 保留原始业务结果是明确要求；只复用现有日志调用机制，不引入新的摘要或截断规则。
- **[Hermes 入口尚未确认]** → 在确认前返回 `unsupported`，不以插件侧下载或 base64 fallback 补齐能力。
- **[已有主 spec 和文档仍有旧掩码/base64 描述]** → 在实施任务中同步 `adapter-observability`、`plugin-lifecycle`、`ARCHITECTURE.md` 和 README；未同步前不宣称变更完成。

## Migration Plan

1. 先补合成 fixture 和 Tool/日志行为测试，并确认 Hermes 实际资源入口。
2. 移除业务掩码，加入 Tool 入参和结果日志，保持现有 Tool allowlist 与错误处理。
3. 删除插件侧资源读取、下载、缓存、路径和 base64 fallback；无入口时固定返回 `unsupported`。
4. 同步冲突的主 spec、`ARCHITECTURE.md` 和 README，再运行相关测试和质量门禁。

回滚使用上一个代码版本即可；不得通过回滚重新引入插件侧资源下载或本 change 删除的 Tool DTO 重构。

## Open Questions

- Hermes core 当前具体入站/出站资源入口需要在实施阶段通过源码或现有测试 contract 确认；未确认前不实现该能力。
