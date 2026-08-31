## Context

See `proposal.md` for the motivation. 当前 Milky client 已能将连接、写入、读取和超时等传输异常收敛为 `transport_unknown`，出站 sender 也能保留该分类；但 Hermes Gateway 的通用发送边界仍可能把未知结果当作可降级失败，继续发起 plain-text fallback。用户提供的脱敏服务端日志证明：第一次群消息已经完成，客户端却先报告未知，随后产生了第二次 fallback 消息；同一错误路径还触发了 MuteTracker 的成员状态刷新。

本 change 受项目边界约束：Milky plugin 不修改 Hermes core，不引入 Milky 端幂等键，也不通过查询历史消息猜测一次 POST 是否已经执行。一次可能产生副作用的 HTTP 请求在响应丢失后无法由客户端单独证明 exactly-once，只能选择安全的未知结果语义。

## Goals / Non-Goals

**Goals:**

- 建立从 Milky Action 到 Hermes 出站边界的一致结果语义，确保 `transport_unknown` 是终态而不是 fallback 条件。
- 让本地格式化拒绝、远端明确拒绝、传输未知和成功结果可被下游区分，并保持原始安全错误返回。
- 让群禁言刷新成为独立、受锁/冷却/并发上限保护的只读维护任务，不阻塞或驱动消息再次发送。
- 以脱敏阶段字段和延迟响应 fixture 复现“服务端成功、客户端未知”的边界，并验证最终只产生一次用户可见消息。
- 验证 MilkyAdapter 的一次性发送覆盖能在不修改 Hermes core 的情况下隔离宿主通用 fallback。

**Non-Goals:**

- 不在插件中实现消息去重服务、持久化发送记录、远端幂等键或发送后的历史查询补偿。
- 不把 `transport_unknown` 改成成功或确定失败，也不通过增加一次重试来提高表面成功率。
- 不修改 Milky API、SSE、Gate/Will、Hermes Agent busy 调度、媒体所有权或文件上传协议。
- 不直接编辑、请求修改或依赖 `../hermes-agent` 或其他 Hermes core 仓库；没有可验证的 adapter delivery hook 时必须记录为 blocked。

## Decisions

### 1. 将未知结果定义为不可重入的出站终态

出站发送边界采用以下决策表：

| 结果 | 是否已进入网络边界 | 用户可见动作 | 是否允许 fallback/重试 |
|---|---:|---|---:|
| 本地输入/格式化拒绝 | 否 | 返回本地错误 | 否，未产生可安全降级的请求 |
| 远端明确拒绝 | 是 | 返回 `rejected`/对应安全分类 | 默认否；除非未来有明确幂等契约 |
| 传输结果未知 | 是 | 返回 `transport_unknown` | 否 |
| 成功且有远端序号 | 是 | 返回成功和 `message_seq` | 否 |

选择不可重入的未知终态，是因为 `send_group_message` 和 `send_private_message` 都是有副作用的 POST。继续 fallback 无法判断第一次请求是否已执行；本次服务端日志已经展示了该风险。相比可能丢掉一次回复，重复发送会造成不可逆的用户可见副作用，因此默认采用安全停止。

备选方案是自动等待更久、再次查询消息或重试一次。等待和查询不能证明缺失响应对应的消息，重试会再次产生副作用，且 Milky v1.3 未确认通用幂等契约，因此不采用。

### 2. 用 adapter 一次性发送边界阻止通用 fallback

插件侧继续使用现有的安全错误分类和 `retryable=False` 语义，不以错误字符串或 fallback 文本猜测宿主行为。当前运行版本的 Hermes Gateway 经只读核对后，会动态调用 adapter 的 `_send_with_retry()`；MilkyAdapter 必须覆盖该边界，并仅调用一次 `self.send()` 后原样返回结果，绝不调用 `super()`、自动重试或 plain-text fallback。

该策略适用于所有 Milky 出站消息，而不只根据 `transport_unknown` 的正文、时间窗或消息内容作拦截：Milky 的发送 Action 是有副作用 POST，已确认的本地格式化失败和远端拒绝同样不应被宿主改写为另一条用户可见消息。该覆盖是经实际宿主动态分派验证的 adapter-local 行为，不是 monkey patch、替换或修改 Hermes core。

备选方案是在 plugin 内吞掉未知异常并报告成功，或把结果伪装成 timeout 以触发宿主已有分支。两者都会隐藏真实交付状态或依赖错误文本，破坏 SendResult 和安全诊断契约，因此不采用。

### 3. 传输阶段只增加安全诊断，不泄露底层异常

Milky client 在保持顶层 `transport_unknown` 的同时，为连接建立、请求写入、响应读取、连接池和未知阶段提供有限枚举的诊断字段。异常原文、URL、请求 body、Authorization、响应正文和真实身份继续被禁止写入日志或结果。显式生命周期取消继续走取消边界，不伪装成普通业务成功；若请求已发出，宿主也不得因取消/未知而 fallback。

选择阶段枚举而不是记录异常文本，是为了在排查本次“约 7ms 客户端未知、服务端约 789ms 完成”的差异时提供足够的连接/代理证据，同时维持既有安全边界。阶段信息不能证明远端是否执行，只能缩小传输故障范围。

### 4. MuteTracker 刷新与发送结果解耦

群发送失败仍可触发 `MuteTracker` 的受控刷新，因为发送失败可能暴露过期的 Bot 成员禁言状态；但刷新是只读维护，不得成为 fallback 的前置条件，也不得覆盖原始 SendResult。刷新任务必须受每群锁、冷却和全局并发上限限制，并纳入 adapter 停止时的任务清理。

本设计优先让出站调用先确定并返回 `transport_unknown`，再 best-effort 调度状态刷新，避免像本次日志一样先等待成员查询再进行错误重发。备选方案是完全取消失败后的刷新，会失去发现状态漂移的机会，与现有 MuteTracker 契约不一致，因此不采用。

### 5. 用延迟响应 fixture 验证“服务端成功、客户端未知”

测试 transport 应能记录请求已经到达服务端、延迟返回成功 envelope，或在服务端完成后模拟客户端响应路径中断。测试断言客户端返回 `transport_unknown`，sender 只产生一次 send Action，宿主 fallback 不被调用；同时可独立断言群刷新至多产生一次 `get_group_member_info(no_cache=true)`，且不会改变发送结果。真实日志只作为脱敏字段形状和时序证据，不进入 fixture。

## Risks / Trade-offs

- [第一次请求确实未执行时，未知结果策略可能导致一次回复没有送达] → 通过安全诊断、人工重试入口或下一次用户消息触发恢复；不以自动重发换取重复消息风险。
- [Hermes Gateway 改变 adapter 发送分派边界] → 用实际 MilkyAdapter 回归锁定一次性发送行为；若未来没有可验证的 adapter seam，明确阻塞，不用 monkey patch、文本匹配或消息去重绕过。
- [传输阶段枚举仍无法定位所有代理或服务端问题] → 同时记录安全耗时、阶段和本地关联 ID，并要求对齐 Milky 服务端毫秒日志；不记录敏感请求内容。
- [异步 MuteTracker 刷新可能在适配器停止时仍运行] → 统一登记刷新 task，使用取消和并发槽清理；刷新失败保留既有状态，不改写为 unmuted。
- [对远端明确拒绝也不自动 fallback 会减少部分兼容性] → 只有未来确认请求未产生副作用且存在幂等/降级契约时，才单独增加允许条件；当前发送 Action 默认不重发。

## Migration Plan

1. 先补齐脱敏 transport phase、请求关联和延迟响应 fake fixture，并验证现有 `transport_unknown` 分类仍保留。
2. 审查实际 Hermes Gateway 的 fallback 入口和 adapter 动态分派；在 MilkyAdapter 覆盖一次性发送边界，原样返回未知结果而不调用宿主通用 retry/fallback。
3. 修改 plugin 出站失败处理，使未知结果直接返回，并把 MuteTracker 刷新改为独立受控任务；补充实际 adapter、group/dm、明确拒绝、格式化失败、取消和并发失败测试。
4. 运行相关单元/集成测试、`uv` 质量门禁和 OpenSpec strict validation；只使用合成延迟服务验证副作用边界，不执行未经明确授权的真实写入 Action。
5. 部署后观察同一关联 ID 下的 Action 结果、刷新和 fallback 计数；确认不再出现未知结果之后的第二次 send Action。回滚时只能恢复旧行为用于诊断，不应在生产默认重新开启未知结果重发。

## Open Questions

无。具体底层异常类型仍需通过新增安全阶段诊断和宿主/代理日志确认，但不会改变本 change 已确定的未知结果不得 fallback 或重试的行为契约。
