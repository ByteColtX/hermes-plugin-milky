# Tasks

## 1. 手动契约冻结和兼容持久化

- [ ] 1.1 固定现有手动 `add/list/edit/reanalyze/del/cleanup/reindex`、`sticker_items`、`sticker_files`、`sticker_send_usage`、`inbox/library/junk` 和字段级 source 行为；用现有手动测试与迁移前后快照验证旧条目、ID、文件、人工覆盖和统计保持不变
- [ ] 1.2 设计并实现增量 schema/version 迁移，旧手动记录只建立内容映射和 unknown 质量状态；用旧 schema、已升级 schema、未知版本、列缺失和事务失败 fixture 验证不重命名、不重分析、不扫描历史消息且不破坏原库
- [ ] 1.3 增加自动 asset metadata、作用域 entry 和自动使用统计的持久化边界，并由统一查询层合并手动共享条目与当前自动 scope；用相同 content ID 的跨 scope、手动旧条目和空库 fixture 验证可见性与 ID 稳定
- [ ] 1.4 增加自动 scope 配置和当前确认 session 解析，默认使用 `dm:<peer_id>`/`group:<group_id>`，只允许显式合法 global；用缺失、非法、temp、未确认 session 和跨 chat 参数测试验证 fail-closed
- [ ] 1.5 让手动和自动 entry 共同参与物理文件引用保护，保持既有发送 claim 时机；用共享 asset、删除一个引用、并发发送、远端成功/失败/未知和统计写入失败测试验证不误删、不重发且只 claim 一次

## 2. 手动维护兼容和自动输入路径

- [ ] 2.1 抽取可复用的图片格式、大小、hash、受控路径和原子提交边界，同时保持手动命令的文件归宿；用现有手动 add/edit/reanalyze/del/cleanup/reindex 回归验证旧行为无变化
- [ ] 2.2 让统一维护服务能够识别手动共享 entry 与自动 scoped entry；用手动 ID、自动 ID、缺失文件、无效索引和跨 scope ID 测试验证维护操作不越权且错误分类固定
- [ ] 2.3 接入当前 `message_receive` 资源解析完成后的自动旁路，只消费当前顶层已 materialize 图片；用 fake pipeline 验证 canonical/dedup/admission/Gate/Will 顺序、历史/reply/forward/wait 排除和普通 handoff 不变
- [ ] 2.4 实现内部 staging 的 TTL、单图大小、总量、并发和取消边界，不读写人工 inbox/junk；用重复图片、过期、取消、staging 失败和命令图片测试验证不产生双重收集或隐式维护
- [ ] 2.5 验证自动旁路与 `add-milky-relationship-system` 的 observer、工具注册和生命周期合并顺序；用 fake integration 验证两套数据库/表/事件不互相覆盖且任一旁路失败不改变 Hermes handoff

## 3. 自动质量判定和可恢复入库

- [ ] 3.1 实现 PNG/JPEG/GIF/WebP、非空、regular file、可读性、大小和内容 hash 硬门禁；用正负图片、损坏、超限、非图片、符号链接和重复 fixture 验证拒绝不创建 entry
- [ ] 3.2 接入 Hermes 已确认的辅助视觉能力，解析固定 envelope 和有限的 sticker/screenshot/news/chat_capture/document/photo/poster/qr_code/other 结果；用脱敏正负样本验证不记录自由文本理由
- [ ] 3.3 实现 accept/reject/defer、privacy risk 和 classifier unavailable/malformed 降级，并保存有限质量、category、tags 和 classifier version；用 unknown、超时、能力不可用、字段缺失和低置信度 fixture 验证删除 staging、不伪造成功
- [ ] 3.4 实现 content-addressed 文件原子提交、手动/自动 entry 引用建立和 orphan/missing_file 诊断；用文件写入失败、数据库失败、中断恢复、共享引用和 cleanup dry-run 验证引用优先、不误删
- [ ] 3.5 验证自动重复命中手动条目或同 scope 自动条目时不重新视觉、不覆盖人工字段、不增加文件或统计；用手动 edit 后重复图片和跨 scope 同 hash fixture 验证隔离

## 4. 固定 ToolSpec 和发送/纠错边界

- [ ] 4.1 注册 `sticker_categories`、既有契约的 `sticker_search`/`sticker_send` 和 `sticker_forget`，并与 `add-sticker-search-and-id-send` 合并为单一 ToolSpec；用工具发现测试验证注册无网络、无存储创建、无重复名称和无 category/keyword/index 冲突
- [ ] 4.2 在 Tool handler 和既有 pre-tool 检查中验证当前 Milky session、可见性、参数白名单、opaque ID、scope/target/path/URL 拒绝；用空值、bool 冒充整数、未知字段、跨 chat、temp、旧手动 ID 和任意 URI 测试验证网络/写入前失败
- [ ] 4.3 实现 categories/search 对“手动共享 + 当前自动 scope”联合可见集合的有界只读查询；用空库、相关性/limit、缺文件、损坏索引、跨 scope 条目和恶意元数据测试验证不泄露路径、URL、hash、统计或正文
- [ ] 4.4 让 `sticker_send` 复用既有查询/ID 选择、当前目标、文件完整性、大小限制、一次读取和一次 native Action；用手动/自动条目、成功、rejected、malformed、transport unknown、缺文件和统计失败测试验证 claim 时机、不重发和不换图
- [ ] 4.5 实现 `sticker_forget` 只删除当前自动 scope entry，并让底层文件按共享引用延迟清理；用自动误收、手动 ID、跨 scope ID、仍被引用 asset 和 orphan cleanup 测试验证不越权
- [ ] 4.6 验证普通消息、关键词、Will、Agent 输出和视觉结果不能隐式触发 send/forget/手动维护；用 pipeline、Tool handler 和 command fixture 验证所有状态变化都来自显式固定入口

## 5. 生命周期、错误和文档契约

- [ ] 5.1 实现手动命令/Tool 的懒加载和短生命周期关闭，以及自动任务的卸载、断开、reload 取消与 staging 清理；用 register、connect、disconnect、reload、多 client 和普通消息 fixture 验证无注册副作用且已提交数据保留
- [ ] 5.2 统一自动与手动失败分类、回执和低敏日志；用存储、权限、视觉、文件、跨 scope 和未知发送结果测试断言不输出 token、Authorization、URL、绝对路径、bytes、原始参数、异常正文或视觉自由文本
- [ ] 5.3 同步 `ARCHITECTURE.md`、`README.md`、plugin manifest、bundled skill 和相关主规范任务，明确手动基座、自动 scope、质量门控、工具契约和未验证边界；用文档搜索验证没有宣传未交付或冲突参数
- [ ] 5.4 更新与 `add-sticker-search-and-id-send`、`add-milky-relationship-system` 的合并说明和 evidence ledger；用变更间交叉检查确认表、ToolSpec、pipeline hook、统计和授权语义一致

## 6. 集成验证和交付证据

- [ ] 6.1 补充 fake Hermes/Milky 集成 fixture，覆盖旧手动库迁移、手动维护回归、friend/group 自动 scope、global 配置、当前图片自动收集、拒绝分类、共享文件、查询、发送、forget 和普通 handoff 隔离
- [ ] 6.2 运行聚焦测试及项目质量门禁：`uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`；将失败区分为契约、实现、fake host 或环境问题
- [ ] 6.3 运行 `openspec validate --changes --strict`，确认 proposal、五份 spec、design、tasks 的手动兼容、工具参数、作用域和错误分类一致
- [ ] 6.4 更新 evidence ledger，区分 fake host、真实 Hermes 视觉能力和真实 Milky 发送证据；默认只做只读 smoke，任何真实发送或上传必须取得明确授权，未确认边界保持 `unsupported`/`blocked`
