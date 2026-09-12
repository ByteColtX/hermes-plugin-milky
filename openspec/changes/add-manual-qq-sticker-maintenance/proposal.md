## Why

当前插件没有一个可审计的 QQ 贴纸维护入口，操作者无法把已经整理好的图片包安全地导入、查看、删除或修复索引。这个 change 将贴纸库改为显式、手动、可重复执行的维护流程：操作者把候选图片放入 Hermes 为插件提供的持久目录，再通过 `/milky sticker` 命令触发处理。

## What Changes

- 新增独立的 QQ 贴纸持久化库，使用 Hermes `plugin_data_dir("hermes-plugin-milky")` 和 `plugin_db()`，不写入安装目录或 Hermes session DB。
- `sticker_items` 增加使用统计字段 `use_count` 和可空的 `last_used_at`；新条目默认 `use_count=0`、`last_used_at=NULL`，维护命令不改变统计值，后续 `sticker_send` 在有效贴纸已解析并发起发送调用时原子递增一次，不等待或依赖 Milky 返回状态。本 change 不新增发送工具，也不把发送请求成功等同于 QQ 用户已实际看到消息。
- 约定持久目录下的 `stickers/inbox/` 为人工投放目录，`stickers/junk/` 为视觉判定非贴纸后的简单隔离目录；`/milky sticker add` 扫描 inbox 中的图片，先执行格式、大小、可读性和 SHA-256 去重校验，再按稳定顺序最多纳入 50 张唯一候选，通过 Hermes core 的异步辅助视觉接口处理；同时最多保持 10 个视觉调用进行中。结构合法且 `is_sticker=true` 的候选从 inbox 移入 content-addressed 贴纸库并立即可见，结构合法且 `is_sticker=false` 的候选移入 `junk/` 且不入库，超出批次上限的候选留在 inbox 并报告 `batch_deferred`。
- 新增 `/milky sticker list`、`/milky sticker edit <sticker_id>`、`/milky sticker reanalyze <sticker_id>`、`/milky sticker del <sticker_id>`、`/milky sticker cleanup [--dry-run]` 和 `/milky sticker reindex` 维护命令；`edit` 支持字段级部分更新和清除人工覆盖，`reanalyze` 使用同一固定视觉 prompt 更新视觉基线，`reindex` 原子重建库文件技术索引；命令结果使用固定摘要和安全错误分类，不泄露绝对路径、URL 或图片内容。
- 本 change 暂不提供或验证贴纸维护的操作者授权边界；不新增插件级 operator 配置，也不宣称命令只能来自 Milky friend/group。到达插件 command handler 的参数按本 change 处理，来源授权待 Hermes core 提供可信来源上下文后另行处理。
- `add` 对已接受的 `is_sticker=true` 文件采用移动入库，不保留 inbox 原文件；视觉判定 `false` 的文件移入 `junk/`，不建立额外复核流程，需要再次处理时由操作者手动移回 inbox。已确认库中存在完整同 hash 文件的冗余 inbox 副本报告 `duplicate` 并移除，不重新调用视觉或覆盖人工字段。重复执行具有幂等性；同一 content hash 只对应一个可见 `sticker_id`，不支持共享可见引用；`cleanup` 只处理库内孤儿文件、缺失引用和无效索引，不隐式删除 inbox 或 `junk/` 原文件。
- 明确不新增入站消息自动收藏、脱离命令生命周期的后台视觉任务、`pre_llm_call` 图片注入或 Agent 收藏 Tool；视觉辅助只在显式维护命令中运行，用于批量生成固定主情绪、中文检索标签、短描述和 `is_sticker` 判定。`is_sticker` 是新增候选的唯一语义入库门槛：合法 `true` 移入库，合法 `false` 移入 `junk/`；其他视觉调用失败、envelope 非法或结果字段非法的图片暂留 inbox，等待下次命令重试。已入库贴纸可通过 `edit` 手动纠正，或通过 `reanalyze` 重新视觉打标；重新打标失败时原条目不变，返回 `is_sticker=false` 时也保留原条目并报告 `not_sticker`，不自动移入 junk。插件必须先解析 core 返回的外层视觉 envelope，再解析 `analysis` 内的模型 JSON。普通消息和图片不触发视觉调用。

## Capabilities

### New Capabilities

- `qq-sticker-maintenance`: 定义人工投放目录、图片导入、持久化、去重、列表、删除、清理、重建索引、命令回执和失败恢复行为。

### Modified Capabilities

- `slash-commands`: 扩展 `/milky` 的 `sticker` 子命令，并保持既有命令分流和出站回执边界；本 change 不新增命令来源或操作者授权断言。
- `plugin-lifecycle`: 增加贴纸数据库、文件目录的懒加载、连接关闭、重载保留和注册阶段无副作用要求。

## Impact

- 影响 `slash_commands.py`、`inbound/commands.py`、`__init__.py`、`adapter.py`，并新增贴纸 store、导入维护服务和测试 fixture；本 change 不改 Hermes core 的 handler 签名或授权机制。
- 使用 Hermes core 已有的插件持久化接口和 task-local session context；不修改 Hermes core，不复制其 session 队列、媒体下载或安全边界。
- 需要补充命令解析（包括 `edit` 的部分更新/清除语法和 `reanalyze`）、文件格式与大小边界、SHA-256 去重、单次最多 50 张候选和 `batch_deferred`、最多 10 路视觉并发、视觉外层 envelope 与内层 `analysis` 的双层解析、`success`/`error`/scale note 处理、固定 prompt 和 `is_sticker` 布尔 schema、true 入库/false 移入 `junk/`/失败留在 inbox 的文件归宿、core 重试边界、emotion 单选与固定枚举、tags 数量和中文约束、description 长度约束、`sticker_items` 的 detected/current/source/usage 字段、重新打标时保留人工覆盖、`updated_at`/`detected_at` 时间字段、原子移动、`sticker_files` 技术索引及 `reindex` 事务、损坏索引、dry-run、重载和真实形状 fixture/fake Hermes 集成测试，并同步 `README.md`、`ARCHITECTURE.md` 与相关主规范。
- 维护操作只在显式 `/milky sticker ...` 命令中发生；普通消息、关键词、Will、图片入站资源解析和 Agent 输出均不得触发贴纸入库或删除。
