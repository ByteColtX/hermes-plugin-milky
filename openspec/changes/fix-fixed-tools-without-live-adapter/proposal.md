# Proposal

## Why

Hermes cron 的 managed 部署会把每个 job 移交给独立 worker 进程执行。该进程不物化 Milky 平台，
因此进程内没有 live adapter 绑定的 client；固定 Action Tool 的 handler 在 `_ACTIVE_SENDER` 为
`None` 时直接返回 `unsupported`，对外表现为 `{"error":"tool is unavailable"}`。结果是 26 个固定
QQ 工具在 cron 等无 adapter 会话中全部不可用，包括 `send_profile_like`。

官方平台插件契约要求 outbound client tools 在任何会话中可调用；工具不应把执行能力绑定到某个
特定进程里的 adapter 生命周期。

## What Changes

- 固定 Action Tool 执行时优先复用当前进程已绑定的 live client，保持既有网关内行为不变。
- 进程内没有 live client 时，按调用时 profile 配置创建一次性 Milky client 与 sender，执行本次
  Action 后在 `finally` 中关闭；不缓存连接、不重试、不改变副作用 Action 最多提交一次的语义。
- 运行时配置不可读时在网络访问前返回 `unsupported`，不创建 client。
- 抽取共用的 `outbound/lifecycle.py::close_quietly`，让 standalone sender 与 Tool 路径共享同一
  安全关闭语义。
- 两个贴纸语义工具保持原状：它们依赖当前 Milky task-local 会话，cron 中没有会话上下文时返回
  `unsupported` 属于正确语义，不是本次修复范围。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `qq-action-tools`：工具执行生命周期由「必须有已绑定 client」改为「优先 live client，否则一次性
  client」，并明确一次性路径的单次请求、资源关闭和配置不可读分类。
- `security-boundaries`：把「client 未绑定或已关闭」的失败前提更新为「一次性 client 的运行时配置
  不可读」。

## Impact

- 影响 `outbound/tools.py` 的固定 Action 执行路径、`outbound/standalone.py` 的关闭辅助和新增的
  `outbound/lifecycle.py`。
- 新增 `tests/test_tools_without_adapter.py`；移除 `tests/test_qq_tools.py` 中已过时的
  「未绑定即拒绝且不得建立 client」断言。
- 不修改 Hermes core，不新增 Action catalog、依赖或持久连接；注册阶段仍然无网络。
- 真实 cron worker 行为仍需在目标部署中验证，fake transport 与本地 loopback 结果不替代宿主验证。
