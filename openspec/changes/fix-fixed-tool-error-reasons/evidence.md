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

插件代码 `e607427` 已部署到 `hermes-dev` 并重启网关，Milky 重新连接成功。用插件依赖环境执行
四种输入，结果互不相同：

```text
A config   -> {"ok":false,"classification":"unsupported","reason":"configuration_unavailable","error":"tool is unavailable","retryable":false}
B closed   -> {"ok":false,"classification":"unsupported","reason":"client_closed","error":"tool is unavailable","retryable":true}
C remote   -> {"status": "failed", "retcode": -500, "message": "quota reached"}
D count=51 -> {"ok":false,"classification":"invalid_input","reason":"input_invalid","error":"tool input is invalid","retryable":false}
```

真实宿主 `PluginManager.list_plugin_skill_metadata()` 已返回带描述的条目：

```text
hermes-plugin-milky:milky-qq-action-tools | Reference for Milky QQ Agent's 25 fixed Action ToolSpecs ...
hermes-plugin-milky:milky-qq-cq-reference  | Reference for Milky QQ Agent's CQ-compatible at, reply, face ...
```

仍未观察到的：真实 QQ 账号触发「今日同一好友点赞数已达上限」后的模型响应措辞。该样本依赖
配额耗尽，不作为已验证项。

## Retained boundaries

- 远端响应体仍原样交付，不附加本地字段，不解析 envelope。
- 不新增自动重试；`retryable` 只是给模型的提示。
- 不修改 Hermes core。
- 告警和结果不包含路径、凭证或异常正文。
