# Spec Delta

## MODIFIED Requirements

### Requirement: 管理回执区分规则和真实运行状态

list SHALL 稳定排序并完整返回当前 profile 的持久有效规则、配置来源、运行规则及二者是否一致，不设分页或条数截断。帮助及名单标题 SHALL 为“Milky · 会话白名单”，来源标签 SHALL 使用 Source。来源 SHALL 保留 settings、legacy、environment、default 原名称；一致时只显示一份，不一致时分别显示“当前配置”和“当前运行”，提示重启 Gateway。空列表 SHALL 明示全部普通入站阻止。反馈 SHALL 只发回原命令来源，不广播其他群。

add/del 回执 MUST 区分 saved、applied、unchanged、blocked、conflict、unsupported、invalid_input 和 unknown 等实际结果的语义，使用简洁正式的中文，不要求展示英文状态码前缀，也不附加群禁言判断。回执发送失败 SHALL 不回滚配置、不重新执行修改或自动重发。诊断只保留操作、固定分类、版本或受限计数，不记录命令正文、完整列表、凭证、路径或底层异常正文。

#### Scenario: 持久值与在线值不同

- **WHEN** Web 已保存新白名单但实例尚未重新加载，调用者执行 list
- **THEN** 列表 SHALL 区分持久配置与运行策略，提示重启 Gateway
- **AND** list SHALL 不隐式应用新配置或查询所有群状态

#### Scenario: 完整列表与回执失败

- **WHEN** 列表超过 50 条，或成功提交后的 QQ 回执发送失败
- **THEN** 前者 SHALL 完整返回规则并由既有发送流程处理长消息，后者 SHALL 保留提交结果
- **AND** SHALL 不提供分页参数、截断规则或因回执失败重放修改

#### Scenario: 空参数与显式帮助

- **WHEN** core 允许调用者执行 /milky allowlist 或 /milky allowlist help
- **THEN** 系统 SHALL 返回相同静态短帮助，保留 Usage、Commands，命令行独立换行并缩进两个空格；add/del 共用的目标示例在 Commands 末尾以一行 e.g. target: 给出，不显示独立 Targets、Examples 章节；默认行为以简短说明给出
- **AND** Usage SHALL 展示 /milky allowlist [command] [args...]；Commands SHALL 展示 list、add [target]、del [target]、help 并标注“别名 remove”；共用示例 SHALL 包含合成 group:<十进制群号>、dm:<十进制 QQ 号>、group:*、dm:*，不暗示目标类型仅适用于某个动词；说明 SHALL 明确 add/del 省略目标时使用可信当前会话、不带子命令时显示帮助；list/help SHALL 不接受目标或其他参数，概括语法不放宽校验；帮助 SHALL 不读取配置、不查询群状态，也不进入 Will 或普通 Agent
- **AND** 帮助末尾 SHALL 不添加并发修改 Note

#### Scenario: 紧凑格式错误

- **WHEN** allowlist 参数非法，包括 help 后附加目标或其他参数
- **THEN** 系统 SHALL 返回“指令格式不正确。”及分行缩进的 Usage 和 Help 区块
- **AND** 已知动词的 Usage SHALL 只展示自身合法语法：add/del 带 [target]，list/help 无目标；remove SHALL 展示 del 的规范语法。未知动词 SHALL 展示 /milky allowlist <list|add|del|help>；Help SHALL 展示 /milky allowlist help，不读写配置或查询群状态
- **AND** 其他异常回执 SHALL 不附加查看名单命令
