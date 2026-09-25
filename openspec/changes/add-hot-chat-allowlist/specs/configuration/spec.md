# Spec Delta

## MODIFIED Requirements

### Requirement: 启动时解析正式配置契约

适配器 MUST 按本规范的来源优先级在启动时解析配置。经过 Hermes core 允许的白名单管理指令 SHALL 按 hot-chat-allowlist 契约持久化并在线更新入站白名单；其他配置仍为启动快照。以下 MILKY_* 名称表示对应配置及其兼容环境输入，相同校验 SHALL 适用于最终选中的原生类型设置；必需连接地址可来自任一合法普通配置来源，凭证来自宿主凭证机制。 `MILKY_BASE_URL`、`MILKY_ACCESS_TOKEN` 和可选的
`MILKY_ALLOWED_CHATS`、`MILKY_WILL_POLICY`、`MILKY_SESSION_BUFFER_SIZE`、`MILKY_HOME_CHANNEL`、
`MILKY_MAX_LOCAL_MEDIA_BYTES`、`MILKY_LONG_TEXT_FORWARD_THRESHOLD` 和
`MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` SHALL 共同构成启动配置；`MILKY_MAX_LOCAL_MEDIA_BYTES` SHALL 是表示字节数的十进制整数，
取值范围 SHALL 为 `8 MiB` 至 `32 MiB`（含边界），所有来源均省略该项时 SHALL 使用 `33554432`；缺失必需值、
类型错误、范围错误或 home channel 目标格式错误 MUST 使启动失败。

#### Scenario: 缺少必需配置

- **WHEN** 所有合法来源均未提供必需的连接地址或宿主凭证
- **THEN** 启动 SHALL 失败并指出缺少的配置名
- **AND** 错误 SHALL NOT 包含 token 值

#### Scenario: 使用默认出站资源上限

- **WHEN** 所有普通配置来源均未提供本地出站资源上限
- **THEN** 配置 SHALL 保存 `33554432` 字节作为本地出站资源上限
- **AND** 该默认值 SHALL 供图片、语音、视频、文档和 CQ sticker 的本地出站路径使用

#### Scenario: 使用自定义出站资源上限

- **WHEN** 按优先级选中的本地出站资源上限是范围内的整数（环境输入使用十进制文本），例如 `16777216`
- **THEN** 配置 SHALL 保存该数值
- **AND** 出站本地资源 SHALL 按该值判断是否超限

#### Scenario: 非法出站资源上限

- **WHEN** 按优先级选中的本地出站资源上限为空、类型或十进制格式错误、低于
`8 MiB` 或高于 `32 MiB`
- **THEN** 启动 SHALL 失败并指出安全的配置错误类别
- **AND** SHALL 不建立 Milky 网络连接或读取本地资源

#### Scenario: 多入口保持同一启动快照

- **WHEN** 当前实例已经完成配置解析，随后操作者保存新设置
- **THEN** 除已经通过白名单管理指令核验并发布的入站白名单外，该实例的普通 adapter、独立 sender 和 home-channel 元数据 SHALL 保持已解析快照
- **AND** 其他新设置及单独通过 Web 保存的白名单 SHALL 在新的启动或宿主明确重新加载该配置后才适用

### Requirement: MILKY_ALLOWED_CHATS 支持命名空间通配符

适配器启动时 SHALL 接受 `MILKY_ALLOWED_CHATS` 中的完整 `group:<十进制群号>`、
`dm:<十进制 QQ 号>`、`group:*` 和 `dm:*` 条目；条目两端的空白 SHALL 被裁剪，重复条目
SHALL 归一化。`group:*` SHALL 表示所有合法 group chat，`dm:*` SHALL 表示所有合法 friend
chat；通配符 SHALL 只在完整条目中出现。除上述格式外的通配符、未知场景、空 ID、负数、
额外分隔符和空条目 MUST 使启动失败并指出安全的 `MILKY_ALLOWED_CHATS` 配置错误类别。
空值、未配置或原生空列表 SHALL 表示阻止全部普通 friend/group 入站。全部放行 MUST 显式配置 `group:*` 与 `dm:*`。此语义 SHALL 同时适用于启动、重连恢复和管理指令更新，不新增模式字段。

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

本场景沿用既有标识以便规范迁移；原有放行结果由本 BREAKING 变更替换为阻止。

- **WHEN** `MILKY_ALLOWED_CHATS` 未配置或为空字符串
- **THEN** 配置 SHALL 产生空白名单
- **AND** 合法 friend/group 普通消息 SHALL 被白名单门禁拒绝；白名单管理命令按独立路由契约进入 core，由 core 判断命令权限

#### Scenario: 高优先级空列表不回退

- **WHEN** settings 显式保存空列表，低优先级环境仍有非空白名单
- **THEN** 有效白名单 SHALL 为空并阻止全部普通入站
- **AND** SHALL 不恢复环境授权或自动写入通配符
