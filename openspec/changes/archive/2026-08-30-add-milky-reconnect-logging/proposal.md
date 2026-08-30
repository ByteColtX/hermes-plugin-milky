## Why

Milky SSE 事件流发生断连或进入退避重连时，运维日志目前无法清楚说明连接为何中断、何时会再次尝试以及重连是否成功，排查消息接收中断只能依赖底层异常。现在补充这组可观察日志契约，使断连和重连行为在不泄露凭证或消息内容的前提下可诊断。

## What Changes

- 为 Milky SSE `/event` 事件流增加断连日志，区分正常停止、可恢复断连和连接/协议错误等安全原因类别。
- 为每次退避重连增加英文日志，显示重连尝试序号、退避等待秒数和安全错误类别，并避免输出 token、Authorization、完整 URL、消息正文或媒体路径。
- 为重连成功增加英文日志，显示连接恢复及本次连接的尝试信息；主动取消期间不得记录为异常断连或继续安排重连。
- 为上述日志补充脱敏 fixture、结构化断言和断连—退避—成功/取消的回归测试，保持 handler 隔离和事件流资源释放契约不变。

## Capabilities

### New Capabilities

### Modified Capabilities

- `milky-event-stream`: 增加 SSE 断连、退避重连、重连成功和主动取消的可观察日志要求。

## Impact

- 影响 `milky/event_stream.py` 的运行时诊断边界及其测试、SSE fixture 和日志断言。
- 不改变 `/event` URL、认证、SSE 帧解析、handler 调度、退避算法或重连期间不恢复丢失事件/策略状态的既有契约；本 change 只使这些状态转移可观察。
- 不新增配置项、Milky Action、外部依赖或持久化状态。
