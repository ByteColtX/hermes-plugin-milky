# 验证证据

## 已验证行为

- 拦截器按完整字符串相等匹配，未执行 trim、大小写折叠或模糊比较；可向可复用函数登记多条规则。
- fake adapter、sender 和 client 测试证明完整命中会在普通文本 sender 前以成功终止结果结束，不调用 Milky 消息 Action，也不返回远端 message ID。
- 未命中、包含提示的长文本、前后缀及空白、标点、大小写差异继续走既有发送路径；媒体和文件专用入口携带相同提示文案时仍正常委托。
- 过滤结果使用 `success=True`，因此 Hermes Gateway 仍可能按现有 `SendResult.success` 语义将 obligation 记为 delivered；测试未连接 Hermes Gateway 验证其运行时 ledger。

## 检查记录

- `uv run pytest -q`：`1004 passed, 3 skipped`。
- `uv run pytest -q -rs`：同为 `1004 passed, 3 skipped`；skip 分别是当前测试环境无 Hermes host、真实 Hermes 集成要求显式开启，以及多媒体测试当前无 Hermes host。
- `uv run ruff check .`、`uv run ruff format --check .`、`git diff --check`：通过。
- `openspec validate intercept-outbound-text --strict`：通过。

## 验证范围

本 change 的拦截证据来自合成文本及 fake adapter/sender/client 单元测试；这些测试只证明插件在命中时没有请求 Milky 消息 Action，不代表真实 Hermes/Milky 端到端投递验证。完整 pytest 运行包含的 fake host 测试也不连接真实 Milky，未执行真实消息发送。
