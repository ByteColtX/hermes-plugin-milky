## MODIFIED Requirements

### Requirement: 白名单按完整 chat key 匹配

当 `MILKY_ALLOWED_CHATS` 为空时 Gate SHALL 放行可识别的 friend/group 消息；非空时 MUST 仅在
消息的完整 `group:<id>` 或 `dm:<id>` chat key 被精确列出，或存在对应的完整 `group:*` 或
`dm:*` 通配符时放行。具体 key 和通配符 SHALL 保持 `group`/`dm` 命名空间隔离，通配符
不得跨场景或按数值部分匹配。temp 在 Gate 之前已被忽略，不创建命名空间。

#### Scenario: 空白名单

- **WHEN** 未配置聊天白名单
- **THEN** 合法 group 和 dm 消息 SHALL 通过白名单门禁

#### Scenario: 同号不同命名空间

- **WHEN** 白名单只包含 `group:<id>` 而消息来自 `dm:<id>`
- **THEN** 消息 SHALL 被拒绝
- **AND** SHALL NOT 因数值部分相同而放行

#### Scenario: 私聊通配符

- **WHEN** 白名单包含 `dm:*` 且消息来自合法 friend 私聊
- **THEN** 消息 SHALL 通过白名单门禁
- **AND** 任意 group 消息 SHALL NOT 因 `dm:*` 通过白名单门禁

#### Scenario: 群聊通配符

- **WHEN** 白名单包含 `group:*` 且消息来自合法 group 聊天
- **THEN** 消息 SHALL 通过白名单门禁
- **AND** 任意 friend 私聊 SHALL NOT 因 `group:*` 通过白名单门禁

#### Scenario: 具体条目和通配符混用

- **WHEN** 非空白名单同时包含具体 chat key 和一个命名空间通配符
- **THEN** 命中具体 key 或对应通配符的消息 SHALL 通过白名单门禁
- **AND** 未命中任一规则的消息 SHALL 被拒绝

#### Scenario: 白名单拒绝仍停在 Gate

- **WHEN** 非空白名单没有匹配消息 chat key 或其对应命名空间通配符
- **THEN** ChatAllowlist gate SHALL 拒绝消息
- **AND** SHALL 不进入 wait buffer、Will、资源补全或 Hermes
