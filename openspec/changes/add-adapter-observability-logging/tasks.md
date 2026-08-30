## 1. 日志契约与脱敏 fixture

- [x] 1.1 建立合成身份、凭证、URL、正文、媒体引用、本地路径和异常详情的日志测试输入，并验证它们不会出现在 `LogRecord` 消息或结构化字段中
- [x] 1.2 固定 `[Milky] ` 前缀、Hermes-agent 风格的 `info`/`warning`/`error`/`debug` 级别、事件名集合、脱敏 ID 形状和允许字段，并用 `caplog` 验证规范场景
- [x] 1.3 为 inbound wait → trigger → resource → Hermes handoff、Action 失败、出站失败和 mute refresh 建立可关联的 ingress/count fixture，并验证 fixture 不含真实身份或 live 响应

## 2. 共享安全日志边界与既有日志迁移

- [x] 2.1 实现无状态的共享日志辅助边界，统一 `[Milky]` 消息前缀、固定事件名、字段白名单、数字 ID/chat key 脱敏和安全错误分类，并通过独立单元测试验证未知字段和敏感输入被拒绝
- [x] 2.2 将 `milky/event_stream.py` 的断连、退避、尝试、恢复、取消和坏帧日志迁移为 Hermes-agent 风格，同时保留既有 event name、reason 白名单、attempt/delay 语义；运行 SSE 重连、取消和资源释放测试验证行为不变
- [x] 2.3 将 `state/mute_tracker.py` 与 `adapter.py` 的冷启动、ready、停止、事件更新、刷新成功/失败日志迁移为统一风格，并验证 UID/群号脱敏、重复停止不重复记录和初始化顺序不变

## 3. 多模块关键路径日志

- [x] 3.1 在 HTTP Action 的统一调用边界记录安全的成功/失败、分类、HTTP 状态和耗时日志，不记录 body、URL 或 Authorization；用 fake transport 覆盖成功、rejected、malformed、超时和未知结果
- [x] 3.2 在 inbound/canonical、dedup、Gate、session buffer、Will 和 Hermes handoff 边界记录 observe-only、temp/非法、duplicate、deny、wait、trigger、drain、提交成功/失败和 reply cost 事件；验证日志不改变 admission、buffer、Will 或 Agent 调度
- [x] 3.3 在资源/reply/forward materialization 边界记录触发阶段的开始、完成计数和降级分类，在 outbound sender/file upload 边界记录 group/dm 路由、分块/附件计数和最终结果；验证 URL、路径、文件名、正文和 file ID 不泄露
- [x] 3.4 为未知事件、malformed 帧、重复拒绝和普通成功细节加入 debug、限速或聚合策略，并用慢日志 handler/突发事件测试验证 receive loop、detached handoff 和后续事件不被阻塞
- [x] 3.5 对需要 traceback 的本地未处理错误建立安全例外测试，验证只有不含远端 payload、凭证和路径的异常可以使用 Hermes-agent 风格的 `error`/`exc_info`，远端错误只记录安全分类

## 4. 回归验证与交付证据

- [x] 4.1 运行 `uv run pytest tests/test_milky_event_stream.py tests/test_mute_tracker.py tests/test_adapter_lifecycle.py tests/test_hermes_pipeline.py tests/test_outbound.py -q`，验证既有协议、生命周期、入站、出站和新增日志断言通过
- [x] 4.2 运行 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check`，并按协议字段/路径、并发/顺序、权限/安全、Hermes API 或测试基础设施分类失败
- [x] 4.3 在宿主缺少 HTTPX 时使用 `uv run --with httpx==0.28.1 pytest -q` 补跑相关测试，验证日志 change 不改变已有 fake/本地 HTTPX 集成行为；不执行未经明确授权的 Milky 写入 Action
- [x] 4.4 运行 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`，验证新 capability 与 SSE、生命周期、系统安全 delta 的 requirement、scenario 和 tasks 一致，并在完成前记录未解决风险

## 5. 全量日志一致性重构

- [x] 5.1 建立 adapter、Milky client、SSE、inbound、resource、outbound、MuteTracker 和 smoke CLI 的完整输出清单，确认 runtime 只有登记的日志入口、事件名和字段，且 CLI `print` 与 runtime logger 明确分离；用源码检索和审计测试验证。
- [x] 5.2 重构共享日志边界为固定事件标签 + 单次安全字段渲染，移除动态自定义消息和字符串字段去重路径；补充 `uid`、`nickname`、`component`、`member_mute`、`whole_mute` 等字段的类型/枚举/脱敏校验，并用单元测试验证重复字段、双 `[Milky]` 前缀和未脱敏数字 ID 均不能进入日志。
- [x] 5.3 重构 adapter 与 MuteTracker 日志，修正 component close/fatal report 事件归属，保留冷启动 UID、nickname、确认禁言群 member/whole 状态和单条扫描汇总；用真实 MuteTracker 初始化、失败、刷新、TTL 和重复停止测试验证事件数量、字段只出现一次且状态语义不变。
- [x] 5.4 重构 SSE 与 HTTP Action 日志，区分 frame ignored、handler failed、连接断开/重连和 Action 失败分类，补齐安全 reason 与状态字段；用 malformed、unknown、handler exception、超时、rejected、非 JSON 和 HTTP 错误 fake transport/fixture 验证不输出原始异常或 payload。
- [x] 5.5 审计并规范 inbound、Will/session 编排、resource 和 outbound 的日志归属、级别、终态和关联字段；确保 Action 结果与上层结果不互相伪装，resource completed/degraded、inbound handoff 和 outbound chunk/upload 不重复伪造终态；用 fake pipeline 和顺序断言验证业务控制流不变。
- [x] 5.6 收紧本地异常和非阻塞日志分发边界，递归检查 exception cause/context/notes 与 traceback 路径，远端错误不得带 traceback；用慢 handler、突发 debug、容量耗尽和安全/不安全异常测试验证业务不等待日志且 info/warning/error 处理符合设计。
- [x] 5.7 运行定向日志/协议/生命周期测试、`uv run pytest`、必要的 `uv run --with httpx==0.28.1 pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check` 和 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`；将结果、未解决风险和未执行的真实写入 Action 更新到本台账。

## 6. 执行证据台账

| 阶段 | 命令/证据 | 结果 | 反馈分类与下一步 |
|---|---|---|---|
| 规划 | 已读取 `ARCHITECTURE.md`、当前 active change 全部 artifacts、既有重连日志 change，以及 `../hermes-agent` 的 `AGENTS.md`、`hermes_logging.py`、`gateway/platforms/base.py`、`gateway/platforms/qqbot/adapter.py` 和 `gateway/platforms/weixin.py` 相关日志实现 | 待实施阶段补充 | 范围限定为 Hermes-agent 风格的跨模块日志，不改变 Milky 协议、策略和宿主日志后端 |
| fixture/实现 | 新增 `tests/fixtures/observability_inputs.py`、`tests/test_observability.py`、`milky/observability.py`，并接入 adapter、client、SSE、inbound、resource、outbound 和 MuteTracker | `uv run pytest tests/test_observability.py -q`：19 passed；定向回归：68 passed/2 skipped | 已验证固定事件名、字段白名单、ID/chat 脱敏、Action/资源/出站/mute 关联、慢 handler 不阻塞和固定标签与结构化字段分离；未发现敏感字段泄露或顺序回归 |
| 质量门禁 | `uv run pytest`；`uv run ruff check .`；`uv run ruff format --check .`；`uv build`；`git diff --check` | 全量 295 passed/12 skipped；`uv run --with httpx==0.28.1 pytest -q`：307 passed；ruff、format、build、diff 均通过 | 默认环境依赖补跑使用 `uv run --with httpx==0.28.1`；未执行真实 Milky 写入 Action |
| OpenSpec | `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict` | 2 changes passed，0 failed | 新 capability 与既有 SSE、生命周期、系统安全 delta 校验通过；无未解决规范风险 |
| 复核/修订 | 全量检索 runtime logger、动态 `message=`、事件 registry、现有 delta 与主 spec | 已修复 Mute 汇总重复渲染、双前缀、动态消息脱敏旁路、两个错误事件归属和 Will/session 日志归属问题；人类消息现只保留固定标签，动态值只进入结构化字段 | 已更新 proposal/design/spec/tasks、实现代码和回归测试；5.1-5.7 已完成 |
| 最终验证 | 定向日志/协议/生命周期测试、全量 pytest、HTTPX 补跑、Ruff、format、build、diff check、OpenSpec strict | 定向 68 passed/2 skipped；默认 295 passed/12 skipped；HTTPX 307 passed；`ruff check`、`ruff format --check`、`uv build`、`git diff --check`、strict validation 全部通过（2 changes passed，0 failed） | 未执行真实 Milky 写入 Action；没有已知未解决的实现或规范风险 |
