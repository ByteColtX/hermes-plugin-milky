# Proposal

## Why

固定 Action 工具的参数契约和执行约定分散在工具注册、出站与协议 module，近期新增资源临时链接工具仍需同时修改多处 interface。收拢共同规则和执行可以提高 locality，并保留已定义的工具行为。

## What Changes

- 固定工具执行 module 覆盖现有全部 26 个 Action，隐藏共同校验、生命周期降级、单次提交和原始响应交付，提高 depth 和调用方的 leverage。
- 工具注册依赖固定操作与参数的窄 interface，不向模型增加可调用入口。
- 保留各 operation 当前注册入口的省略、显式 null、false、类型和值域行为，非 Tool 继续使用既有响应校验；发现 schema、主规范与实际执行的差异时记录证据，不将修正混入纯重构。
- 通过注册工具的 interface 验证行为，替换被同等覆盖的内部转接测试。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。qq-action-tools、qq-group-action-tools 和 milky-http-actions 的行为保持；纯重构使用 skip_specs。

## Impact

影响 outbound/tools.py、outbound/sender.py、milky/client.py 的固定工具路径、相关测试与架构说明，保留 manifest 契约。不涉及媒体、两个贴纸语义工具、Dashboard、命令绑定、Tool 运行归属或 Hermes core；不开放任意 Action，不增加依赖、独立连接或持久状态。

源码和既有测试提供设计依据，未归档 change 不作为已交付前提。本轮仅规划，实施后本地与真实宿主证据分别记录。
