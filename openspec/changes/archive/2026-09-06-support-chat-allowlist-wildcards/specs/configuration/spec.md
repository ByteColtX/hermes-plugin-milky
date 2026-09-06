## ADDED Requirements

### Requirement: MILKY_ALLOWED_CHATS 支持命名空间通配符

适配器启动时 SHALL 接受 `MILKY_ALLOWED_CHATS` 中的完整 `group:<十进制群号>`、
`dm:<十进制 QQ 号>`、`group:*` 和 `dm:*` 条目；条目两端的空白 SHALL 被裁剪，重复条目
SHALL 归一化。`group:*` SHALL 表示所有合法 group chat，`dm:*` SHALL 表示所有合法 friend
chat；通配符 SHALL 只在完整条目中出现。除上述格式外的通配符、未知场景、空 ID、负数、
额外分隔符和空条目 MUST 使启动失败并指出安全的 `MILKY_ALLOWED_CHATS` 配置错误类别。
空值或未配置时 SHALL 保持空白名单语义，不因该配置拒绝合法 friend/group 消息。

#### Scenario: 混合具体条目和通配符

- **WHEN** `MILKY_ALLOWED_CHATS` 配置为 `group:123, dm:* , dm:*`
- **THEN** 启动 SHALL 成功
- **AND** 解析后的白名单 SHALL 保留 `group:123` 和 `dm:*` 两种授权规则
- **AND** 重复的 `dm:*` SHALL 不产生额外规则

#### Scenario: 通配符按命名空间生效

- **WHEN** `MILKY_ALLOWED_CHATS` 配置为 `dm:*`
- **THEN** 任意合法 `dm:<十进制 QQ 号>` 消息 SHALL 被白名单规则允许
- **AND** 任意合法 `group:<十进制群号>` 消息 SHALL 不因该 `dm:*` 条目被允许

#### Scenario: 非法通配符被拒绝

- **WHEN** `MILKY_ALLOWED_CHATS` 包含 `dm:**`、`group:12*`、`*:123` 或 `private:*` 等非完整通配符条目
- **THEN** 启动 SHALL 失败并指出 `MILKY_ALLOWED_CHATS` 的安全配置错误类别
- **AND** SHALL 不将非法条目静默转换为具体 chat key、`dm:*` 或 `group:*`

#### Scenario: 空白名单保持原有语义

- **WHEN** `MILKY_ALLOWED_CHATS` 未配置或为空字符串
- **THEN** 配置 SHALL 产生空白名单
- **AND** 合法 friend/group 消息 SHALL 不因 ChatAllowlist 被拒绝
