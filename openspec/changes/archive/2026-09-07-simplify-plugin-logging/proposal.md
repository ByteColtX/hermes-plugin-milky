## Why

插件当前维护了一套独立的安全日志边界：敏感字段白名单、异常内容检查、固定事件渲染和后台日志提交。Hermes core 已经提供统一的日志脱敏、文件路由和异步队列，但原计划同时删除了固定的运维事件和请求结果字段，会削弱排查 Action 失败、慢端点、SSE 重连和入站决策的能力。

本 change 改为只删除插件私有的安全日志实现，保留一套足够支持故障调查的最小业务日志契约。插件不主动记录凭证、原始请求/响应、消息正文或资源内容；Hermes core 负责最终格式化、脱敏、路由和落盘。

## What Changes

- **BREAKING** 删除 `milky.observability` 的字段白名单、敏感 marker、异常/traceback 检查、自定义 `LogRecord`、插件私有异步日志队列和 Tool 参数/结果安全投影。
- 保留标准 Python logger，并统一使用 `hermes_plugins.milky.*` logger 命名空间，使业务日志进入 `agent.log`，且在 gateway 进程中可通过 `hermes logs gateway -f` 查看。
- 保留少量稳定的运维事件标签：生命周期、Action、SSE、入站决策、资源、出站、mute 和 Tool；事件标签是可检索的运维词汇，不是插件安全 API。
- Action、Tool 和出站操作的完成日志保留操作名、结果分类、HTTP 状态码、传输阶段和 `duration_ms`；SSE 保留连接、断线、重连次数、退避和安全原因分类。
- 入站、资源和 mute 日志保留决策、阶段、低敏关联 ID、计数和降级分类；高频 frame、常规丢弃和逐项细节降为 DEBUG 或省略。
- 业务日志使用标准 logger 的消息文本表达固定 `event=... key=value` 低敏字段，不依赖插件自定义 `extra`、字段渲染器或日志后端。
- 任何级别都不得记录 token、Authorization、完整 URL、请求/响应 body、消息正文、raw segment、媒体 URL、路径、文件内容、Tool 原始参数/结果、自由文本异常或 traceback。
- 保留日志不可用、被丢弃或 handler 失败时的业务行为不变；不在插件内新增指标系统、降采样器或 fallback handler。
- 更新日志相关 OpenSpec 条款和测试计划，保留协议错误分类、媒体权限、allowlist、Tool 授权、资源所有权和生命周期语义。

## Capabilities

### New Capabilities

无。本 change 只调整现有日志能力的实现边界和可观察行为。

### Modified Capabilities

- `adapter-observability`: 删除插件私有安全日志层，但保留最小运维事件、关键结果字段、日志级别和检索边界。
- `milky-event-stream`: 保留 SSE 连接、断线、重连和 handler 失败的可观察事实，移除插件私有格式和安全过滤器。
- `plugin-lifecycle`: 保留初始化、关闭、fatal report 和 mute 扫描汇总的运维可见性，移除插件私有日志实现。
- `security-boundaries`: 保留日志不得主动接收敏感原始值，以及 Tool raw envelope 不被日志改写或复制的边界。
- `qq-action-tools`: 保留显式 Tool 调用的名称、分类、状态码和耗时诊断，不记录参数和结果内容。
- `home-channel-delivery`: 保留 home channel 投递成功、失败、耗时和安全分类的诊断。

## Impact

- 运行时代码：`milky/observability.py`、`adapter.py`、`milky/`、`inbound/`、`outbound/`、`state/` 中的日志调用、logger 命名空间和 Tool 日志辅助函数。
- 测试：日志安全边界测试、业务结果测试、Action/SSE/生命周期/出站/Tool 日志可观察性测试及其 fixture。
- 规范：上述六个 capability 的 change delta；归档 change 只作为历史记录，不直接修改。
- 依赖：依赖 Hermes core 的标准 logger、`RedactingFormatter`、异步队列和 `hermes logs` 文件路由；不修改或 monkey patch Hermes core。
- 运维入口：默认 `hermes logs -f` 查看 `agent.log`；gateway 进程使用 `hermes logs gateway -f`；深入排查使用 `--level DEBUG` 和 `--since`。
- 风险：日志文本不是业务 API，但关键 `event` 标签和结果字段需要保持足够稳定以支持人工检索、故障 runbook 和错误率/延迟分析。
