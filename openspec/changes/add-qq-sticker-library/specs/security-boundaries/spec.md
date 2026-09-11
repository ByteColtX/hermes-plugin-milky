## ADDED Requirements

### Requirement: Sticker operations MUST be bound to the confirmed Milky session

自动收集、sticker Tool handler 和维护入口 MUST 使用 Hermes 当前 session context 与已确认的 Milky chat identity，不能从模型传入的昵称、正文、路径、source JSON 或 guessed ID 推导目标。默认 chat scope MUST 与当前 `dm:<id>`/`group:<id>` 一致；跨 chat 读取、发送、删除和自动收集 MUST 被拒绝。global scope 只有配置显式启用时可用。

#### Scenario: Current chat sends its visible sticker

- **WHEN** 当前 Milky session 调用 `sticker_send` 发送当前作用域可见的 sticker
- **THEN** 系统 SHALL 只向当前已确认的 dm/group target 发送
- **AND** SHALL 使用现有目标解析和权限边界

#### Scenario: Automatic collection uses current chat scope

- **WHEN** 当前消息通过既有入站 Gate/Will 并进入自动收集
- **THEN** 新 entry SHALL 绑定该消息的已确认 chat scope
- **AND** 自动收集 SHALL 不从图片正文、模型输出或 guessed ID 推导另一个 target

#### Scenario: Model submits a different target

- **WHEN** tool args、session state 或维护参数指向另一个群、好友、temp 或未确认 target
- **THEN** 系统 SHALL 在网络边界或数据库变更前返回 `unauthorized`、`invalid_input` 或 `unsupported`
- **AND** SHALL 不执行 Milky send Action 或跨 scope mutation

### Requirement: Agent MUST never supply a filesystem or remote-media reference for sticker collection

自动 collection 的图片来源 MUST 只能是当前消息已由 Hermes media helper materialize 且经过 pipeline 边界交给内部收集器的本地输入。Agent Tool MUST 不接受用于收藏的 candidate ID、路径、`file://`、`http(s)://`、`base64://`、Milky `resource_id` 或任意 `asset://`/`artifact://` URI；Agent 也不得通过 `sticker_send` 或 `sticker_forget` 参数改变文件来源。

#### Scenario: Arbitrary path injection

- **WHEN** Agent 将本地路径、远端 URL、资源 ID 或 URI 放入任一 sticker 参数
- **THEN** 工具 SHALL 返回 `invalid_input` 或 `sticker_not_found`
- **AND** SHALL 不读取、下载、复制或发送该值

#### Scenario: Untrusted image is outside current message

- **WHEN** 图片来自历史消息、reply、forward、wait buffer 或未完成 Hermes materialization
- **THEN** 自动收集 SHALL 忽略该图片
- **AND** SHALL 不创建 staging、asset 或 entry

#### Scenario: Quality gate bypass is attempted

- **WHEN** Agent、普通正文、关键词或视觉模型输出试图绕过拒绝类别或 unknown 结果强制入库
- **THEN** 系统 SHALL 拒绝该 mutation
- **AND** SHALL 不把截图、新闻或隐私风险不明的图片写入 library

### Requirement: Sticker logs and errors MUST be low-sensitivity

Sticker 日志和异常 MUST 只包含固定工具名、固定安全分类、低基数计数、受限 scope 类别、质量枚举和必要的脱敏关联 ID。不得记录 token、Authorization、原始 Tool args、远端 URL、本地绝对路径、图片 bytes、完整 source、视觉模型自由文本理由或未脱敏个人资料。

#### Scenario: Automatic rejection is logged safely

- **WHEN** 图片因截图、新闻、文档、质量不足、隐私风险、classifier unavailable 或 malformed 结果被拒绝
- **THEN** 日志 SHALL 记录固定分类和必要的计数
- **AND** SHALL 不包含路径、URL、文件内容、视觉理由原文、异常正文或凭证

#### Scenario: Collection failure is logged safely

- **WHEN** 收藏因文件缺失、类型不支持、大小超限、数据库失败或 staging 过期而失败
- **THEN** 日志 SHALL 记录固定分类
- **AND** SHALL 不包含路径、URL、文件内容、异常正文或凭证
