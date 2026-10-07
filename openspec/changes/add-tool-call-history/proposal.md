# Proposal

## Why

Milky 工具当前的运行日志只记录工具名、结果分类和耗时，无法按时间查看一次调用实际用了哪个 QQ 工具及其安全参数摘要。持久化历史与只读统计可以帮助操作者了解工具用法、调用频率和耗时，同时保留 QQ 响应与自由文本的现有数据边界。

## What Changes

- 观察 Hermes 的 `post_tool_call` 事件，只接收本插件声明的 Milky/QQ 工具调用；不注册审批或拦截逻辑。
- 为每条观察到的调用保存 UTC 观察时间、耗时、工具名、受限状态分类，以及按各工具参数 schema 白名单生成的安全参数摘要。保留有助于理解目标和选项的数值 QQ ID、序号、数量、布尔选项及贴纸 ID；其他参数只标示是否提供，不保存其原值。
- 不持久化原始参数对象、完整 Tool 结果、自由文本错误、middleware trace、凭证、URL、路径、媒体引用或文件内容。Tool 结果可能是 Milky 的不透明远端响应，因此记录的状态只表示 Hermes 观察到的 Tool 状态，不表示 QQ 业务已成功。
- 在现有受认证的 Dashboard 中提供按 profile 隔离的只读历史、时间/工具/状态筛选和分页，并显示调用总数、各工具与状态分类计数及耗时统计。
- 每个 profile 最多保留 30 天或 10,000 条记录，以先达到者为准；超出范围的最早记录自动清理。
- 历史依赖 Hermes 的观察 hook；hook 未触发、超时或写入失败时可能缺少记录，页面和规范不把它描述成完整取证台账。

## Capabilities

### New Capabilities

- `tool-call-history`: 记录、保留、统计和按 profile 查询 Milky/QQ 工具调用的安全历史。

### Modified Capabilities

- `milky-web-dashboard`: 增加受认证、按 profile 隔离的只读工具调用历史和统计视图。

## Impact

影响插件的 Hermes hook 声明与注册、profile 作用域内的本地持久化、Dashboard 查询接口和页面。现有 Tool 结果交付及运行日志边界保持不变；不增加审批流程，也不要求修改 Hermes core。
