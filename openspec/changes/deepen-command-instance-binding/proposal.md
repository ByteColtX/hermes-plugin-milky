# Proposal

## Why

命令依赖的 client、白名单管理者和状态观察者分别登记与撤销，调用方承担归属、开放时机和代次关系。集中这些约定可减少生命周期知识的分散。

## What Changes

- 实例绑定 module 统一拥有归属、唯一实例选择、运行代次和撤销规则。
- 通过登记实例、确认就绪与撤销的窄 interface 隐藏各用途的内部集合。
- 保留启动中的本地状态观察与完成同步后协议访问的不同时机。
- 通过命令和连接的 interface 验证多实例、迟到读取和管理关联失效。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。slash-commands、plugin-lifecycle 和 hot-chat-allowlist 行为保持，纯重构使用 skip_specs。

## Impact

影响 slash_commands.py、adapter.py 的命令绑定路径、相关测试与架构说明。静态帮助、回执、profile 校验和 core 授权保持。不涉及连接资源重建、pipeline、Dashboard、Tool 或 Hermes core，不增加依赖。

源码与本地测试是设计依据，未归档规划不纳入实施前提。实施后的真实 Hermes 集成仍待确认。
