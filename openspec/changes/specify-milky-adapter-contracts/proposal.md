## Why

本仓库目前只有 Milky 适配器骨架，行为契约散落在 `ARCHITECTURE.md`，还没有可由
OpenSpec 工具逐项验证的 feature spec。
现在先把目标能力拆成独立、可观察的规范，能在后续实现和评审中保持 Milky、Hermes、Gate、Will、媒体与安全边界一致。

## What Changes

- 初始化 OpenSpec 的项目配置和 Codex skills-only 工作流。
- 将当前架构基线拆成一个 capability 对应一个结构化 `spec.md` 的 active change。
- 为协议通信、事件流、canonical 入站、segment、Gate、Will、会话缓冲、禁言、媒体、Hermes 映射、出站和安全事件定义行为、场景与失败降级。
- 保留当前骨架未实现的事实；本次不实现运行时代码，不同步或归档到主 specs。

## Capabilities

### New Capabilities

- `plugin-lifecycle`: 唯一插件入口、初始化顺序、重连和停止生命周期
- `configuration`: 环境变量、URL 派生、嵌套 Will 配置、manifest 与脱敏
- `milky-http-actions`: HTTP Action 传输、envelope、错误分类和远端消息序号
- `milky-event-stream`: SSE `/event` 收帧、分发、重连、取消和退避
- `canonical-messages`: message_receive 场景、chat key、canonical record 与 TTL 去重
- `message-segments`: typed segment、mention/quote 信号、媒体引用和未知内容降级
- `inbound-gates`: Self、allowlist、mute 三道确定性硬门禁及其顺序
- `will-routing`: 借鉴 YesImBot 设计的 routing 决策与系统 nudge 边界
- `will-willingness`: 借鉴 YesImBot 设计的 willingness 状态、公式、概率与 reply cost
- `chat-session-buffer`: per-chat admission、有界 wait buffer 和 detached trigger batch
- `mute-tracking`: Bot 群禁言权威状态、事件更新和受控刷新
- `media-and-reply-resolution`: trigger 阶段资源/reply 补全与 Hermes media helper 边界
- `hermes-message-pipeline`: friend/group MessageEvent 映射和入站 turn 交接
- `outbound-messaging`: 目标路由、Milky segment、分块、文件上传和 SendResult
- `system-events-and-safety`: observe-only 系统事件、诊断和敏感信息安全边界

### Modified Capabilities

## Impact

- 新增 `openspec/config.yaml`、OpenSpec Codex skills 和本 change 的 15 份 delta spec。
- 不修改 Milky 运行时代码；后续实现仍须遵循本 change `tasks.md` 的 T01-T20 顺序和质量门禁。
- 未来归档会把已实现的 delta 合并到 `openspec/specs/<capability>/spec.md`；在此之前 active change 是这些目标能力的审查入口。
