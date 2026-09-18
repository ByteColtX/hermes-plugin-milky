## Why

当前 Milky 插件已经提供独立的 `stickers.db`、显式 `/milky sticker` 人工维护流程和受限的
`sticker_send`；但它还不会从当前入站图片自动收集贴纸，也没有按 QQ 会话隔离的 asset/entry
模型、自动库的搜索/纠错工具。本 change 在现有库和发送边界上扩展能力，让系统在图片进入当前
消息资源边界后自主判断是否是高质量贴纸，避免要求用户或 Agent 先发起收藏动作。

## What Changes

- 在现有贴纸库上增加按图片内容 SHA-256 去重的 asset/entry 模型，分离共享文件实体和作用域内的分类条目；迁移必须保留已有人工条目、文件和使用统计。
- 新增可配置的 sticker library scope；默认按当前 QQ 会话隔离，显式配置后才允许跨会话共享。
- 新增固定的 `sticker_categories`、`sticker_search` 和 `sticker_forget` ToolSpec，并将现有
  `sticker_send` 调整为新 library 契约；自动收藏是内部旁路，不开放任意资源 URI、文件路径或
  Milky Action catalog。
- 在资源解析成功后自动检查当前消息的顶层图片，先执行格式、大小和可读性过滤，再使用 Hermes 已有视觉能力判断贴纸质量；截图、新闻、聊天记录、文档、二维码、普通照片和低置信度图片不得进入长期库。
- 复用 Hermes 入站资源 helper 和现有 Milky 出站 materialization；自动收藏不新增下载器或远端缓存，发送不绕过现有群聊/私聊路由和大小限制。
- 使用 Hermes `plugin_db()` 和 `plugin_data_dir()` 保存元数据及 content-addressed 文件；提供导入、清理、重建索引和 dry-run 运维入口。
- 支持自动分类、有限标签、质量判定、使用次数和最近使用时间；无法确认质量时跳过收藏而不是降低门槛。
- 记录固定工具的授权、失败分类和低基数统计；不记录 token、远端媒体 URL、本地绝对路径、原始图片 bytes 或敏感正文。

## Capabilities

### New Capabilities

- `qq-sticker-library`: 定义 QQ sticker 的导入、候选收藏、内容去重、作用域、分类/标签、搜索、发送、使用统计、清理和安全降级行为。

### Modified Capabilities

- `hermes-message-pipeline`: 明确资源 resolver 完成后当前消息图片如何进入自动质量判定，并保持 Gate/Will、历史上下文、当前正文和 Hermes handoff 边界。
- `qq-action-tools`: 在保留现有 `sticker_send` 的基础上增加固定、可审计的贴纸 ToolSpec，并定义自动收藏不经 Agent Tool、参数校验、当前会话目标和一次副作用调用边界。
- `security-boundaries`: 增加自动收集输入的会话归属、作用域隔离、路径不可由 Agent 提交、发送/删除工具授权和安全日志要求。
- `plugin-lifecycle`: 增加 sticker SQLite/file store 的懒加载、关闭、清理和重载语义，保持注册阶段无网络和无长期任务。

## Impact

- 影响 `__init__.py`、`adapter.py`、`inbound/pipeline.py`、`inbound/hermes_mapper.py`、`milky/resources.py`、`outbound/tools.py` 和新增 sticker store/quality/service 模块。
- 扩展现有 `plugin_db("hermes-plugin-milky", filename="stickers.db")` 与
  `plugin_data_dir("hermes-plugin-milky")` 的持久化边界；必须兼容已有人工贴纸库，Hermes core 不修改。
- 需要补充脱敏的 store、自动分类质量 fixture、任务生命周期、ToolSpec、跨会话授权、出站发送结果和 fake Hermes 集成测试，并同步 `ARCHITECTURE.md`、`README.md` 与相关主规范。
- 与未完成的 `add-milky-relationship-system` 共享 `outbound/tools.py`、`inbound/pipeline.py` 和插件数据库生命周期；实现时必须保持两者表、hook 和错误边界相互隔离。
- 非目标包括：复制 Hermes 下载/SSRF/cache、建立通用 `asset://` 资源仓库、修改 Hermes core、引入独立的 Agent queue/Will 系统、处理历史/reply/forward/wait 图片，以及提供绕过质量门控的强制收藏接口。
