# Proposal

## Why

Milky Tool 的响应目前经过插件侧 envelope 解析、敏感字段过滤、容器冻结、最小结构校验和 JSON 重建，部分结果因此不能完整到达 Hermes。Hermes core 还会在插件 handler 之后运行 `transform_tool_result`，所以需要明确插件 raw passthrough 边界，并把最终模型可见结果的原样保证作为 Hermes core 的外部前置依赖。

## What Changes

- **BREAKING** 已注册 Milky Tool 只要取得远端响应体，就把其协议结果和未知字段原样交给 Hermes core；插件不再过滤 `token`、`authorization` 等字段，不把数组转换为其他容器，不重建或摘要 envelope。
- **BREAKING** 不再把远端协议拒绝、HTTP 错误或其他可获得响应改造成插件自有固定结果；没有可获得远端响应时，才使用 `transport_unknown` 或既有本地错误分类。
- 保留 Tool 参数校验、固定 operationId、认证、单次副作用 Action、生命周期绑定和安全日志；日志继续只记录低基数元数据，不复制响应体。
- 明确 Hermes core 的 `transform_tool_result` 是插件之后的结果变换边界；插件不注册、拦截或反向覆盖该 hook。
- 将 Hermes core 的 Tool 结果规范化/错误字段截断和 `transform_tool_result` opt-out 列为外部依赖；只有 core 跳过这些变换时，才能保证最终进入模型上下文的结果仍与 Milky 响应一致。
- 增加 fake Hermes/Milky 证据，分别验证插件到 core 的原样交付、无 hook 时的最终结果，以及存在 core transform 时的边界差异。

## Capabilities

### New Capabilities

无。本 change 收敛既有 Milky Tool 的结果交付边界，不新增 Tool 或 Milky operationId。

### Modified Capabilities

- `security-boundaries`: 将 Tool raw 结果从“成功 envelope 原样交付”扩展为“任何可获得的远端响应原样交付”，并明确 Hermes core 后置变换边界。
- `qq-action-tools`: 移除插件把远端拒绝和可获得错误响应统一改造成固定结果的要求，保留无响应、本地输入错误和安全日志边界。
- `qq-group-action-tools`: 对群文件、群请求和群管理 Tool 采用相同的响应透传语义，保留显式调用、单次副作用和无响应分类。

## Impact

- 主要影响 [`milky/parser.py`](/Users/bytecolt/PythonProjects/hermes-plugin-milky/milky/parser.py)、[`milky/client.py`](/Users/bytecolt/PythonProjects/hermes-plugin-milky/milky/client.py)、[`outbound/sender.py`](/Users/bytecolt/PythonProjects/hermes-plugin-milky/outbound/sender.py) 和 [`outbound/tools.py`](/Users/bytecolt/PythonProjects/hermes-plugin-milky/outbound/tools.py) 的 Tool 响应路径及其测试 fixture。
- 需要与 Hermes core 的 Tool registry 和 [`transform_tool_result`](/Users/bytecolt/PythonProjects/hermes-agent/model_tools.py:834) 行为协同；本 change 不修改 Hermes core，只记录其 opt-out 能力为外部依赖和验证边界。
- 入站事件解析、普通消息上下文、日志内容、资源下载权限、Tool allowlist 和副作用调用次数不在本 change 内改变。
- 真实 Hermes host、真实 Milky 响应和可能产生副作用的 Action 仍不自动验证；相关证据使用 fake host、fake transport 和合成 fixture。
