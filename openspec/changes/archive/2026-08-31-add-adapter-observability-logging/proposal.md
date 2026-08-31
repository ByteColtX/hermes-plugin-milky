## Why

现有日志已经覆盖 Milky 适配器的主要生命周期和消息路径，但全量复核发现日志契约没有明确区分固定人类可读文本与结构化字段。MuteTracker 扫描汇总因此把同一组统计字段打印两次，部分自定义消息还重复输出 `[Milky]` 前缀，并绕过了统一字段脱敏边界。多个错误路径的事件名也不能准确表示实际失败阶段，增加了运维检索和安全审计风险。

## What Changes

- 将本 change 扩展为一次全量运行时日志审计和一致性重构，覆盖 adapter、HTTP Action、SSE、inbound、resource、outbound、MuteTracker 以及共享日志边界。
- 建立单一渲染来源：人类可读文本只使用固定事件标签，动态诊断值只作为经过白名单验证和脱敏的结构化字段输出；同一语义字段在人类可读消息中最多出现一次。
- 移除调用方预格式化动态日志消息的约定，修正 MuteTracker 的扫描汇总、身份、群状态和 TTL 日志，保留既有冷启动所需的 UID、nickname、群状态和汇总计数语义。
- 统一事件所有权和命名，修正 component close、fatal error report、SSE frame 和 handler 失败之间的错误归类，避免一个状态被多个层伪装成不同终态。
- 收紧异常、数字 ID、nickname、禁言状态和组件标识的安全字段边界；远端错误不输出原始异常、请求、响应或路径，traceback 只有在完整安全检查通过时才允许记录。
- 对所有运行时日志调用点建立审计清单、caplog 回归、真实 MuteTracker 扫描测试、静态直接 logger 检查、敏感输入扫描和非阻塞日志测试。
- 保持 Milky 协议、SSE 重连、Gate/Will、Hermes media ownership、SendResult、工具权限和 CLI smoke 输出语义不变；不新增日志配置、后端或真实 Milky 写入 Action。

## Capabilities

### New Capabilities

- `adapter-observability`: 定义 Milky 适配器跨模块日志的单一渲染来源、事件归属、字段白名单、级别、限噪和脱敏行为。

### Modified Capabilities

- `milky-event-stream`: 区分已接收帧的 handler 失败与帧解析丢弃，并保持安全重连日志。
- `plugin-lifecycle`: 统一冷启动身份、禁言扫描、组件关闭和 fatal error report 日志的字段与事件语义。
- `system-events-and-safety`: 收紧自定义消息、异常链、事件观察和日志输出的安全边界。

## Impact

- 影响 `milky/observability.py` 及 `adapter.py`、`milky/client.py`、`milky/event_stream.py`、`inbound/`、`milky/resources.py`、`outbound/`、`state/mute_tracker.py` 的日志调用和安全字段定义。
- 影响 `tests/test_observability.py`、`tests/test_mute_tracker.py`、`tests/test_milky_event_stream.py` 及新增的日志审计 fixture/回归断言。
- 仅修改本 change 已存在的 planning artifacts；实现阶段由 `$openspec-apply-change` 按新增 tasks 执行，完成后需重新验证并更新证据台账。
