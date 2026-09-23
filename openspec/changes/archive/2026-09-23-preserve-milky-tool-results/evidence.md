# 验证证据

## 已验证行为

- Tool 调用入口在网络前执行固定 operationId、参数和 client 状态校验；取得 HTTP body 后直接以 UTF-8
  字符串交付，非法 UTF-8 使用替换字符，不调用 envelope/DTO parser、最小 `data` 校验、敏感键过滤、
  容器冻结或 JSON 重建。
- 合成响应覆盖成功 envelope、协议拒绝、HTTP 4xx/5xx、HTML 和非 JSON 文本、数组、标量、显式 `null`、
  空 body、嵌套敏感键、非 UTF-8 字节；fake Hermes host 在无结果变换 hook 时收到与 transport body 一致的
  字符串。
- Tool 本地结果仅保留 `invalid_input`、`unsupported` 和 `transport_unknown`；副作用 Tool 的请求在未知
  传输结果下只提交一次，协议拒绝和 HTTP 错误均归类为 `delivered` 并只在日志中保留状态码。
- sender 的 Tool 包装不再校验或重建响应，也不因 Tool 远端结果调度 MuteTracker 刷新；普通 Action、登录、
  群列表、成员状态、消息发送和文件上传继续沿用既有 envelope 校验与错误分类。
- `register(ctx)` 和 Tool 注册未声明 `transform_tool_result`、截断或落盘 hook；Hermes core 的后置处理不在
  插件交付契约内。

## 检查记录

- `uv run pytest -q -rs`：`985 passed, 3 skipped`；3 项 skip 仍是既有 fake/真实 Hermes 集成环境限制。
- `uv run ruff check .`、`uv run ruff format --check .`、`git diff --check`：通过。
- `openspec validate --changes --strict`：全部未归档 change 通过。

## 验证范围

仅使用 fake transport、fake host、合成 fixture 和 monkeypatch parser；未连接真实 Milky、未执行真实消息、
群管理、好友关系或其他可能产生副作用的 Action。Hermes core 的 hook、`error` 字段截断和大结果落盘行为由
宿主负责，本 change 只证明插件交付边界，不宣称最终模型上下文仍逐字一致。
