## Context

本 change 建立在当前 Milky 入站和出站边界之上。普通消息已经按 canonical、TTL dedup、admission、Gate、Will、buffer drain、trigger 资源解析、Hermes mapper 和 `handle_message()` 交接；`ResourceResolver` 在 trigger 阶段把已确认的远端媒体交给 Hermes helper，并只向 mapper 提供本地 materialization。出站图片已经由统一 sender 负责目标解析、大小限制、URI materialization 和 Milky native Action。

当前版本还已经交付显式 `/milky sticker` 人工维护和 `sticker_send`：独立 `stickers.db` 使用
`sticker_items`、`sticker_files`、`sticker_send_usage` 等表，图片位于 plugin-data 下的受控目录。
本 change 需要在这个既有持久化边界上迁移或扩展 schema，保留已有人工条目、文件、字段覆盖和
使用统计；不得把“首次启用”实现为创建空库、覆盖旧表或重复导入已有文件。

贴纸收藏的目标是“系统自主收集高质量贴纸”，而不是让 Agent 看到图片后再调用收藏工具。因此自动收集必须挂在资源解析完成之后的 Milky-owned 旁路上，并且不能改变原有 Hermes handoff。视觉判定优先复用 Hermes 已有的 `vision_analyze_tool` 能力；视觉能力不可用或结果不满足严格格式时，自动收藏安全跳过。

因此 sticker library 不需要复制下载器、SSRF 校验、远端媒体缓存或第二套出站发送协议。它只需要暂存当前图片的受信任本地输入，经过确定性过滤和视觉质量策略后，把接受的内容写入插件自己的持久化目录，并在发送时重新交给既有出站边界。

本 change 采用内容 hash 去重、作用域条目、category/tag 搜索、usage 统计、原子文件写入和 cleanup。Koishi 的 `asset://`、`artifact://`、数据库模型和每频道 AgentPlugin 生命周期不作为 Hermes 公共 API 假设。Hermes 提供的 `register_tool`、`pre_tool_call`、`pre_llm_call`、`register_system_prompt_section`、`plugin_db`、`plugin_data_dir` 和任务生命周期接口足以覆盖本 change。

当前 `add-milky-relationship-system` 仍在进行中，可能同时修改 `inbound/pipeline.py`、`outbound/tools.py` 和插件状态初始化。本设计通过独立数据库文件、独立表前缀和独立服务绑定降低耦合；最终合并时仍须复核两条 change 的入口顺序和注册清理顺序。

## Goals / Non-Goals

**Goals:**

- 在当前消息的顶层图片 materialize 后自主判断并收藏高质量 QQ 贴纸，不要求用户或 Agent 先调用收藏动作。
- 通过确定性格式门禁和视觉质量分类排除截图、新闻、聊天记录、文档、二维码、普通照片、低质量或高隐私风险图片。
- 让相同 bytes 在多个作用域中安全复用，同时隔离分类、标签和使用统计。
- 复用 Hermes 入站资源 helper、视觉能力和 Milky 既有出站 materialization。
- 保持注册阶段无网络、Gate/Will/队列边界不变，并在自动分类或存储旁路失败时继续正常 Hermes handoff。
- 提供搜索、发送和删除误收贴纸的固定工具，以及可 dry-run、可审计的导入和 cleanup 运维路径。

**Non-Goals:**

- 不处理历史消息、reply、forward 或 wait buffer 图片，不扫描既有聊天记录进行回填。
- 不建立 Hermes 通用 `asset://`/`artifact://` 资源仓库，不修改 Hermes core。
- 不引入独立的 Agent queue、busy/follow-up/interrupt、Will 或完整 AgentPlugin 生命周期。
- 不提供绕过质量门控的 Agent 强制收藏工具；需要强制导入时只走受权限控制的 operator CLI，且仍执行格式和隐私边界。
- 不在当前 change 中实现跨设备同步、quarantine UI、embedding 相似搜索或按热度自动删除。

## Decisions

### 1. 在现有贴纸库上扩展两层内容目录，并保存质量判定元数据

插件继续使用现有独立的 `stickers.db`，通过 `plugin_db("hermes-plugin-milky", filename="stickers.db")`
打开；实际 bytes 位于 `plugin_data_dir("hermes-plugin-milky") / "stickers"`。文件名由 SHA-256
content ID 派生，不能由 Tool 参数、远端 URL 或原始文件名派生。迁移需保留当前人工维护 schema
和已有条目，再增加或映射自动 collection 所需的 asset/entry 数据；schema 失败时不得清空旧库。

数据库至少包含两层逻辑：

```text
sticker_asset
  content_id, mime, size, relative_file,
  quality_class, quality_score, classifier_version,
  created_at

sticker_entry
  entry_id, content_id, scope_key, category, tags,
  source_scene, source_chat_key, source_message_id,
  auto_collected, usage_count, last_used_at,
  created_at, updated_at
```

`sticker_asset` 负责一份真实内容及其已确认的质量状态；`sticker_entry` 负责某个作用域的可见分类、标签和统计。 `UNIQUE(scope_key, content_id)` 防止同一作用域重复条目。质量标签使用固定枚举，不保存视觉模型的自由文本理由；source 只保存低敏关联字段，不保存消息正文、临时 URL、完整 Milky raw、发送者昵称或本地路径。

继续使用独立 `stickers.db` 而不是复用关系系统的默认数据库，是为了避免关系表迁移、连接关闭和
schema 版本互相污染。两者仍共享 Hermes plugin-data 根目录，但不共享表、repository 或事务对象。

备选方案是单个 JSON 文件或 `ctx.state`；前者无法安全处理并发和原子引用，后者有配额且不适合图片目录和关系查询，因此不采用。直接复用 Hermes session DB 也会把插件业务状态耦合到 core session 生命周期，排除在外。

### 2. 作用域默认按当前会话隔离

scope 解析优先读取已确认的 Hermes/Milky session context：

```text
friend -> dm:<peer_id>
group  -> group:<group_id>
global -> 只有显式 MILKY_STICKER_SCOPE=global 时可用
```

Tool 参数不提供任意 `scope_key` 或任意发送目标。自动收集使用当前消息的已确认 chat key；`sticker_categories`、`sticker_search`、`sticker_send` 和 `sticker_forget` 由当前 session 自动决定作用域。global 模式只改变可见 library scope，不改变出站目标，出站仍只能是当前 session。

QQ 群图片可能包含隐私内容，跨群复用必须是 operator 的明确选择。未来如果需要 global 到 chat 的显式迁移，应增加受权限控制的 CLI，而不是让 Agent 传入任意 scope。

### 3. 在 resource resolver 和 mapper 之间建立自动收集旁路

不修改 Hermes core。Milky 自己的 `InboundPipeline` 在 `resolve_batch()` 完成后，只读取 `resolved_batch.current` 的当前顶层 `image_occurrences`，不读取 history、reply 或 forward occurrence。每个合格的本地 materialization 先进入有 TTL、大小上限和取消语义的内部 staging；staging 失败时继续既有 `map_message_event()` 和 `handle_message()`。

自动收集任务不产生供 Agent 提交的 candidate ID。系统内部只传递受信任的任务句柄和本地输入，任务完成后删除未入库的 staging 文件。staging 不是远端下载器或通用媒体缓存，只用于保证 Hermes materialization 生命周期和后台视觉判定之间的边界。

视觉判定和入库任务必须受并发上限、单图超时和总量上限约束，并加入 pipeline/adapter 的生命周期任务集合。自动任务可以晚于 Hermes handoff 完成；任务异常、取消、超时或存储失败不得回滚消息交接、Gate、Will 或 reply cost。

`pre_llm_call` 不再注入 candidate ID，也不负责触发收藏。稳定的 `register_system_prompt_section` 只说明 Agent 如何查询、发送和删除已入库贴纸；自动收集结果不强制写入对话正文。

### 4. 使用两阶段质量门控，未知结果不入库

第一阶段执行不需要视觉模型的硬规则：

- 只接受已解码的 PNG、JPEG、GIF 或 WebP 图片；
- 拒绝空文件、非 regular file、超出启动限制的文件和明显无法复用的尺寸；
- 先计算 content ID，已有合格 asset 可以直接复用，避免重复视觉调用；
- 不读取或记录 URL、路径之外的原始 Milky source，也不扩大 Hermes 的媒体权限。

第二阶段调用 Hermes 已有视觉能力，要求返回可解析的固定结构：

```json
{
  "class": "sticker|screenshot|news|chat_capture|document|photo|poster|qr_code|other",
  "quality": "good|poor|unknown",
  "reusable": true,
  "privacy_risk": "low|high|unknown",
  "category": "reaction|character|meme|emoji|other",
  "tags": ["..."]
}
```

只有 `class=sticker`、`quality=good`、`reusable=true`、`privacy_risk=low` 且没有拒绝标签时才接受。初始阈值和标签集合必须用脱敏正负样本 fixture 校准；不把未经验证的数字阈值写成跨模型保证。截图、新闻、聊天记录、文档、票据、二维码、海报、普通照片和低质量图片直接拒绝。带少量文字的反应图或梗图可以接受，但文章标题、栏目、来源、聊天气泡、浏览器边框和时间戳等结构属于拒绝信号。

视觉能力不可用、返回 malformed、字段不完整或结果为 unknown 时执行 `defer`：删除 staging，不写 asset/entry，不向用户报告收藏成功。视觉结果中的自由文本只用于当前判定，不持久化、不写日志。

### 5. Agent 只负责使用和纠错，自动收集不是 ToolSpec

Agent 可见的固定工具为：

```text
sticker_categories: {}
sticker_search: {category?, keyword?, tags?, limit?}
sticker_send: {sticker_id?, category?, tags?, index?}
sticker_forget: {sticker_id}
```

`sticker_categories`、`sticker_search`、`sticker_send` 和 `sticker_forget` 都从当前 session 推导 scope；Agent 不得提交路径、URL、resource ID、content bytes 或任意 target。 `sticker_forget` 只删除当前作用域的 entry；底层 asset 只有在没有其他 entry 引用时才由可恢复 cleanup 处理。

当前 `sticker_send` 只按 `intent`、`emotion` 和 `tags` 使用既有人工库；本 change 会在保留当前
会话目标和一次发送边界的前提下，将其调整为可处理新 entry 的受限契约，并增加其余固定工具。

自动收集是内部服务操作，不注册为 Agent Tool，也不由关键词、Will、普通回复或系统事件隐式触发。 `pre_tool_call` 只为四个固定工具做会话、scope、参数和权限检查；handler 继续重复校验。 `sticker_send` 最多一次网络发送，未知结果不重试、不计数。

### 6. 读写和文件一致性采用可恢复顺序

自动收藏写入顺序为：读取并验证 staging -> 计算 content ID -> 查询已有 asset/entry -> 确认质量结果 -> 临时文件写入并原子 rename -> 在事务中创建 asset/entry -> 删除 staging。数据库插入失败时删除未被引用的临时/新文件；若 cleanup 发现 metadata 缺文件，保留 metadata 并返回 `missing_file`，不删除未知引用。

删除 scope entry 前先确认 content ID 是否仍被其他 entry 引用；只有无引用时才删除 asset 文件。cleanup 默认 dry-run，真正删除必须来自显式维护命令。数据库和文件系统无法形成跨系统原子事务，因此以“数据库引用优先保守保留文件”为原则，允许孤立文件后续清理，不允许先删文件造成静默损坏。

### 7. 运维和生命周期

`ctx.register_cli_command()` 提供 import/list/cleanup/reindex 及 `--dry-run`。目录导入只接受 operator 明确提供的本地路径，仍执行同一格式、大小、hash、质量策略和 atomic write 检查；dry-run 不写文件和数据库。导入结果按 created/duplicate/rejected/unsupported/storage_error 分类，不回显完整路径。

storage service 首次工具、自动收集任务或 CLI 使用时懒加载，使用 schema version 表进行小步迁移。通过 `ctx.on_unload()` 关闭数据库、取消分类任务、清理 staging，并等待有限的文件操作完成；正常首版没有常驻扫描任务。plugin reload 和代码更新不删除 plugin-data，回滚只需禁用自动收集或工具，数据保留供后续版本读取或手工清理。

### 8. 与现有 change 的依赖方向

关系系统和 sticker library 各自拥有数据库文件、表、服务和 Tool 名称。二者可以共享 Milky 当前 session context 和现有 pipeline admission，但不能互相调用 repository 或把 sticker 收藏当作 relationship event。实现合并时优先保证 pipeline 的既有顺序，然后分别挂载自动收集 observer 和 relationship observer；任一旁路失败都不能改变 Hermes handoff。

## Risks / Trade-offs

- **[视觉分类误收截图或新闻]** -> 采用固定拒绝类别、质量/隐私三重门槛、保守的 unknown 处理和脱敏正负样本回归；不提供 Agent 绕过门槛的收藏工具。
- **[视觉模型不可用或输出 malformed]** -> 自动收藏只做 best-effort，删除 staging 并继续原有 handoff；不把失败伪装为空库或收藏成功。
- **[自动任务增加资源和延迟]** -> staging 有大小上限，分类任务有并发上限和超时，且不阻塞 Hermes handoff；任务由生命周期统一取消。
- **[数据库写入与文件写入不是同一事务]** -> 采用临时文件、原子 rename、数据库引用优先和显式 cleanup；宁可暂留 orphan file，不先删除仍可能被引用的文件。
- **[全局库造成跨群隐私泄露]** -> 默认 chat scope，global 必须显式配置；Tool 不接受任意 scope 参数，搜索、发送和删除始终受当前 session 限制。
- **[图片体积和磁盘增长]** -> 复用 `MILKY_MAX_LOCAL_MEDIA_BYTES`、限制 staging/store 数量、提供 dry-run cleanup；不在本 change 中实现自动按热度删除。
- **[重复图片并发入库]** -> 使用 content ID 和 `(scope_key, content_id)` 唯一约束；重复任务返回 duplicate，不增加文件副本。
- **[关系 change 同时改 pipeline/tool 注册]** -> 使用独立模块和 `stickers.db`，在任务阶段加入 fake host 的合并回归，禁止任一 change 静默覆盖另一个 observer 或 ToolSpec。

## Migration Plan

1. 首次启用自动 collection 时先识别并迁移现有 `stickers.db`/library schema，保留人工条目、文件、
   人工字段和使用统计；不自动扫描历史入站消息，不回填历史图片，也不迁移其他插件的数据库或资源目录。
2. 先实现只读 categories/search、质量 fixture 和 dry-run import，再启用自动收集、send 和 forget；视觉能力不可用时只提供查询/发送已有条目。
3. 在 fake Hermes、脱敏资源 fixture 和 fake Milky sender 上验证正负图片分类、截图/新闻排除、作用域隔离、任务取消、文件/数据库失败和未知发送结果；实机 smoke 仅在用户明确授权目标后进行。
4. 回滚时关闭自动收集或撤销插件版本；保留 `plugin-data/.../stickers`，不执行自动删除。恢复版本时通过 schema version 或显式 reindex 处理，不依赖重新下载远端媒体。
5. 归档前必须具备 store、自动分类、质量拒绝、固定工具授权、出站结果、生命周期和安全日志的自动化证据；未验证的真实 Hermes/Milky host 行为继续标记为 `unsupported` 或 evidence 中的待确认边界。
