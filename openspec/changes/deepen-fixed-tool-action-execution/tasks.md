# Tasks

## 1. 固定行为基线与共同契约

- [x] 1.1 通过注册工具 interface 建立全部 26 个 Action 的请求与结果基线，并将已确认的 schema、主规范与运行差异及基线测试位置记录到本 change 的 evidence.md；按各 operation 的校验规则覆盖代表性的省略、null、false、合法空字符串、非法类型、范围、未知字段、未绑定与非法输入分类，包含 no_cache=false 投影和 count 差异，核对 manifest 并运行 uv run pytest -q tests/test_qq_tools.py tests/test_tool_result_passthrough.py。
- [x] 1.2 建立固定执行 module 的窄 interface 并迁移共同规则，保留各入口网络前校验与既有字段投影；同步 ARCHITECTURE.md 的职责说明，通过基线请求/结果差异断言和 uv run pytest -q tests/test_qq_tools.py tests/test_milky_client.py 验证没有新增或收紧行为。
- [x] 1.3 迁移查询工具路径并同步架构说明；运行 uv run pytest -q tests/test_tool_result_passthrough.py tests/test_qq_tools.py，验证原始文本、数组、null、非 JSON、协议拒绝和 HTTP 错误均保真，内部资源和状态查询继续执行 typed 校验。

## 2. 收拢执行与兼容路径

- [x] 2.1 迁移状态变更工具和生命周期降级，更新职责说明；用 fake transport 验证同名 operation、精确请求体、无响应只提交一次、未绑定和关闭不建连接、不触网，取消继续传播且不重发，运行 uv run pytest -q tests/test_qq_tools.py tests/test_tool_result_passthrough.py tests/test_observability.py 确认日志不泄漏原文。
- [x] 2.2 将仅供测试的 typed 转接迁移到真实 client 与 raw fake transport adapter，核对直接调用方后移除失去用途的转接，保留非 Tool interface 与现有 client 连接所有权；运行 uv run pytest -q tests/test_milky_client.py tests/test_adapter_lifecycle.py tests/test_resources.py tests/test_multimedia_outbound.py，确认同名资源或成员查询的 Tool 与非 Tool 响应契约各自保持。
- [x] 2.3 替换被注册 interface 完整覆盖的内部测试并更新 ARCHITECTURE.md；交付旧场景到保留测试的覆盖对应记录，验证 manifest、现有 Tool 绑定、两个贴纸语义工具和注册无网络行为不回归，运行 uv run pytest -q tests/test_plugin_entry.py tests/test_sticker_send.py tests/test_sticker_search.py。

## 3. 综合验证

- [x] 3.1 运行完整 pytest、Ruff 检查与格式检查、uv build、git diff --check 和 OpenSpec 严格校验，记录命令结果与 skip。
- [x] 3.2 在可用真实宿主验证只读工具发现和响应交付，证据分别记录 fake 与真实结果；副作用 smoke 必须另获明确授权，环境不可用记 blocked/unsupported，不称集成通过。
