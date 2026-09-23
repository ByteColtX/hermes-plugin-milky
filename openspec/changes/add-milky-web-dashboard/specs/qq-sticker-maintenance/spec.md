# Spec Delta

## Purpose

提供由显式维护命令或宿主认证的 Web 管理操作驱动、可恢复且可核验的共享贴纸维护闭环，保持普通消息与 Agent 输出隔离。

## MODIFIED Requirements

### Requirement: 贴纸维护必须限制在 plugin-data 和固定目录

系统 MUST 使用 Hermes `plugin_data_dir("hermes-plugin-milky")` 与独立
`plugin_db("hermes-plugin-milky", filename="stickers.db")`。命令输入只来自
`stickers/inbox/`，正式库和隔离目录分别为 `stickers/library/` 与 `stickers/junk/`；命令不得
接受或读取任意路径、URL、URI、符号链接或特殊文件。

Web 上传 SHALL 仅来自宿主认证的显式请求，存入同一 profile 插件持久根中的独立暂存区；不得位于命令递归扫描的 inbox 内。Web 导入只接受已确认归属的不透明批次/文件 ID，不接受服务器路径或远端 URL。

#### Scenario: 维护输入边界

- **WHEN** 维护命令收到固定目录之外的输入
- **THEN** 系统 SHALL 拒绝该输入且不读取目标路径

### Requirement: add 必须先确定性校验去重再调用视觉

`add` SHALL 递归校验非空 PNG、JPEG、GIF、WebP regular file，单文件不超过 `10 MiB`，并以流式
SHA-256 去重。每次命令最多为 50 张唯一候选调用 Hermes `vision_analyze_tool`，同时最多 10 路；
超出部分返回 `batch_deferred` 并留在 inbox。视觉调用必须解析外层 JSON envelope 和内层 analysis
对象，严格校验单选 `emotion`、2–5 个中文 `tags`、20 字以内中文 `description` 和布尔
`is_sticker`。true 原子移动到 library 并写入 `sticker_items`/`sticker_files`，false 原子移动
到 junk；视觉失败、非法结构或移动失败不得伪造成功，源文件留在 inbox。

以上 inbox 扫描和超量保留语义 SHALL 继续适用于命令 add。Web 导入 SHALL 对明确提交的暂存候选复用相同校验、去重、视觉结构、原始格式及成功/隔离规则；失败文件保留在原批次受控暂存区供显式重试，不能移入命令 inbox。Web 批次上限、配额及过期回收 SHALL 遵守 milky-web-dashboard 规范。

#### Scenario: add 校验失败

- **WHEN** inbox 中存在损坏、超限或重复文件
- **THEN** 系统 SHALL 在视觉分析前分类处理且不得伪造导入成功

### Requirement: 维护命令必须有界、懒加载并隔离普通消息

系统 MUST 支持 `add`、`list`、`edit`、`reanalyze`、`del`、`cleanup`、`reindex` 及对应 `--dry-run`/`--limit`
语法。dry-run 不移动、删除或写入贴纸文件、数据库记录或索引。命令贴纸 store 只在有效维护命令中
懒加载，注册、普通连接、普通消息、关键词、Will 和 Agent 输出不得触发维护。handler 只按
`raw_args` 处理，不声明或实现 operator 身份授权。

已授权显式 Web 维护 SHALL 按 Dashboard 生命周期懒加载自己拥有的库资源；Web 浏览仅只读打开已有库，不初始化或迁移存储。Web 入口不依据命令 raw_args 推断授权。

#### Scenario: 普通消息不触发维护

- **WHEN** 插件处理普通消息、关键词、Will 或 Agent 输出
- **THEN** 系统 SHALL 不扫描贴纸目录、不打开贴纸 store 且不调用视觉能力

### Requirement: 结果和日志必须脱敏

命令回执、Web JSON/任务摘要和日志 MUST 只能包含固定安全分类、低基数计数、受限元数据和不透明 ID，不得包含 token、
Authorization、绝对路径、URL、图片 bytes、完整参数、视觉原文或异常正文。贴纸维护失败不得改变
SSE、Gate、Will、buffer、Hermes handoff、reply cost 或出站 sender 状态。

只有通过宿主认证、校验当前 profile 可见条目与文件完整性的 Web 媒体响应 SHALL 交付受限图片 bytes；这不是 JSON/任务摘要或日志的脱敏例外，不能暴露服务器路径、媒体直链或目录。

#### Scenario: 维护失败保持脱敏

- **WHEN** 贴纸维护或存储操作失败
- **THEN** 回执和日志 SHALL 使用固定安全分类且不得包含凭证、路径或完整异常

### Requirement: 贴纸维护必须使用插件持久目录和固定输入边界

贴纸维护 SHALL 使用 Hermes 提供的插件持久目录作为唯一持久化根目录。命令输入目录 SHALL 固定为该根目录下的 `stickers/inbox/`，库文件和元数据 SHALL 位于同一插件持久化根目录的受控子目录或数据库中。系统 MUST NOT 写入插件安装目录、Hermes session DB、任意命令参数指定的路径或用户全局 skills 目录。

Web 上传 SHALL 使用同一 profile 插件持久根内独立于 inbox 的受控暂存区，导入只消费所提交批次确认的候选。只读图库浏览 SHALL 不创建缺失的持久目录或数据库。

#### Scenario: 首次执行 add 创建维护目录

- **WHEN** 操作者首次执行 `/milky sticker add` 且插件持久目录尚不存在
- **THEN** 系统 SHALL 创建固定的 `stickers/inbox/` 和贴纸库所需目录
- **AND** SHALL 只在插件持久目录中创建文件或数据库对象

#### Scenario: 命令参数试图改变输入目录

- **WHEN** 命令参数包含绝对路径、相对路径、`..`、URL、`file://` 或其他输入目录
- **THEN** 系统 SHALL 返回 `invalid_input`
- **AND** SHALL 不读取、下载或写入该值指向的位置

### Requirement: 贴纸维护授权边界暂不由本 change 提供

既有命令入口 SHALL 只按插件 command handler 收到的 `raw_args` 处理贴纸维护参数，不得宣称这些参数一定来自 Milky friend/group，也不得宣称写操作具备 operator-only 边界。插件 MUST NOT 增加操作者 ID、来源判断或第二套授权配置；Hermes core 能否在 handler 前拒绝 canonical `/milky` 不属于本 change 对贴纸写操作来源的保证。授权边界待 core 向 handler 提供可信来源上下文后另行处理。

Web 入口 SHALL 独立复用宿主 Dashboard 的可信访问控制、请求保护、profile 及启用状态，不将 command handler 参数当作 Web 授权证明；Web 认证不改变现有命令来源保证。

#### Scenario: handler 收到贴纸维护参数

- **WHEN** 插件 command handler 收到合法的 `sticker add`、`list`、`edit`、`reanalyze`、`del`、`cleanup` 或 `reindex` 参数
- **THEN** 系统 SHALL 按本 change 的语法、持久化和视觉规则处理参数
- **AND** SHALL 不读取或推断未随 handler 传入的 Milky friend/group、平台或操作者身份

#### Scenario: 不新增插件操作者授权配置

- **WHEN** 部署者配置插件或执行贴纸维护命令
- **THEN** 插件 SHALL 不要求或读取 `MILKY_STICKER_OPERATOR_IDS` 或等价的插件级操作者配置
- **AND** 本 change SHALL 不验证 `allow_admin_from`、`group_allow_admin_from`、`user_allowed_commands` 或 `group_user_allowed_commands` 能否约束贴纸子命令

#### Scenario: 非显式普通流程不触发维护

- **WHEN** 普通消息正文、入站图片、关键词、Will 决策或 Agent 输出没有到达贴纸维护 command handler 的显式参数路径，也没有已授权的显式 Web 维护请求
- **THEN** 系统 SHALL 不执行 add、edit、reanalyze、del、cleanup 或 reindex
- **AND** SHALL 不把贴纸维护作为普通消息旁路或 Agent Tool 暴露

#### Scenario: 普通消息或 Agent 输出触发维护

- **WHEN** 普通消息正文、图片、关键词、Will 决策、Agent 输出或其他事件没有显式匹配维护命令，也没有已授权的显式 Web 维护请求
- **THEN** 系统 SHALL 不执行 add、edit、reanalyze、del、cleanup 或 reindex
- **AND** SHALL 不把贴纸维护作为普通消息旁路或 Agent Tool 暴露

## ADDED Requirements

### Requirement: Web 维护复用既有条目语义且明确批次范围

已授权 Web 操作 SHALL 复用命令维护的图片验证、内容去重、视觉结果结构、字段级人工覆盖、删除引用保护和索引修复语义。浏览/预览 SHALL 只读；上传不自动等于入库，导入必须具有明确候选集合。单项及批量编辑、覆盖清除、重新分析和删除 SHALL 仅处理明确 ID，遵守 Dashboard 的批次上限、版本和持久任务契约；单项字段更新保持原子，批次允许逐项成功并返回真实结果。所有 Web 维护 SHALL 不改变既有 use_count/last_used_at 统计、不发送 QQ 消息，不将维护能力暴露为 Agent Tool。

#### Scenario: Web 与命令遵守相同人工覆盖规则

- **WHEN** Web 编辑或重新分析由命令导入且已有人工覆盖的条目
- **THEN** 指定字段 SHALL 按相同 set/clear 和视觉基线规则更新，未指定字段与人工覆盖按原契约保留
- **AND** 图片、条目 ID 与发送统计 SHALL 不因元数据维护改变

#### Scenario: Web 批次失败可核验

- **WHEN** 一个明确批次中部分候选导入成功，部分视觉失败或被判定为非贴纸
- **THEN** 系统 SHALL 分别报告已提交、visual_unavailable 和 junk 等实际结果
- **AND** 失败输入 SHALL 保留在原批次受控暂存区，非贴纸 SHALL 按原隔离契约处理，不报告全部成功

### Requirement: 多入口维护必须协调跨进程提交与文件读取

同一 profile 图库的命令、Web 及相关本地读取 MUST 共享跨进程一致性边界；不同 profile 不能共享目标或锁定状态。提交前 SHALL 在同一短保护范围内复核条目版本、内容唯一性、文件状态与引用，再提交变更；并发冲突不得覆盖新版本、重复创建相同内容条目或回收正在受保护读取的文件。视觉分析和 Milky 网络请求不得占用整个维护提交保护周期。数据库与文件提交失败 SHALL 保持原有恢复语义，不暴露半条目；无法取得保护 SHALL 返回有界 busy 或 storage_error，不无限等待。

#### Scenario: 两个进程同时导入相同内容

- **WHEN** 命令与 Dashboard 同时对相同图片完成分析并请求入库
- **THEN** 提交时 SHALL 再次去重，只产生一个可见条目
- **AND** 后提交者 SHALL 获得 duplicate 或明确冲突，不覆盖先前人工维护字段

#### Scenario: 视觉返回前条目被编辑

- **WHEN** Web 重新分析期间命令或另一 Web 操作修改了目标条目
- **THEN** 重新分析提交 SHALL 复核所见版本，变化时报告 conflict 并保留新值
- **AND** SHALL 不以较早快照重置人工字段或恢复已删除条目

#### Scenario: 删除与本地读取竞争

- **WHEN** 预览或发送正在验证并一次性读取库文件，另一入口请求删除或清理
- **THEN** 回收 SHALL 遵守短读取保护及引用复核，不破坏在途本地读取
- **AND** 读取结束后的 Milky 网络请求 SHALL 不继续占用维护保护，也不因统计或回收失败重复发送

#### Scenario: 清理计划之后出现新引用

- **WHEN** Web 清理预览后其他入口改变了待处理对象的引用或版本
- **THEN** 执行 SHALL 拒绝过期计划或跳过变化对象并明确说明
- **AND** SHALL 不删除被引用文件、不纳入后来出现的文件，并保持 junk 排除
