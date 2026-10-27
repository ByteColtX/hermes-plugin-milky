# Proposal

## Why

线上 cron 与群聊里，`send_profile_like` 交替出现两类结果：插件本地的
`{"ok":false,"classification":"unsupported","error":"tool is unavailable"}`，以及 Milky 远端
`200` 响应体里的业务拒绝（例如「今日同一好友点赞数已达上限」）。第一类没有说明是配置不可读、
客户端已关闭还是服务不可达；第二类按原样交付契约被记为 `delivered`。模型必须重试才能区分，
而重试有副作用的 Action 会重复消耗每日点赞额度。

同类问题覆盖全部 25 个固定 Action Tool：它们共用 `outbound/tools.py::_execute_action` 与
`_tool_error`。

## What Changes

- 本地失败结果增加固定 `reason` 原因码与 `retryable` 提示；`retryable` 只在请求未进入网络时为
  true。
- `ActionError` 增加 `reason_code`，并在配置不可读、客户端已关闭、Action 未注册三处赋值；
  `sender` 与结果序列化层保留该原因码，不再折叠成 `service_unavailable`。
- `send_profile_like` 的 `count` 运行时校验对齐 schema 声明的 `1..50`，越界在网络前失败。
- 平台指引补充两种结果形状与重试语义，使模型无需试错即可判断。
- bundled skill 注册时传入 SKILL.md frontmatter 的 `description`，缺失时告警而不是静默跳过。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `qq-action-tools`：本地失败增加原因码与可重试提示，`count` 范围对齐。
- `milky-platform-prompt-guidance`：指引说明本地失败与远端原样响应的区别。
- `plugin-lifecycle`：bundled skill 登记时携带描述，失败可见。

## Impact

- 影响 `outbound/tools.py`、`outbound/sender.py`、`milky/client.py`、`milky/fixed_actions.py`、
  `__init__.py` 及对应规范与测试。
- 远端响应体仍原样交付；不修改 Hermes core，不新增自动重试，不改变副作用语义。
