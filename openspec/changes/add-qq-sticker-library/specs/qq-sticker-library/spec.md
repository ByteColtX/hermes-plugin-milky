## Purpose

为 QQ 会话提供一个能够自主筛选、持久化、按作用域搜索和复用高质量贴纸的 library，使系统可以从正常图片消息中沉淀可复用的反应图，同时排除截图、新闻和隐私风险内容。

## ADDED Requirements

### Requirement: Sticker library MUST use explicit scopes and stable content identity

系统 MUST 为 sticker library 使用明确的作用域。默认作用域 SHALL 是当前已确认的 QQ 会话：friend 使用 `dm:<peer_id>`，group 使用 `group:<group_id>`；只有启动配置显式启用 global 模式时，条目才可写入和读取 `global` 作用域。相同图片 bytes MUST 产生相同的 SHA-256 content ID；同一作用域内相同 content ID MUST 只保留一个可见条目。不同作用域的分类、标签和使用统计 MUST 相互隔离。

#### Scenario: Same image is automatically collected twice in one scope

- **WHEN** 同一作用域两次收到完全相同且已判定合格的图片 bytes
- **THEN** 第二次操作 SHALL 返回或记录 `duplicate`
- **AND** SHALL 不增加文件副本或重复条目
- **AND** SHALL 保留已有质量判定、分类和使用统计

#### Scenario: Different sessions receive the same sticker

- **WHEN** 两个不同 QQ 会话收到相同且已判定合格的图片 bytes
- **THEN** 每个会话 SHALL 只能看到自己作用域中已授权的条目
- **AND** 一个会话的分类、标签和使用次数 SHALL 不改变另一个会话的对应值
- **AND** 底层内容可以复用，但不得因此扩大可见范围

#### Scenario: Global mode is not explicit

- **WHEN** sticker scope 配置缺失、非法或未显式启用 global
- **THEN** 系统 SHALL 使用当前会话作用域
- **AND** SHALL 不把图片写入或读取 `global`

### Requirement: Automatic collection MUST accept only high-quality reusable stickers

系统 MUST 在当前消息的顶层图片已由 Hermes media helper 成功 materialize 后自动执行 sticker quality gate。质量 gate MUST 先拒绝不支持、损坏、空、超限或不可读的图片，再使用可用的 Hermes 视觉能力判断图片类别、质量、可复用性和隐私风险。只有类别为 sticker、质量合格、可复用、隐私风险为低且没有拒绝标签的图片才可创建长期 library entry。

#### Scenario: Reaction image passes quality gate

- **WHEN** 当前顶层图片是清晰的角色反应图、表情图或可复用梗图，且视觉判定为 sticker、quality good、reusable true、privacy low
- **THEN** 系统 SHALL 自动创建当前作用域的 sticker entry
- **AND** SHALL 自动写入受限 category 和 tags
- **AND** SHALL 不要求用户或 Agent 先调用收藏工具

#### Scenario: Screenshot is rejected

- **WHEN** 当前图片包含明显的浏览器或应用边框、聊天气泡、时间戳、窗口控件或高密度界面文字
- **THEN** 系统 SHALL 将其判定为 screenshot 或 chat_capture
- **AND** SHALL 不创建 asset、entry 或可搜索的 sticker 条目

#### Scenario: News or document image is rejected

- **WHEN** 当前图片呈现新闻标题、栏目、来源、文章版式、票据、文档、二维码或海报结构
- **THEN** 系统 SHALL 将其判定为 news、document、qr_code 或 poster
- **AND** SHALL 不创建长期 sticker 条目

#### Scenario: Ordinary photo or low-quality image is rejected

- **WHEN** 当前图片是普通生活照片、主体不适合反应复用、严重模糊、裁切异常或质量不足
- **THEN** 系统 SHALL 返回或记录 `rejected`
- **AND** SHALL 不把该图片作为 sticker 展示给搜索工具

#### Scenario: Quality result is uncertain

- **WHEN** 视觉能力不可用、超时、返回 malformed 或无法区分 sticker 与其他类别
- **THEN** 系统 SHALL 执行 `defer` 或 `classifier_unavailable`
- **AND** SHALL 清理临时输入
- **AND** SHALL 不降低门槛、不创建长期条目、不报告自动收藏成功

### Requirement: Automatic collection MUST preserve accepted media and expose bounded quality metadata

系统 MUST 对接受的 PNG、JPEG、GIF 或 WebP 保留原始图片 bytes，并按 content ID 写入 content-addressed 文件。GIF 不得被强制转换为静态图片。库内部可以保存固定枚举的 quality class、quality score、classifier version、category 和有限 tags，但不得保存视觉模型自由文本理由、原始 URL、绝对路径、完整 source、图片 bytes 或敏感正文。

#### Scenario: Accepted animated sticker is preserved

- **WHEN** 当前图片是通过质量 gate 的 GIF 或其他受支持动画图片
- **THEN** 系统 SHALL 保留其原始格式和 bytes
- **AND** 后续发送 SHALL 使用已保存的原始媒体
- **AND** 不得静默转换为单帧静态图

#### Scenario: Store write fails

- **WHEN** 自动收藏在临时文件写入、原子 rename 或数据库事务阶段失败
- **THEN** 系统 SHALL 返回或记录 `storage_error`
- **AND** SHALL 不留下可见的半条目或伪造 `created`
- **AND** 正常 Hermes 消息交接 SHALL 不受影响

### Requirement: Search and send MUST use the current authorized scope and existing media boundary

`sticker_categories`、`sticker_search` 和 `sticker_send` MUST 默认使用当前 Hermes session 对应的 Milky chat scope。搜索结果 SHALL 只返回可供发送的 opaque sticker ID 和受限元数据。 `sticker_send` 可以按 opaque ID 精确发送，也可以按 category 选择一个条目；目标 SHALL 是当前已确认会话，不得由 Agent 指定任意跨 chat 目标。发送 MUST 复用现有 Milky image sender、目标解析、本地附件大小限制和 native media upload。只有收到可确认的成功结果后才能增加 `usage_count` 和 `last_used_at`。

#### Scenario: Search finds an automatically collected sticker

- **WHEN** 当前会话调用 `sticker_search` 且作用域中存在匹配的自动收藏条目
- **THEN** 搜索 SHALL 返回 opaque ID、分类、有限标签和受限媒体元数据
- **AND** 结果 SHALL 不包含路径、URL、Authorization、原始正文或完整资源引用

#### Scenario: Send succeeds

- **WHEN** Agent 在当前会话选择一个可见 sticker 且 native image send 返回可确认成功
- **THEN** 系统 SHALL 发送一次原始图片
- **AND** SHALL 只更新一次该条目的使用统计

#### Scenario: Send target is not current session

- **WHEN** 工具参数或内部状态试图把 sticker 发往其他群、好友、temp 目标或未确认目标
- **THEN** 工具 SHALL 在网络 Action 前返回 `unauthorized`、`invalid_input` 或 `unsupported`
- **AND** SHALL 不更新使用统计

#### Scenario: Send result is unknown

- **WHEN** native media send 已进入网络边界但结果为 `transport_unknown`、`malformed` 或其他不可确认状态
- **THEN** 工具 SHALL 返回对应安全分类
- **AND** SHALL 不自动重发
- **AND** SHALL 不增加使用统计

### Requirement: Incorrect automatic entries MUST be removable and maintenance MUST be recoverable

系统 MUST 允许拥有当前 session 权限的 Agent 通过 `sticker_forget` 删除当前作用域可见的误收 entry；底层 asset 只有在没有任何 entry 引用时才可被 cleanup 删除。插件 MUST 提供受权限控制的导入、列举、清理、重建索引和 dry-run 维护入口；维护操作 SHALL 不由普通消息、关键词、Will 或自动分类任务隐式触发。

#### Scenario: Forget an incorrect entry

- **WHEN** Agent 使用当前搜索结果中的 sticker ID 调用 `sticker_forget`
- **THEN** 系统 SHALL 删除当前作用域 entry
- **AND** SHALL 不删除其他作用域仍引用的共享 asset
- **AND** 后续当前作用域搜索 SHALL 不再返回该 entry

#### Scenario: Dry-run import

- **WHEN** 操作者以 dry-run 模式导入一个包含图片和不支持文件的目录
- **THEN** 系统 SHALL 只返回待创建、重复、拒绝和失败的计数/安全原因
- **AND** SHALL 不创建或删除 library 条目和图片文件

#### Scenario: Cleanup finds a missing referenced file

- **WHEN** cleanup 发现数据库条目引用的图片文件不存在
- **THEN** 系统 SHALL 报告 `missing_file`
- **AND** SHALL 保留 metadata 供运维修复
- **AND** SHALL 不报告清理成功或删除其他仍被引用的内容
