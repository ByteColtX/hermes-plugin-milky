## Why

当前插件已经交付了显式 `/milky sticker` 手动维护、独立 `stickers.db`、受控的
`inbox/library/junk` 文件目录和贴纸发送能力，但普通入站图片仍不会沉淀为可复用条目。本 change
在这套已交付的手动维护契约上增加自动收集和按会话可见性，而不是重做或替换现有贴纸库。

## What Changes

- 保留现有 `sticker_items`、`sticker_files`、`sticker_send_usage`、文件目录和
  `/milky sticker add/list/edit/reanalyze/del/cleanup/reindex` 的可观察行为；已有条目、文件、
  opaque ID、人工字段覆盖和使用统计必须在升级后保持可用。
- 以增量 schema 扩展自动收集所需的内容资产、质量元数据和作用域条目；迁移不得把旧手动记录
  直接改造成按会话条目，也不得因首次启用而重复导入或覆盖旧文件。
- 在当前图片完成 Hermes 资源 materialization 后增加内部自动收集旁路，默认把新自动条目绑定到
  当前 `dm:<peer_id>` 或 `group:<group_id>`；只有显式配置才允许自动条目进入 `global`。
- 自动收集复用既有图片校验、受控文件存储、媒体大小和出站 materialization 边界，但使用内部
  staging，不扫描或改写人工 `inbox/junk`，也不进入 Agent Tool、普通正文或主 Agent transcript。
- 使用内容 hash 复用物理图片；同一作用域内不得产生重复自动条目，人工共享条目和其他作用域的
  自动条目不得因此互相泄露分类、标签或使用统计。
- 继续使用 Hermes 已有视觉能力执行严格的格式、质量、可复用性和隐私门控；未知、malformed、
  超时或能力不可用时安全跳过，不降低手动维护的 `is_sticker` 入库门槛，也不报告假成功。
- 增加固定的分类查询和自动条目纠错能力；`sticker_search` 与 `sticker_send` 沿用现有及
  `add-sticker-search-and-id-send` 的 intent/emotion/tags、opaque ID 和一次发送契约，不在本
  change 中重新定义互相冲突的 `category/keyword/index` 参数。`sticker_forget` 只允许删除当前
  会话可见的自动条目，人工条目仍由显式维护命令管理。
- 自动条目和既有人工条目共享统一的可恢复清理、缺失文件诊断和发送统计边界；发送统计沿用
  现有“已发起发送调用后 claim 一次、远端结果不回滚”的语义。
- 保持注册阶段无网络、无图片读取和无长期分类任务；维护命令不新增插件级 operator 身份配置，
  自动旁路、Agent Tool 和出站目标仍必须使用已确认的当前会话边界。

## Capabilities

### New Capabilities

- `qq-sticker-library`: 定义在既有手动库上增加自动收集、作用域可见性、质量门控、分类查询、自动条目纠错和兼容迁移的行为。

### Modified Capabilities

- `hermes-message-pipeline`: 增加当前消息顶层图片进入自动收集旁路的边界，并保持显式手动命令路径独立。
- `qq-action-tools`: 增加自动条目的固定查询/纠错工具，同时沿用既有贴纸搜索和发送契约。
- `security-boundaries`: 区分自动/Agent 当前会话授权与既有手动命令不声明来源授权的边界。
- `plugin-lifecycle`: 扩展手动贴纸库的懒加载、兼容迁移、自动任务取消和重载保留语义。

## Impact

- 影响 `inbound/pipeline.py`、`inbound/commands.py`、`outbound/tools.py`、贴纸维护/发送服务和
  插件生命周期绑定；Hermes core、普通消息 handoff、Gate、Will、wait 和 sender 责任边界不变。
- 扩展既有 `stickers.db` 与 plugin-data 下的受控文件库，必须兼容已交付的手动 schema、命令和
  `sticker_send`，并使物理文件在人工条目和自动条目之间可恢复地共享。
- 需要增加自动收集、作用域隔离、旧库迁移、工具参数、任务取消、质量拒绝和文件引用保护测试，
  以及同步 `ARCHITECTURE.md`、`README.md`、manifest/skill 和相关主规范的任务。
- 与 `add-sticker-search-and-id-send`、`add-milky-relationship-system` 共享工具注册或 pipeline
  入口时，必须通过合并回归保持各自的表、hook、ToolSpec 和错误分类，不直接覆盖另一 change 的契约。
- 非目标包括：把旧手动条目追溯迁移为按会话条目、复制 Hermes 下载/SSRF/cache、引入任意路径或
  远端导入、开放任意 Action catalog、提供绕过质量门控的 Agent 收藏、改变手动命令的 operator
  授权声明，或修改 Hermes core。
