# Evidence ledger

## 根因

线上日志中 `send_profile_like` 的两类结果：

```text
classification=unsupported  (本地)  -> {"ok":false,"classification":"unsupported","error":"tool is unavailable"}
classification=delivered    (远端)  -> {"status":"failed","retcode":-500,"message":"...已达上限"}
```

第一类是插件本地 JSON，`unsupported` 同时覆盖配置不可读、client 已关闭和 Action 未注册；
`_tool_error` 丢弃了 `ActionError.reason`，所以三种情形对外文本完全相同。第二类按原样交付契约
返回远端 body，模型必须自行解析。

`sender` 层的 `_failure(_error_classification(error), _safe_reason(error))` 进一步把原因折叠成默认值，
即使 client 已带 `reason_code` 也无法到达结果层。

## 实现

- `milky/client.py`：`ActionError` 增加 `reason_code`，白名单为 `ACTION_REASON_CODES`；配置、
  client 已关闭、Action 未注册三处赋值。
- `outbound/sender.py`：`_failure_from_error` 保留原因码；`OutboundSendResult.reason_code` 与
  `_make_result` 兼容宿主 `SendResult` 不认识的字段。
- `outbound/tools.py`：`_tool_error` 与 `_serialize_result` 输出 `reason`、`retryable`；
  `retryable` 只在 `client_closed` 为 true。
- `send_profile_like` 的 `count` 在 handler、client、`validate_tool_params` 三处统一为 `1..50`。
- `__init__.py`：skill 登记读取 frontmatter `description`，注册能力或文件缺失时记录固定告警。
- 平台指引补充两类结果形状与重试语义。

## Verification

- `uv run pytest -q tests/test_tools_without_adapter.py`：9 passed，覆盖配置不可读、传输未知、
  client 已关闭、`count` 越界与边界值。
- `uv run pytest -q tests/test_plugin_entry.py`：20 passed，断言 skill 登记携带 frontmatter 描述。
- `uv run pytest -q`：1495 passed, 6 skipped。
- `uv run ruff check .`、`uv run ruff format --check .`、`git diff --check`：通过。
- `uv run openspec validate fix-fixed-tool-error-reasons --type change --strict`：valid。

## 真实环境

- 未在 `hermes-dev` 实测三种结果的可区分性；任务 5.4 保持未完成，不宣称线上已验证。

## Retained boundaries

- 远端响应体仍原样交付，不附加本地字段，不解析 envelope。
- 不新增自动重试；`retryable` 只是给模型的提示。
- 不修改 Hermes core。
- 告警和结果不包含路径、凭证或异常正文。
