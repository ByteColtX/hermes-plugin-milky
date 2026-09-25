# OpenSpec

本目录按 [OpenSpec](https://github.com/Fission-AI/OpenSpec) 管理插件的行为规范和功能变更。

## 模型

- `specs/`：当前系统行为的事实来源。
- `changes/`：一个变更的提案、delta spec、设计和任务。
- `changes/archive/`：已完成变更的历史；归档时 delta spec 合并到 `specs/`。

## 主规范导航与职责

主规范描述当前已确认契约；源码、测试及 evidence 证明交付状态。未归档 change 保留目标增量，
不得因整理而提前写入主规范。稳定模块所有权见 [ARCHITECTURE.md](../ARCHITECTURE.md)，安装和使用说明见 [README.md](../README.md)。

| 范围 | 主规范 | 主要职责 |
|---|---|---|
| 生命周期 | [plugin-lifecycle](specs/plugin-lifecycle/spec.md) | 注册、连接就绪、停止、重连及各入口资源所有权 |
| 配置 | [configuration](specs/configuration/spec.md) | 来源优先级、字段类型、默认值、校验及保存与生效 |
| HTTP | [milky-http-actions](specs/milky-http-actions/spec.md) | POST、认证、非 Tool 响应校验与传输错误 |
| 事件流 | [milky-event-stream](specs/milky-event-stream/spec.md) | SSE 分帧、空闲、重连和取消 |
| 消息身份 | [canonical-messages](specs/canonical-messages/spec.md) | canonical、chat key、稳定序号和去重身份 |
| 消息内容 | [message-segments](specs/message-segments/spec.md) | 入站 segment 语义、正文和引用占位 |
| 入站编排 | [hermes-message-pipeline](specs/hermes-message-pipeline/spec.md) | 去重、门禁、命令、Will、资源与宿主交接顺序 |
| 入站门禁 | [inbound-gates](specs/inbound-gates/spec.md) | 自身消息、白名单、禁言拒绝及短路效果 |
| 在线白名单 | [hot-chat-allowlist](specs/hot-chat-allowlist/spec.md) | 显式管理、持久化、发布、撤销与规则回执 |
| 群禁言 | [mute-tracking](specs/mute-tracking/spec.md) | 初始同步、按需准备、事件与刷新状态 |
| 路由触发 | [will-routing](specs/will-routing/spec.md) | 确定性 wait/trigger、关键词与优先级 |
| 意愿触发 | [will-willingness](specs/will-willingness/spec.md) | 分数、衰减、概率、force 与扣分 |
| 等待上下文 | [chat-session-buffer](specs/chat-session-buffer/spec.md) | 有界历史、原子 drain、系统上下文合并与展示 |
| 入站资源 | [media-and-reply-resolution](specs/media-and-reply-resolution/spec.md) | trigger 后资源补全、Hermes helper 和失败占位 |
| 系统事件 | [system-events-and-safety](specs/system-events-and-safety/spec.md) | 事件观察、撤回、成员通知及非授权边界 |
| 命令 | [slash-commands](specs/slash-commands/spec.md) | core 分发、命令入口、帮助、中文回执与运行状态 |
| 出站 | [outbound-messaging](specs/outbound-messaging/spec.md) | 目标、segment、forward、媒体、文件及发送结果 |
| 文本分段 | [outbound-message-splitting](specs/outbound-message-splitting/spec.md) | SPLIT 语法、转义、长度预检与投递顺序 |
| 默认投递 | [home-channel-delivery](specs/home-channel-delivery/spec.md) | 系统与 cron 的默认目标及 live/standalone 投递 |
| Agent 控制 | [agent-facing-message-controls](specs/agent-facing-message-controls/spec.md) | CQ 控制语法、真实 ID 来源及模型选择 |
| 平台提示 | [milky-platform-prompt-guidance](specs/milky-platform-prompt-guidance/spec.md) | platform hint、操作指引 section 与 Bot 身份 |
| 会话提示 | [milky-session-context-prompt](specs/milky-session-context-prompt/spec.md) | 场景 metadata 白名单、快照、prompt 缓存与恢复 |
| Action 工具 | [qq-action-tools](specs/qq-action-tools/spec.md) | 完整固定目录、转发/私聊文件/好友管理参数及行为 |
| 群 Action 工具 | [qq-group-action-tools](specs/qq-group-action-tools/spec.md) | 群文件、入群请求、邀请和专属头衔 |
| 贴纸维护 | [qq-sticker-maintenance](specs/qq-sticker-maintenance/spec.md) | 命令/Web 共享校验、视觉、字段维护、持久化及修复 |
| 贴纸搜索 | [qq-sticker-search](specs/qq-sticker-search/spec.md) | 只读检索、排序、有界结果及备选 |
| 贴纸发送 | [qq-sticker-send](specs/qq-sticker-send/spec.md) | 选择、文件校验、发送前统计与单次发送 |
| Web 管理 | [milky-web-dashboard](specs/milky-web-dashboard/spec.md) | 认证/profile、配置页面、上传批次、任务与资源限制 |
| 信息边界 | [security-boundaries](specs/security-boundaries/spec.md) | raw 保真、Action Tool 响应、资源所有权及合成资料 |
| 可观测性 | [adapter-observability](specs/adapter-observability/spec.md) | 日志字段、级别、关联 ID 与各阶段终态 |

## 主规范维护

- 每项行为选定主要定义位置；其他规范说明自身入口的可观察约束并链接主定义，避免复制整套业务规则。
- Requirement 标题反映当前行为，场景放在直接约束它的 requirement 下。正文不使用“本 change”或“未来已交付功能”等历史视角。
- 合并条款时保留独有的前置条件、结果、错误分类和场景；先核对实现、测试与 evidence，再修正契约分歧。
- 调整 requirement 名称或场景归属时，同时核对所有未归档 delta 的 MODIFIED/REMOVED/RENAMED 引用及完整场景集合，避免同步时恢复旧基线。
- 已归档 change 保留历史原文。纯规范整理不修改实现、不勾选功能任务，也不把规划状态改成已交付。
- 严格校验只证明格式及可检查的引用约束；交付前还须检查语义一致性、相对链接与场景保全。

本次整理的语义依据、场景映射和验证结果见 [2026-09-26 整理记录](maintenance/2026-09-26-spec-cleanup.md)。

## 工作流

官方流程是“先达成共识，再实现”：

```text
explore → propose → apply → sync/archive
```

本项目 Codex skill 的调用名如下；`openspec ...` 在终端运行，`$openspec-*` 在 AI
对话中运行：

```text
$openspec-explore
$openspec-propose <change-name>
$openspec-apply-change <change-name>
$openspec-update-change <change-name>
$openspec-sync-specs <change-name>
$openspec-archive-change <change-name>
```

## Change 文件

```text
changes/<change-name>/
├── proposal.md   # 为什么改、改什么
├── specs/        # ADDED/MODIFIED/REMOVED 的 delta
├── design.md     # 如何实现
└── tasks.md      # 实施清单
```

变更可以随时迭代。规范描述可观察行为和具体场景，不描述实现细节。

## 校验

```text
openspec status --change <change-name>
openspec validate --changes --strict
openspec validate --specs --strict
```

参考：[Getting Started](https://github.com/Fission-AI/OpenSpec/blob/main/docs/getting-started.md) ·
[Overview](https://github.com/Fission-AI/OpenSpec/blob/main/docs/overview.md) ·
[CLI](https://github.com/Fission-AI/OpenSpec/blob/main/docs/cli.md)
