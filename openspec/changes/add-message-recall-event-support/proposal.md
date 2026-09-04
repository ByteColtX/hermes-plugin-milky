## Why

当前适配器能够识别 `message_recall`，但只把它作为 observe-only 事件记录，不会让对应会话的后续 Agent 上下文知道哪条消息被撤回。补充受限的撤回事件上下文支持，可以保留现有不自动触发回复和不扩大权限的安全边界，同时让 Agent 在下一次同会话消息中获得可解释的事件信息。

## What Changes

- 校验 SSE 收到的 `message_recall` 事件，支持 `friend` 和 `group` 场景，并使用 `dm:<user_id>` 或 `group:<group_id>` 建立对应会话。
- 将字段完整且身份合法的撤回事件登记为对应会话的 context-only 记录，在下一次同会话 `trigger` 的 `channel_context` 中按 ingress 顺序注入一次。
- 为撤回记录定义稳定、安全的展示格式：群聊中无 `operator_id` 时显示 `uid <sender_id> 撤回了消息 msg_seq <message_seq>`，有 `operator_id` 时显示 `管理员 uid <operator_id> 撤回了 uid <sender_id> 的消息 msg_seq <message_seq>`；不把 `display_suffix` 或未知扩展字段直接放入上下文。
- 缺少场景、会话 ID、消息序号或发送者等必要字段时，记录 `malformed`/`unsupported` 安全诊断，不创建上下文记录。
- 保持 `message_recall` 不进入普通 `message_receive`、canonical、Gate、Will 或独立 Agent turn；不因收到撤回事件自动调用 `get_message`、`recall_group_message`、发送消息或修改权限。
- 增加合成事件 fixture、解析/上下文/pipeline/可观测性回归测试，并同步架构、README 和相关主规范。

## Capabilities

### New Capabilities

无。撤回事件属于现有系统事件观察与会话上下文能力的扩展。

### Modified Capabilities

- `system-events-and-safety`：将字段完整的 `message_recall` 纳入受限 context-only 注入，并定义字段、展示和安全边界。
- `chat-session-buffer`：允许撤回事件进入已有的有界系统事件缓冲，并按一次性 `channel_context` 语义交接。

## Impact

- 影响 `inbound/system_events.py`、`inbound/pipeline.py`、系统事件与上下文渲染测试，以及撤回事件 fixture。
- 影响 `ARCHITECTURE.md`、`README.md` 和上述 OpenSpec 主规范的系统事件清单与上下文行为说明。
- 不新增 Milky Action、ToolSpec、配置项或外部依赖，不修改 Hermes core，不改变现有主动撤回工具 `recall_group_message` 的出站行为。
- 撤回事件只提供事件元数据，不承诺恢复已撤回消息正文；是否能通过其他显式读取工具查询原消息仍属于独立能力。
