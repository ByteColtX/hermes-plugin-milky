# Spec Delta

## MODIFIED Requirements

### Requirement: 结果分类和生命周期

成功返回 `status=sent` 和 Milky `message_id`，不得返回内部 `sticker_id`；没有候选返回 `no_match`。参数、上下文、文件、存储、协议拒绝、HTTP、malformed 和 transport unknown MUST 使用固定机器可读分类。注册、连接、SSE、普通 Agent 输出和 disconnect MUST 不打开贴纸 store、扫描 library、创建检索后台任务或执行网络 I/O；`jieba` 作为正常运行时依赖随插件模块加载，不得在 Tool discovery 中按需导入。过期 definition 和未连接 sender MUST fail closed。

查询发送模式没有足够匹配证据时 MUST 返回 `status=no_match` 和 `alternatives` 数组。当原查询同时包含 `intent` 与至少一个 `emotion` 或 `tags` 时，该数组 MUST 包含至多 5 个当前可见、文件有效的备选；备选 MUST 忽略 `intent` 匹配条件、保留显式 `emotion` 精确筛选和 `tags` 至少命中一个的条件，并按命中的请求 tag 数量降序、再按不透明 `sticker_id` 字典序稳定排序。其他无匹配情形 MUST 返回 `alternatives=[]`。每个备选 MUST 只包含 `sticker_id`、`emotion`、`tags` 和 `description`，不得包含路径、URL、hash、图片内容、统计或匹配解释。备选不是原查询的匹配结果；`sticker_send` MUST 不据此选择或发送贴纸，也不得更新使用统计。工具结果序列化 MUST 保留 `no_match` 的备选字段。

#### Scenario: 未连接 sender

- **WHEN** 过期 definition 或未连接 sender 调用 `sticker_send`
- **THEN** Tool SHALL fail closed 且不得创建旁路连接

#### Scenario: 严格发送无匹配时返回有限备选

- **WHEN** 查询模式的 `sticker_send` 没有足够匹配证据，且原查询同时包含 `intent` 与 `emotion` 或 `tags`
- **THEN** Tool SHALL 返回 `status=no_match` 和最多 5 个明确标为备选的当前可用条目
- **AND** SHALL 不发送消息、不更新使用统计，且不得声称备选满足原 intent
- **AND** 只有 Agent 显式选中某个 `sticker_id` 并再次调用工具时，才可进入精确发送路径

#### Scenario: 只有 intent 无匹配时不伪造相关备选

- **WHEN** 查询模式只提供 `intent` 且没有足够匹配证据
- **THEN** Tool SHALL 返回 `status=no_match` 和 `alternatives=[]`
- **AND** 插件 SHALL 不自动浏览或发送其他条目

#### Scenario: 发送 Action 结果不确定时插件不自动重试

- **WHEN** `sticker_send` 返回 `http_error`、`malformed` 或 `transport_unknown`
- **THEN** 插件 SHALL 返回对应固定分类，且本次调用不自动再次发送或改发另一张贴纸
- **AND** 工具定义和 bundled skill SHALL 仅说明通用接口和结果语义，不规定调用方的后续对话或搜索策略
