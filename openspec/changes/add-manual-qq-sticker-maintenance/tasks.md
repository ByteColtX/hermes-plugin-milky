## 1. 目录契约和持久化基础

- [ ] 1.1 新增贴纸 store 的 schema version、独立数据库文件、`sticker_items`/`sticker_files` 表和固定目录解析，使用 Hermes `plugin_data_dir("hermes-plugin-milky")`/`plugin_db()`；用首次加载、重载、未知 schema、file_sha256 唯一约束和不触及 session DB 的测试验证持久化边界
- [ ] 1.2 实现固定 `stickers/inbox/`、content-addressed library 与 `stickers/junk/` 的路径边界检查，拒绝符号链接、特殊文件、越界路径和命令参数路径；用临时目录测试验证所有移动和写入都落在插件持久目录
- [ ] 1.3 实现 PNG、JPEG、GIF、WebP 的非空、magic/header、结构可读性和 `10 MiB` 单文件上限校验；用正负图片 fixture、文本、空文件、损坏文件、扩展名伪装和超限文件验证 `rejected` 分类且不产生库文件

## 2. 导入、去重、删除和修复操作

- [ ] 2.1 实现 inbox 递归扫描、流式 SHA-256、`is_sticker=true` 到 library 的原子移动、`is_sticker=false` 到 `junk/` 的原子移动和移动失败回退；用成功移动、中断、写入失败和临时文件残留测试验证源文件归宿、可见性顺序和失败不伪造成功
- [ ] 2.2 实现 file_sha256 去重、`file_sha256 UNIQUE`、随机不透明 `sticker_id`、`detected_emotion`/`detected_tags_json`/`detected_description`、当前生效字段、字段级来源和时间戳、派生行级 `source`、列表稳定排序和受限摘要；同 hash 已存在完整 library 文件时消费 inbox 冗余副本且不覆盖人工字段；用同 bytes 多次导入、不同 bytes、GIF 保真、空库、`--limit` 边界、`field_sources`、`junk` 和输出脱敏测试验证幂等性
- [ ] 2.3 实现按当前可见 `sticker_id` 删除、一 hash 一可见 ID 的事务校验和 orphan 延迟回收；用未知 ID、重复删除、异常多引用、库文件缺失和删除后 cleanup 测试验证不越权、不误删和固定错误分类
- [ ] 2.4 实现 `cleanup` 的 orphan/临时文件/缺失引用诊断与 `--dry-run`，且不删除 `junk/`；实现只扫描 library、校验路径/file_sha256/格式/大小并原子重建 `sticker_files` 的 `reindex`；用 dry-run 无移动/删除/写入、合法 orphan、missing_file、reindex_skipped、事务失败回滚和可恢复清理测试验证保留元数据、不扫描 inbox/junk、不创建 sticker_id
- [ ] 2.5 为 add/edit/reanalyze/del/reindex/cleanup 增加单条事务、进程内短临界区和 finally 关闭连接；用并发 add/del、edit 多字段原子更新、reanalyze 基线替换、clear 恢复视觉基线、数据库异常、索引不兼容、重复执行和视觉完成时的交错提交测试验证无半条目且普通流程不受影响
- [ ] 2.6 接入 Hermes core 的异步辅助视觉接口，固定使用 design 中与用户确认完全一致的英文 sticker metadata annotator prompt；实现确定性校验/hash 去重之后按稳定顺序最多纳入 50 张唯一候选、最多 10 个并发调用、超过上限报告 `batch_deferred`、单选 `emotion` 固定枚举、2–5 个中文 `tags`、20 字以内 `description`、严格布尔 `is_sticker` 的 JSON schema 校验；`is_sticker=true` 原子移动入库并立即提交，`is_sticker=false` 原子移动到 `junk/` 并报告 `junk`，视觉失败留存 inbox；测试 fixture 必须使用真实返回形状：外层 JSON 字符串 envelope、`success=true`、`analysis` 内层 JSON、可选 `scale_note` 前缀、`success=false`/`error` 失败 envelope、空结果最终 fallback 文本、非法外层 JSON 和传输异常；验证固定 prompt 文本不漂移、外层 envelope 解析、scale note 精确去除、内层对象校验、`is_sticker` 类型校验、true/false 文件归宿、移动失败回退、core 内部重试不被插件重复叠加、并发上限、槽位补位、单条完成即提交、批次上限、宿主超时/取消时已提交与未提交状态、异常 JSON/超时/非法字段不移动且下次可重试、重复图片不调用视觉、dry-run 只预览不移动和主 Agent transcript 不变
- [ ] 2.7 实现 `/milky sticker edit <sticker_id> [--emotion=<enum>] [--tags=<tag1>,<tag2>,...] [--description=<text>] [--clear=<field>[,<field>...]]` 的字段级 set/clear、部分更新、全量校验后单事务提交、视觉基线恢复、字段来源和派生行级 source；用测试验证未指定字段不变、手动字段不被重复 add 覆盖，且图片 bytes、file_sha256、技术索引和 sticker ID 保持不变
- [ ] 2.8 实现 `/milky sticker reanalyze <sticker_id>` 的固定 prompt 调用、真实 envelope/schema 解析、detected_* 基线替换、detected_at/updated_at 更新和字段来源合并；用测试验证 `is_sticker=true` 仅更新视觉来源字段、manual 字段保持、`false` 返回 `not_sticker` 且原条目不变、失败回滚、图片和 sticker ID 不变
- [ ] 2.9 为 `sticker_items` 增加 `use_count`（默认 `0`）和可空 `last_used_at`（UTC）字段；实现 list 展示和维护操作不变更统计值的约束，预留后续 `sticker_send` 发起发送调用时的原子递增接口；用新建初始化、无效发送不变更、搜索/维护不变更、并发递增、Milky 成功/失败/未知状态均计数、同一调用只计一次、显式重试重新计数、统计写入失败不重发的测试验证计数语义

## 3. 命令、生命周期接入和授权边界说明

- [ ] 3.1 扩展 `/milky` 参数解析，保留无参数 `get_impl_info`，加入 `sticker add [--dry-run]`、`list [--limit]`、带 set/clear option 的 `edit`、`reanalyze <sticker_id>`、`del`、`cleanup [--dry-run]`、`reindex` 及固定 usage；用命令解析测试覆盖额外参数、越界 limit、缺失 ID、edit 无字段、同字段 set/clear、reanalyze 缺失 ID、标签/描述边界和未知子命令
- [ ] 3.2 暂不实现贴纸维护授权边界；记录 Hermes core handler 只收到 `raw_args`、无法可信确认 Milky friend/group 或操作者身份的限制，不增加 `MILKY_STICKER_OPERATOR_IDS` 或等价配置，也不测试 admin/operator gate
- [ ] 3.3 将维护 service 绑定到现有 command service/adapter 生命周期，确保注册阶段不创建目录、数据库、网络连接或脱离命令生命周期的后台任务，贴纸路径不创建旁路 client；用 register、connect、disconnect、多 client 和普通 command pipeline 测试验证边界
- [ ] 3.4 保持插件命令路径的既有分流；用 fake pipeline 验证显式 `sticker add` 或 `reanalyze` 参数才触发视觉调用，add 最多 10 个并发、最多 50 张候选、`batch_deferred`、真实 envelope 双层解析、`is_sticker=true` 移动入库、`is_sticker=false` 移动到 `junk/`、失败留在 inbox、完成即处理和槽位补位；reanalyze 的 `true` 更新视觉来源字段、`false` 保留原条目，且不触发 Agent turn、主 Agent transcript、Milky Action、reply cost 或普通消息 handoff
- [ ] 3.5 统一命令回执和日志的安全分类、计数上限和脱敏规则；用异常路径测试断言不输出 token、Authorization、绝对路径、URL、图片 bytes、完整参数、异常正文或未确认身份

## 4. 文档、主规范和集成验证

- [ ] 4.1 更新 `ARCHITECTURE.md`、`README.md`、`plugin.yaml` 和配置说明，记录 `stickers/inbox/`、`stickers/junk/`、授权边界暂缓、edit set/clear 语法、reanalyze 语义、字段级 source、`sticker_items`/`sticker_files`、detected/current/source/timestamp 字段、reindex 技术索引与事务边界、dry-run、视觉建议与手动修正、true/false 文件归宿、单次 50 张上限、`batch_deferred`、单选 emotion/中文 tags/description/is_sticker 元数据、成功移动源文件和非目标；用文档搜索验证没有把普通消息自动收集或无限后台视觉任务写成已支持能力
- [ ] 4.2 更新 `openspec/specs/qq-sticker-maintenance` 主规范以及 `slash-commands`、`plugin-lifecycle` 的归档后契约；用 OpenSpec delta 对照检查要求、命令名、`junk/` 归宿、reanalyze 行为和 core 权限说明一致
- [ ] 4.3 补充 fake Hermes/Milky 集成 fixture，覆盖 handler 仅收到 raw args 且不做来源授权断言、friend/group/CLI 等来源不在本 change 内保证、50 张批次上限、`batch_deferred`、最多 10 路并发、add/list/edit/reanalyze/del/cleanup/reindex、edit 部分更新/clear/字段级 source/非法输入原子回滚、一 hash 一可见 ID、真实视觉 envelope 成功入库/scale note/失败 envelope/空结果 fallback/传输失败、严格 `is_sticker` true 入库/false 移动 junk/移动失败回退/dry-run 不移动、reanalyze true 更新视觉来源字段/false 返回 not_sticker 且原条目不变、视觉失败留在 inbox 并由下次命令重试、reindex 合法 orphan/missing_file/reindex_skipped/事务回滚、宿主超时/取消时已提交与未提交状态、存储失败、重载保留和普通消息回归；验证命令回执、视觉调用边界、core 重试不被重复叠加、手动元数据优先级、主 Agent 上下文和真实 Milky Action 调用数均符合规范
- [ ] 4.4 运行相关聚焦测试，并按项目标准运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`；将失败按契约、实现、fake host 或环境问题分类
- [ ] 4.5 运行 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`，确认新 change 的全部 artifact 完整、delta requirement 标题与主规范匹配、change 内无旧方案引用，并记录验证结果
