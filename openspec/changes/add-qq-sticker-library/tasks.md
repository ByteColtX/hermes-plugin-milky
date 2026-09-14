## 1. 契约、配置和持久化基础

- [ ] 1.1 增加 sticker scope 配置解析，默认使用当前 `dm:<peer_id>`/`group:<group_id>`，仅允许显式合法的 global 配置；用配置单元测试验证缺失、非法和 global 场景不猜测目标
- [ ] 1.2 建立独立的 sticker storage 模块和 schema version，使用 `plugin_db("hermes-plugin-milky", filename="stickers.db")` 与 `plugin_data_dir()` 下的 sticker 文件目录；用 schema 初始化、重载和路径边界测试验证不触及 Hermes session DB
- [ ] 1.3 实现 `sticker_asset`/`sticker_entry` 的作用域、SHA-256 content ID、quality class/score、classifier version、category/tag、usage 字段和 `(scope_key, content_id)` 去重；用 store 单元测试覆盖 duplicate、跨作用域隔离、空库和损坏记录
- [ ] 1.4 实现接受图片的 MIME/大小/常规文件校验、临时文件原子写入、引用优先清理和 missing/orphan 诊断；用 PNG/JPEG/GIF/WebP、超限、非 regular file、写入失败和 cleanup 测试验证不留下假成功

## 2. 入站自动收集旁路和质量判定

- [ ] 2.1 在现有 trigger 资源解析完成后接入自动收集旁路，只读取当前顶层已 materialize 图片，不处理历史/reply/forward/wait 图片；用 pipeline fake resolver 测试验证 Gate/Will 顺序、零重复下载和既有 handoff 不变
- [ ] 2.2 实现受 TTL、单图大小、总量和并发上限约束的内部 staging 与任务句柄，不向 Agent 暴露 candidate ID；用过期、取消、staging 失败、并发限制和自动清理测试验证 fail-closed
- [ ] 2.3 实现确定性质量 gate，拒绝不支持格式、损坏、空、超限和不可读图片；用边界图片 fixture 验证拒绝结果不会创建 asset/entry 且不阻断 Hermes handoff
- [ ] 2.4 复用 Hermes 已有视觉能力执行固定结构的 sticker/screenshot/news/chat_capture/document/photo/poster/qr_code/other 分类；用脱敏正负样本 fixture 验证截图、新闻、聊天记录、文档、二维码、普通照片和低质量图片不入库
- [ ] 2.5 实现保守的 accept/reject/defer 策略、有限 category/tags 和 classifier unavailable/malformed 降级；用视觉能力不可用、超时、unknown 和 malformed 测试验证删除 staging、不降低门槛、不伪造收藏成功
- [ ] 2.6 将自动分类任务加入 pipeline/adapter 生命周期管理，确保视觉任务不阻塞正常 handoff；用 fake host 测试验证任务取消、卸载清理和普通消息继续交接

## 3. 固定 ToolSpec、授权和纠错

- [ ] 3.1 注册 `sticker_categories`、`sticker_search`、`sticker_send` 和 `sticker_forget` 固定 ToolSpec，确认自动收集不作为 Agent Tool；用工具发现和参数边界测试验证注册阶段无网络/图片读取/视觉调用副作用
- [ ] 3.2 增加 sticker 专用 `pre_tool_call` 授权与安全审计，并在 handler 内重复校验当前 platform、session、chat scope 和 target；用跨群、temp、未确认 session、任意路径/URL/资源 URI 注入测试验证网络和 mutation 前拒绝
- [ ] 3.3 实现 `sticker_categories`/`sticker_search` 的当前作用域查询，返回紧凑元数据且不泄露路径、URL、正文、bytes 或视觉自由文本；用 category/keyword/tag/limit、空库、损坏 DB 和缺文件测试验证结果边界
- [ ] 3.4 实现 `sticker_send` 复用现有 Milky image sender、目标解析和 materialization，最多一次网络发送，仅在确认成功后更新 usage；用成功、rejected、unsupported、transport unknown、缺文件和重复工具调用测试验证不重发不计数
- [ ] 3.5 实现 `sticker_forget` 的当前作用域删除和共享 asset 引用计数保护；用误收条目、跨 scope ID、仍被引用 asset 和 orphan cleanup 测试验证不越权删除

## 4. 运维、导入和生命周期

- [ ] 4.1 提供受权限控制的 import/list/cleanup/reindex CLI 及 `--dry-run`，导入目录沿用同一 MIME、大小、hash 和质量策略；用 dry-run 断言无文件/数据库写入，并覆盖不支持文件、截图/新闻拒绝和重复导入
- [ ] 4.2 接入懒加载、`ctx.on_unload()` 关闭、自动分类任务取消、staging 清理和 plugin reload 数据保留；用注册阶段、首次使用、卸载、重载、数据库不可用和 schema 不兼容测试验证不阻断普通 Milky handoff
- [ ] 4.3 更新 `ARCHITECTURE.md`、`README.md`、plugin manifest/配置说明和 bundled skill，明确自动质量门控、scope、四个工具、运维命令和拒绝边界；用文档搜索和 manifest 能力检查验证没有宣传未交付能力
- [ ] 4.4 与 `add-milky-relationship-system` 的工具注册、pipeline observer 和生命周期改动进行合并复核，保持独立数据库/表/事件语义；用两套 change 的 fake integration 回归验证没有覆盖注册或改变关系规则

## 5. 集成验证和交付证据

- [ ] 5.1 补充 fake Hermes/Milky 集成 fixture，覆盖 friend/group、Gate deny、wait/trigger、当前图片自动分类、截图/新闻排除、自动入库、Tool 调用、native send、forget 和 storage/classifier 失败；用脱敏测试断言不输出 token、URL、路径、bytes、视觉理由原文或敏感正文
- [ ] 5.2 运行相关聚焦测试并按项目标准运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`；将失败按契约、实现、fake host 或环境问题分类
- [ ] 5.3 运行 `openspec validate --changes --strict`，修复 artifact/schema/链接问题并确认所有任务、规范和设计状态一致
- [ ] 5.4 更新 evidence ledger，明确哪些行为只在 fake host 验证、哪些 Hermes/Milky 视觉与实机边界仍为 `unsupported`；默认只做只读 smoke，任何真实发送或上传必须单独取得明确授权后再验证
