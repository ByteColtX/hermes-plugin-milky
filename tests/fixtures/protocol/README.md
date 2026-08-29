# Milky 协议 fixture

这些 fixture 是 T03 的脱敏协议输入，不是 live 响应快照。数字身份、消息序号、资源 ID、文件名和正文均为合成值，内容为中性测试内容。

- `actions/` 保存带有 `status`、`retcode` 和 Action 专属 `data` 层级的 JSON 响应。
- `events/` 保存单个外层事件 JSON；其中 `message_receive` 覆盖 friend、group、temp 和未知 segment。
- `sse/` 保存原始 SSE 帧，用来区分外层 `milky_event` 和 data 内的业务 `event_type`。
- `expected/` 保存 fixture 的预期分类和 T04 parser 使用的边界断言。

资源 URL、头像 URL 和市场表情 URL 使用空字符串表示已脱敏字段；这不代表可访问地址。fixture 不包含 token、Authorization header、真实 QQ 号、真实媒体路径或敏感正文。
