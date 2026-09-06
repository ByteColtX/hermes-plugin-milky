## 1. 契约和调用点盘点

- [ ] 1.1 对照六个 delta spec 和现有主 spec，确认要移除的是插件私有安全日志层，不是关键运维可观察性、认证、错误分类、媒体权限、allowlist 或 Tool raw envelope；验证 OpenSpec requirement 名称与 delta 一致
- [ ] 1.2 盘点 `milky/observability.py` 的公开 API、全部运行时导入、`log_event()`/`log_local_exception()` 调用、普通 logger 调用和 Tool 日志投影；为每个调用标注保留事件、级别、低敏字段或删除结论，并用 `rg` 验证没有遗漏
- [ ] 1.3 建立日志矩阵，覆盖 `milky.lifecycle`、`milky.action`、`milky.sse`、`milky.inbound`、`milky.resource`、`milky.outbound`、`milky.mute` 和 `milky.tool`；验证每个关键边界至少有结果分类，Action/Tool/出站至少有状态码（已知时）和 `duration_ms`
- [ ] 1.4 审查保留日志参数，确认 token、Authorization、完整 URL、请求/响应 body、消息正文、raw segment、媒体 URL、路径、文件内容、Tool 原始参数/结果、自由文本异常和 traceback 不会进入 logger；验证源码检索和合成敏感 fixture 覆盖这些输入

## 2. 移除插件私有安全日志层

- [ ] 2.1 删除 `milky/observability.py` 的字段白名单、敏感 marker、固定安全 registry、异常/traceback 检查、自定义 `LogRecord` 和后台日志分发；验证运行时源码不再导入该模块或调用其 API
- [ ] 2.2 将运行时 logger 统一迁移到 `hermes_plugins.milky.*` 命名空间，并保持默认传播到 Hermes root；验证 fake logger 不添加 handler、不开启 `propagate=False`，且组件前缀可被 Hermes core 识别
- [ ] 2.3 将 adapter、Action、SSE、resource、inbound、outbound、mute 和 home channel 的关键结果改为标准 logger 消息，保留 `event=milky.*`、分类、状态码、耗时、计数和必要关联 ID；验证 `INFO/WARNING/DEBUG` 级别符合日志矩阵
- [ ] 2.4 删除 `outbound/tools.py` 的参数/结果安全投影和日志目的复制；Tool 日志仅保留工具名、Action、分类、状态码、耗时和必要关联 ID，验证成功 raw envelope、失败分类和自由文本参数交付不变
- [ ] 2.5 清理因 helper 移除而无用的安全日志 import、字段转换和异常包装，但保留业务错误分类和 `error_type` 规范化；验证 `uv run ruff check .` 不报告未使用符号

## 3. 测试和回归

- [ ] 3.1 删除只测试 `[Milky]` 前缀、旧 event registry、字段白名单、异常链拒绝、日志线程池和 Tool 安全投影实现的测试与 fixture；验证测试目录不再引用已删除 helper
- [ ] 3.2 为每类关键事件增加日志断言：生命周期 ready/failure、Action 成功/拒绝/超时/malformed/transport_unknown、SSE 重连、入站 wait/trigger/gate、资源降级、出站结果、mute 汇总和 Tool 结果；验证事件标签、级别和必要字段可被 `caplog` 检索
- [ ] 3.3 增加合成敏感输入回归：异常包含 token/Authorization/URL/body，Action 响应包含正文，入站包含正文和媒体引用，Tool 返回下载 URL；验证 logger 消息不出现这些值，也不出现 traceback
- [ ] 3.4 增加日志禁用、低级别、handler 丢弃或 handler 失败场景；验证连接、SSE、Gate/Will、buffer、Action、Tool、出站和 MuteTracker 的结果不依赖日志输出
- [ ] 3.5 运行受影响的协议、生命周期、SSE、inbound、outbound、Tool、resource 和 mute 定向测试；验证没有因日志迁移改变事件顺序、扣费、重连、发送结果或未知结果语义

## 4. 文档和规范同步

- [ ] 4.1 更新 `ARCHITECTURE.md` 中的日志职责、logger 命名空间、关键事件类别和敏感输入边界；验证文档与 delta spec、实现调用点一致
- [ ] 4.2 更新 `README.md` 和开发文档，说明 `hermes logs -f`、`hermes logs --level DEBUG -f`、`hermes logs gateway -f` 的查看路径，并删除旧 `[Milky]`、旧字段 schema 和插件安全后端承诺
- [ ] 4.3 在归档前依据本 change 的 delta spec 同步六个主 spec；验证主 spec、代码、测试和 README 的日志所有权、事件字段和禁止项一致

## 5. 质量门禁和证据

- [ ] 5.1 运行受影响测试和完整 `uv run pytest -q -rs`，记录通过数量、跳过项及 Hermes host/真实 Milky 未覆盖边界
- [ ] 5.2 运行 `uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check`，验证没有未使用导入、格式问题、构建问题或空白错误
- [ ] 5.3 运行 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`，验证六个 delta spec、proposal、design 和 tasks 的 requirement、scenario 与任务描述一致
- [ ] 5.4 复核最终 diff 和日志 fixture，确认没有新增或保留 token、Authorization、完整 URL、请求/响应 body、真实身份、敏感正文、真实媒体 URL、媒体字节、路径或 traceback；将命令结果、跳过项和外部环境边界写入 evidence ledger

## Evidence ledger

记录日期：待实施阶段填写（Asia/Shanghai）

### 已执行

- 规划阶段已读取当前实现、Hermes core `0.21.0` 日志实现、相关主 spec 和现有 change artifacts；本 change 尚未修改运行时代码，尚未运行实现回归命令。
- 已确认 Hermes core 默认 `hermes logs -f` 跟踪 `agent.log`，root logger 记录通过异步队列写入；`hermes logs gateway -f` 只接收 gateway 组件前缀，因此本 change 采用 `hermes_plugins.milky.*` 命名空间。

### 未覆盖与边界

- 当前规划不证明真实 Hermes host 会加载插件日志，也不证明真实 Milky 服务行为；实施阶段必须把 fake host、协议 fixture、日志文件路由和真实环境未覆盖项分开记录。
- 本 change 不授权真实 Milky 消息发送、文件上传或其他远端写入 smoke。
