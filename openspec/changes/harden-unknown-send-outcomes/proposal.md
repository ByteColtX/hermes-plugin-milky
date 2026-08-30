## Why

一次 Milky `send_group_message` 已在服务端成功处理，但客户端在收到响应前将结果分类为 `transport_unknown`；Hermes Gateway 随后执行 plain-text fallback，导致同一回复再次发送。现有契约虽然禁止 Milky client 盲目重试，但没有把该边界明确传递到宿主 fallback，也没有覆盖“服务端完成请求而客户端丢失响应”的端到端回归场景。

## What Changes

- **BREAKING** 禁止对已经进入 HTTP 请求边界且结果为 `transport_unknown` 的消息发送执行 plain-text fallback、自动重试或隐式降级发送。
- 明确区分本地发送前格式化失败、远端确定拒绝和远端执行结果未知；只有能够证明原请求尚未发出的情况才允许安全降级。
- 在不修改 Hermes core 的前提下，要求 Milky adapter 在已验证的宿主发送分派边界实施一次性发送：不把“没有收到响应”解释为“没有发送”，也不进入通用 plain-text fallback。
- 将群禁言状态刷新与消息重发解耦：群发送失败后的 `MuteTracker` 刷新可以作为受控诊断或状态维护，但不得成为 fallback 的前置条件，也不得改变原始发送结果。
- 为连接、写入、读取、连接池和取消等传输阶段补充安全、可关联的诊断分类；不记录凭证、请求正文、原始异常、真实 ID 或敏感正文。
- 增加 fake transport、延迟响应和端到端出站回归，证明第一次服务端已接受时最终只产生一次用户可见消息，并验证私聊失败不触发群状态查询。

## Capabilities

### New Capabilities

无。本 change 收紧既有 HTTP Action 和出站消息的结果语义，不新增独立的用户能力。

### Modified Capabilities

- `milky-http-actions`: 补充传输阶段与远端执行未知的可观察边界，确保 POST Action 在无响应时保持 `transport_unknown` 且不暗示未执行。
- `outbound-messaging`: 明确 fallback/重试不得处理可能已产生副作用的未知发送结果，并保持原始错误和稳定结果语义。
- `mute-tracking`: 明确发送失败触发的群状态刷新不阻塞、不驱动消息重发，也不覆盖原始发送错误。

## Impact

- 影响 `milky/client.py`、`outbound/sender.py`、`state/mute_tracker.py` 及其 fake transport、出站和集成测试。
- 影响 Hermes Gateway `gateway.platforms.base` 的 fallback 兼容边界；本仓库只读核对该行为，并在 Milky adapter 的已验证发送分派边界完成兼容，绝不修改或要求修改 Hermes core。
- 需要新增脱敏传输阶段诊断和“服务端延迟完成、客户端结果未知”的协议 fixture；真实 Milky 写入复现仍需用户明确授权，不能把 live 消息或返回序号写入仓库。
- 不改变 Milky Action 路径、Bearer 认证、SSE、Gate/Will、Hermes media ownership、文件上传或三个显式 ToolSpec 的权限边界。
