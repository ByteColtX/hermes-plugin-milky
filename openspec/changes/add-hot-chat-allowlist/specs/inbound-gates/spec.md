# Spec Delta

## MODIFIED Requirements

### Requirement: Gate 按固定顺序执行

除按 hot-chat-allowlist 进入 core 分发的管理命令路由例外外，所有普通入站消息 MUST 依次经过 SelfMessage、ChatAllowlist 和 MutedGroup 三道门禁；任何门禁拒绝后 SHALL 停止后续门禁、缓冲、Will 和 Hermes 处理。

#### Scenario: 自身消息

- **WHEN** `sender_id` 等于 `self_id`
- **THEN** SelfMessage gate SHALL 以稳定 reason 拒绝
- **AND** 消息 SHALL 不增长 wait buffer 或修改 Will

#### Scenario: 白名单外消息

- **WHEN** 普通消息的当前有效入站白名单为空或完整 chat key 未命中任何有效规则
- **THEN** ChatAllowlist gate SHALL 拒绝消息
- **AND** SHALL 不调用 Agent 或资源接口

管理命令例外 SHALL 仅豁免来源会话的白名单匹配；canonical、自身消息和去重边界仍然适用，管理来源群的禁言检查 SHALL 延后至 core 放行后、名单读写前完成。普通正文和其他命令 MUST NOT 获得此路由豁免。Gate MUST NOT 读取管理员名单或判断 slash 权限；所有命令权限 SHALL 由 core 决定。Gate 本身 SHALL 保持只读；按需群状态准备 SHALL 由 core 放行后的管理流程负责。

#### Scenario: 空名单仍能管理

- **WHEN** 有效白名单为空，调用者从合法会话发送规范白名单管理命令且 canonical、自身消息和去重检查通过
- **THEN** 仅该管理命令 SHALL 进入 core 命令通道，由 core 判断权限；插件 SHALL 不先判断发送者是否为管理员
- **AND** 同一发送者的普通正文及其他命令 SHALL 被拒绝

### Requirement: 白名单按完整 chat key 匹配

当当前有效入站白名单为空时 Gate SHALL 拒绝全部普通 friend/group 消息；非空时 MUST 仅在
消息的完整 `group:<id>` 或 `dm:<id>` chat key 被精确列出，或存在对应的完整 `group:*` 或
`dm:*` 通配符时放行。具体 key 和通配符 SHALL 保持 `group`/`dm` 命名空间隔离，通配符
不得跨场景或按数值部分匹配。temp 在 Gate 之前已被忽略，不创建命名空间。

#### Scenario: 空白名单

- **WHEN** 未配置聊天白名单
- **THEN** 合法 group 和 dm 普通消息 SHALL 被白名单门禁拒绝

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

- **WHEN** 普通消息的非空白名单没有匹配消息 chat key 或其对应命名空间通配符
- **THEN** ChatAllowlist gate SHALL 拒绝消息
- **AND** SHALL 不进入 wait buffer、Will、资源补全或 Hermes
