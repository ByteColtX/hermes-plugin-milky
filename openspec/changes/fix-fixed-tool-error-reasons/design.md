# Design

## 现状

固定 Action Tool 的本地失败只有三个分类：`invalid_input`、`unsupported`、`transport_unknown`，
对外文本分别是固定英文。`unsupported` 同时覆盖配置不可读、客户端已关闭和 Action 未注册；调用方
无法判断哪一种可以重试。

远端响应遵循既有的原样交付契约：只要取得响应体就返回原始字符串，日志记为 `delivered`。该契约由
`milky-http-actions` 与 `qq-action-tools` 锁定，不改动。

## 决策

在本地失败结果中增加两个字段，而不是新增分类：

```json
{"ok":false,"classification":"unsupported","reason":"client_closed","error":"tool is unavailable","retryable":true}
```

- `reason` 使用固定集合，避免自由文本泄漏。
- `retryable` 只在请求确定未进入网络时为 true（目前只有 `client_closed`）。
- `transport_unknown` 保持 `retryable=false`：结果未知时重复有副作用的 Action 可能重复执行。

原因码从 `ActionError.reason_code` 逐层保留：client 抛出 → sender 用 `_failure_from_error`
转成结果对象 → `_serialize_result` 读取。三点赋值分别是配置不可读、client 已关闭、Action 未注册。

## 备选方案

- **新增 `rejected` / `http_error` 分类**：违反原样交付契约，且会让调用方把远端拒绝当成本地失败。
- **解析远端 envelope 并改写结果**：同样违反契约；远端 `status`/`retcode` 必须由调用方自己读取。
- **自动重试**：规格禁止，且点赞不是幂等操作。

## 风险

- [风险] 模型可能把 `retryable=true` 当作自动重试许可。→ 指引明确只允许单次重试，且只针对
  `client_closed`。
- [风险] 老宿主 `register_skill` 不接受 description 位置参数。→ 捕获 `TypeError` 后退回两参数
  登记，保持旧行为。
