## Why

当前 Milky 已将入群、退群及其他受支持系统事件写入对应会话的 `channel_context`，但事件 body 仍使用中文，和英文 Agent 上下文不一致；成员变化也没有独立的通知策略。需要让默认行为保持低副作用，同时在显式开启通知时及时提醒 Agent。

## What Changes

- 增加启动配置 `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS`，默认关闭；成员增加/减少事件仍写入对应群聊的 system context，但关闭时只使用不带 `Tip` 的基础英文 body，并等待下一次普通消息触发消费。
- 开启通知时，仅对入群/退群 body 在末尾附加固定英文 `Tip`，并立即消费该群待处理的 system context，触发一次 Hermes Agent turn。
- 开关只改变成员增加/减少事件的 Tip 和即时触发策略；戳一戳、撤回等其他系统事件继续按现有 observe-only/context-only 边界处理。
- 将所有会进入 `<event ...>` 的 body 改为固定英文，包括 nudge、member change 和 message recall。
- `inject_message` 无法获得有效会话或被 Hermes 拒绝时，必须保留缓冲内容并记录安全诊断，不因即时触发失败丢弃事件。
- 保持基础事件的 context-only 安全边界；即时通知只通过 Hermes 已有会话注入接口触发，不修改 Hermes core system prompt，不直接调用 Milky 出站 Action。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `system-events-and-safety`：修改成员事件的配置开关行为及所有 `<event ...>` body 的可观察英文格式。

## Impact

- 配置解析需要新增一个启动期布尔字段及安全摘要字段，pipeline 需要在成员事件渲染和 system context 消费前应用该配置。
- `inbound/system_events.py` 的固定渲染文案、成员事件 Tip 和相关 context fixture/test 需要更新。
- Hermes 注入交接需要传递已确认的 gateway session key 和注入结果；不得从 `group:<id>` 猜测 Hermes session key。
- `openspec/specs/system-events-and-safety/spec.md` 需要补充开关、英文模板、Tip 内容、禁用行为及既有安全边界。
- 不新增网络接口、Milky Action 或 Hermes core 依赖；变更会在通知显式开启且注入成功时产生一个正常 Agent turn。
