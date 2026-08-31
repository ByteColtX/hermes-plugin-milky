## Why

当前实现把业务日志掩码、Tool 结果重构和插件侧媒体处理混在一起，导致实际边界不清晰。这个 change 只收敛四件事：业务日志不掩码、Tool 原样回显并记录调用信息、资源只走 Hermes core，以及仓库资料只使用合成信息。

## What Changes

- **BREAKING** 业务日志不再掩码；已注册 Tool 的日志增加调用入参和远端结果，均按收到的业务值记录，不摘要、不改名、不删除字段。
- **BREAKING** 已注册 Tool 的成功协议结果原样回显给调用方；不在插件中新增结果过滤、凭证过滤或 DTO 重构逻辑。
- **BREAKING** 删除插件侧资源下载、bytes 读取、媒体缓存、本地路径生成和 `base64://` fallback；资源只通过 Hermes core 已确认的入口处理，入口不存在时返回 `unsupported`。
- 保持源码、测试、fixture 和文档只使用合成身份、合成协议值、占位正文和占位资源，不保存 live 响应或真实私密内容。
- 本 change 不重做 HTTP/SSE 错误语义、Tool allowlist、持久化生命周期或发布回滚流程；这些已有契约保持不变。

## Capabilities

### New Capabilities

- `security-boundaries`: 定义业务日志、Tool 结果、Hermes 资源入口和仓库合成数据的边界。

### Modified Capabilities

- `system-events-and-safety`: 业务日志不掩码，并记录 Tool 调用入参和结果。
- `media-and-reply-resolution`: 禁止插件侧下载和资源 materialization。
- `outbound-messaging`: 禁止插件侧读取本地资源或生成 `base64://` fallback。

## Impact

- 运行时代码主要涉及 `milky/observability.py`、`outbound/tools.py`、`milky/resources.py` 和出站资源处理。
- 测试和 fixture 需要验证业务值不掩码、Tool 原始回显、Tool 调用日志以及 Hermes-only 资源路径。
- 实施时还需同步现有 `adapter-observability`、`plugin-lifecycle`、`ARCHITECTURE.md` 和 README 中与新日志/媒体规则冲突的描述；本 change 不修改 Hermes core。
