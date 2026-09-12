# qq-sticker-send Specification

## Purpose

为 Hermes Agent 提供一个只能面向当前 Milky 会话、依据本地贴纸元数据选择并发送单张 QQ 贴纸的受限能力。

## Requirements

### Requirement: Tool 发现和参数边界

插件 MUST 注册独立的 `sticker_send` ToolSpec；它不是 Milky `operationId`，也不是任意 Action catalog。
插件 MUST 通过 manifest 的 `python_dependencies` 和项目运行时依赖声明提供 `Pillow>=12.3.0` 与
`jieba>=0.42.1`，且不得把 `jieba` 作为 optional extra 或按需导入。Agent 可见 definitions 只有在现有
`stickers.db` 中存在当前可见、`sticker_files` 关联有效且 library 文件可用的条目时才包含该工具。
空库检查不得创建目录或数据库。
Tool 只接受 `intent`、`emotion`、`tags`；至少一个参数非空，额外字段、目标、贴纸 ID、路径和 URL MUST 在文件或网络访问前
返回 `invalid_input`。

### Requirement: 目标和查询必须受信

Tool MUST 从 task-local `HERMES_SESSION_PLATFORM` 与 `HERMES_SESSION_CHAT_ID` 获取目标；平台必须为 `milky`，目标必须是合法
`dm:<十进制 QQ 号>` 或 `group:<十进制群号>`。Tool MUST NOT 使用 `HERMES_SESSION_ID`、home channel、默认目标或 Agent 参数。
缺失上下文返回 `missing_session_context`，非法或非 Milky 上下文返回 `unsupported`。

### Requirement: 匹配使用当前元数据且相关性优先

系统 MUST 只读取当前生效的 `emotion`、`tags`、`description` 以及有效 `sticker_files` 关联；`manual` 与 `vision` 来源不得改变
权重。`emotion` 严格筛选，多个请求 `tags` 为 OR，已提供字段之间为 AND。`intent` 使用统一 Unicode 归一化和本地 `jieba`
分词，按完整短语、全部 token、部分 token 的固定层级比较，不计算数值分数或使用阈值。无情绪时必须存在 tag、短语或 token 证据；
仅情绪查询可直接进入候选池。仅最终比较完全并列的候选可以使用当前 chat 的历史做软轮换，最近使用不得硬排除明显更优候选。

### Requirement: 文件校验、统计和发送

选定条目 MUST 通过受控 library containment、regular-file、图片格式、双索引 SHA-256 和一次性 materialization 校验；失败不得静默换图。
本地校验成功后，Tool MUST 在短事务中只更新一次全局 `use_count`/`last_used_at` 和 `(chat_key, sticker_id)` 使用记录，再调用一次
`send_private_message` 或 `send_group_message`。消息只含一张 `image` segment，且 `sub_type` 严格为 `sticker`；不得附加 caption、文本、上传、重试或
fallback。统计不等待远端结果，远端失败或未知不回滚统计。

### Requirement: 结果分类和生命周期

成功返回 `status=sent` 和 Milky `message_id`，不得返回内部 `sticker_id`；没有候选返回 `no_match`。参数、上下文、文件、存储、协议拒绝、HTTP、
malformed 和 transport unknown MUST 使用固定机器可读分类。注册、连接、SSE、普通 Agent 输出和 disconnect MUST 不打开贴纸 store、扫描 library、
创建检索后台任务或执行网络 I/O；`jieba` 作为正常运行时依赖随插件模块加载，不得在 Tool discovery 中按需导入。
过期 definition 和未连接 sender MUST fail closed。
