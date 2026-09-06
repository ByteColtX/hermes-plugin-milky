## Context

当前插件通过 `milky.observability.log_event()` 同时实现了安全字段校验、固定事件渲染、异常链检查和插件私有异步提交；`outbound/tools.py` 还会复制 Tool 参数或结果生成日志投影。Hermes core 已在标准 logger 路径提供 `RedactingFormatter`、文件路由和 `QueueHandler`/`QueueListener`。

原设计把固定事件名、结构化字段和大量关键结果日志一并视为重复安全日志，可能导致运维人员无法回答“哪个 Action 失败”“哪个端点变慢”“SSE 是否在重连”或“消息为什么没有交给 Agent”。本设计把安全实现和业务可观察性拆开：删除插件安全后端，保留少量可检索的运维事实。

## Goals / Non-Goals

**Goals:**

- 让 Hermes core 成为日志接收、最终脱敏、异步落盘和文件路由的唯一所有者。
- 保留能定位生命周期、Action、SSE、入站、资源、出站、mute、Tool 和 home channel 问题的最小业务日志。
- 让 Action、Tool 和出站完成日志包含结果分类、HTTP 状态码和 `duration_ms`，支持错误率和慢端点的人工分析。
- 让日志通过标准 Hermes 命令可见：`hermes logs -f` 查看 `agent.log`，gateway 进程还可查看 `hermes logs gateway -f`。
- 保证日志失败、丢弃或级别关闭不改变业务状态机、重试、扣费、发送或错误结果。
- 保持调用点不把敏感原始值交给 logger，即使 Hermes core 的脱敏配置发生变化。

**Non-Goals:**

- 不修改 Hermes core，不增加插件 fallback handler、指标系统、日志聚合器或 monkey patch。
- 不保留字段 sanitizer、敏感 marker 扫描、异常 traceback 审核、自定义 `LogRecord` 或插件日志线程池。
- 不把日志变成 Tool raw envelope、请求 body、响应 body、消息正文或资源内容的副本。
- 不记录每个 SSE frame、每个 segment、每个普通丢弃或每个高频内部步骤；这些只在 DEBUG 下保留必要摘要。
- 不改变认证、HTTP Action、SSE、Gate/Will、buffer、dedup、资源所有权、媒体限制、出站路由或 Tool 授权语义。

## Decisions

### 1. 删除安全日志实现，保留运维事实

删除 `milky.observability` 的安全字段白名单、敏感 marker、固定字段渲染、异常/traceback 检查、`LogRecord` 构造和后台提交。运行时直接调用标准 logger；每个调用点只传固定事件标签和已经由业务边界确认的低敏标量。

事件标签采用小集合的运维词汇，而不是旧的几十个插件事件 registry：

- `milky.lifecycle`：连接、就绪、关闭和生命周期失败；
- `milky.action`：每个 HTTP Action 的完成结果；
- `milky.sse`：SSE 连接、断线、重连和 handler 失败；
- `milky.inbound`：canonical、dedup、Gate、Will、buffer 和 handoff 结果；
- `milky.resource`：资源解析汇总和降级；
- `milky.outbound`：路由、上传、分块和发送结果；
- `milky.mute`：初始扫描和状态刷新汇总；
- `milky.tool`：显式 Tool 调用的结果。

这些标签需要保持可检索，但不作为插件业务 API、结构化 schema 或安全过滤接口。

### 2. 使用标准 logger 命名空间

插件 logger 使用 `hermes_plugins.milky.<module>` 命名空间。这样子 logger 默认传播到 Hermes root，进入 `agent.log`；gateway 模式下也匹配 Hermes core 的 `hermes_plugins` 组件前缀，进入 `gateway.log`。插件不设置 `propagate=False`，不添加 handler，也不创建自己的文件。

日志消息使用单条普通文本表达必要字段，例如：

```text
event=milky.action.completed action=send_group_message classification=accepted status_code=200 duration_ms=83 chat_key=group:123
```

不依赖 `extra` 作为查看契约，因为 Hermes core 的默认文件格式主要展示 `record.message`。不重复渲染同一字段，不同时维护第二套人类消息和结构化安全投影。

### 3. 按运维问题设计日志级别

- `INFO`：生命周期终态、每个外部 Action 完成结果、Tool 完成结果、出站结果、入站 wait/trigger/handoff、资源完成汇总、mute 扫描汇总和 home channel 结果。
- `WARNING`：拒绝、超时、HTTP/协议/传输未知、重连、降级、unknown mute 状态、handoff 失败、上传失败和慢操作诊断。
- `ERROR`：插件拥有的不可恢复本地边界或明确的生命周期终止错误；只记录固定分类、`error_type` 和关联字段，不使用 traceback。
- `DEBUG`：连接尝试、正常 SSE frame、常规 duplicate/self/temp 丢弃、Gate 细节、逐项资源细节和高频成功细节。

Action 和出站日志至少包含 `action`/`tool`、`classification`、`status_code`（已知时）、`transport_phase`（适用时）和 `duration_ms`。这样不需要插件内新增 metrics 计数器，也能从日志按操作名和分类统计失败或排查慢端点。

### 4. 只保留低敏关联字段

允许的日志值限于固定枚举、非负数、计数、耗时、状态码、规范化异常类型名和必要的业务关联 ID，例如 `chat_key`、`message_id`、`ingress_sequence`、`group_id` 或 `user_id`。昵称不作为常规运维字段。

远端异常先转换为既有业务分类；可选的 `error_type` 只记录异常类名，不记录 `str(exception)`、异常参数、响应正文或 traceback。日志调用不接收完整 URL、请求/响应对象、body、segment、媒体引用、路径、文件内容、Tool 参数或 Tool 结果。

### 5. 用边界结果而不是原始数据支持故障调查

日志必须回答以下问题：

- 是否完成初始化，失败在哪个阶段；
- 哪个 Action、Tool 或出站操作失败，结果属于哪种分类，HTTP 状态和耗时是多少；
- SSE 当前是否连接、何时断开、下一次重连何时发生；
- 入站消息被哪个阶段拒绝、等待还是触发；
- 资源、mute 或出站是否部分降级。

日志不回答消息内容、服务端原始错误、媒体内容或 Tool 返回值本身；这些数据继续由业务返回契约或受控的 Hermes 资源/Tool 边界交付。

### 6. 高频诊断不进入默认 INFO 流

不为每个 raw SSE frame、普通消息正文、每个 segment 或每个重复事件输出 INFO。malformed/unknown 突发只记录固定分类，必要时使用 DEBUG、已有有界诊断或汇总。日志 handler 的速度和可用性不得参与接收、重试、扣费或发送决策。

## Risks / Trade-offs

- [删除安全 helper 后调用点可能误传动态值] → 用固定事件/字段清单、源码审计和日志 fixture 断言禁止敏感输入；Hermes core 脱敏只作为防御层。
- [Action 每次完成都记录可能增加日志量] → 只记录低基数结果字段；SSE frame、segment 和 routine drop 使用 DEBUG 或省略；不在插件内重复实现聚合器。
- [标准日志文本不是结构化日志 API] → 保留稳定的 `event=milky.*`、`action`、`classification`、`status_code` 和 `duration_ms` 词汇，满足 `hermes logs` 和人工 grep；不承诺任意 `extra` 字段。
- [logger 命名空间变化会影响既有测试或外部 grep] → 作为本 change 的 breaking observability change 更新测试和文档；旧 `[Milky]`、旧事件 registry 和旧 logger 名称不再是契约。
- [未记录原始异常会降低单条日志的细节] → 记录业务分类、异常类型、HTTP 状态、传输阶段、耗时和关联 ID；原始异常继续禁止进入日志以保护凭证和正文。
- [`gateway.log` 依赖 Hermes 进程使用 gateway mode] → `agent.log` 始终是默认入口；change 只约束插件 logger 命名空间，不修改 core 的进程模式。

## Migration Plan

1. 更新六个 delta spec，恢复关键运维结果的可观察性，并明确禁止原始敏感输入。
2. 盘点所有日志调用，将 logger 命名空间迁移到 `hermes_plugins.milky.*`，把关键结果改为直接标准 logger 消息；删除 `milky.observability` 和 Tool 日志投影。
3. 删除只测试安全 helper 实现的测试，补充 Action/SSE/生命周期/入站/资源/出站/mute/Tool 的事件、级别和敏感值不泄露测试。
4. 运行定向测试、完整 pytest、Ruff、format、build、diff check 和 OpenSpec strict validation；失败按业务行为、日志可观察性、测试设施或环境差异分类。
5. 上线后用 `hermes logs -f` 验证默认日志，用 `hermes logs --level DEBUG -f` 验证深度诊断；gateway 模式用 `hermes logs gateway -f` 验证命名空间路由。回滚时恢复插件代码即可，不需要日志迁移。

## Open Questions

无。事件标签、字段边界、日志级别和 Hermes 查看路径已在本 change 中确定。
