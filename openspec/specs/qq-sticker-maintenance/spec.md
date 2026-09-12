# qq-sticker-maintenance Specification

## Purpose

为操作者提供只由显式 `/milky sticker` 命令驱动、可恢复且可审计的 QQ 贴纸本地维护闭环。

## Requirements

### Requirement: 贴纸维护必须限制在 plugin-data 和固定目录

系统 MUST 使用 Hermes `plugin_data_dir("hermes-plugin-milky")` 与独立
`plugin_db("hermes-plugin-milky", filename="stickers.db")`。输入只来自
`stickers/inbox/`，正式库和隔离目录分别为 `stickers/library/` 与 `stickers/junk/`；命令不得
接受或读取任意路径、URL、URI、符号链接或特殊文件。

### Requirement: add 必须先确定性校验去重再调用视觉

`add` SHALL 递归校验非空 PNG、JPEG、GIF、WebP regular file，单文件不超过 `10 MiB`，并以流式
SHA-256 去重。每次命令最多为 50 张唯一候选调用 Hermes `vision_analyze_tool`，同时最多 10 路；
超出部分返回 `batch_deferred` 并留在 inbox。视觉调用必须解析外层 JSON envelope 和内层 analysis
对象，严格校验单选 `emotion`、2–5 个中文 `tags`、20 字以内中文 `description` 和布尔
`is_sticker`。true 原子移动到 library 并写入 `sticker_items`/`sticker_files`，false 原子移动
到 junk；视觉失败、非法结构或移动失败不得伪造成功，源文件留在 inbox。

### Requirement: 贴纸条目必须支持字段级维护和可恢复修复

`sticker_items.file_sha256` MUST 唯一，并保存随机不透明 `sticker_id`、`detected_*` 视觉基线、
当前生效字段、字段级 `vision|manual` 来源和 `created_at`/`updated_at`/`detected_at`。`edit`
必须在单事务中支持 set/clear 部分更新；`--clear` 恢复对应视觉基线。`reanalyze` 只更新合法
`is_sticker=true` 的视觉基线，人工字段保持；false 或失败保留原条目。`del` 只接受当前可见 ID，
`cleanup` 只回收无可见引用的 orphan/临时文件且不删除 junk，`reindex` 只扫描 library 并原子
重建 `sticker_files`，不创建条目或 ID。

### Requirement: 维护命令必须有界、懒加载并隔离普通消息

支持 `add`、`list`、`edit`、`reanalyze`、`del`、`cleanup`、`reindex` 及对应 `--dry-run`/`--limit`
语法。dry-run 不移动、删除或写入贴纸文件、数据库记录或索引。贴纸 store 只在有效维护命令中
懒加载，注册、普通连接、普通消息、关键词、Will 和 Agent 输出不得触发维护。handler 只按
`raw_args` 处理，不声明或实现 operator 身份授权。

### Requirement: 使用统计必须不影响维护幂等性

新条目 MUST 初始化 `use_count=0`、`last_used_at=NULL`；list 和所有维护操作不得修改统计。预留
的发送接口只有在有效条目已发起发送调用后才原子递增一次，Milky 成功、失败或未知状态均不回滚，
统计写入失败不得重发已接受的消息。

### Requirement: 结果和日志必须脱敏

用户回执和日志只能包含固定安全分类、低基数计数、受限元数据和不透明 ID，不得包含 token、
Authorization、绝对路径、URL、图片 bytes、完整参数、视觉原文或异常正文。贴纸维护失败不得改变
SSE、Gate、Will、buffer、Hermes handoff、reply cost 或出站 sender 状态。
