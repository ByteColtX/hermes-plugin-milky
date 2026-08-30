# Slash command fixture

这些 event 和 Action fixture 只使用合成身份、合成消息序号和中性正文。成功的
`get_impl_info` fixture 保留顶层及 `data` 扩展字段，用于验证原始 JSON 交付；失败
fixture 只描述脱敏的分类或 HTTP 边界，不是 live 响应快照。

fixture 不包含 token、Authorization、真实身份、可访问 URL、本地路径、媒体正文或
原始 live 响应。
