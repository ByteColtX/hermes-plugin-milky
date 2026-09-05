# Changelog

## [1.2.0] - 2026-09-05

### 新增

- 将固定 QQ ToolSpec 从 17 个扩展到 25 个，新增 `get_group_file_download_url`、
  `get_group_files`、`accept_group_request`、`reject_group_request`、
  `accept_group_invitation`、`reject_group_invitation`、`get_friend_info` 和
  `set_group_member_special_title`。
- 支持严格独立行 `[SPLIT]` 控制出站文本，按顺序最多发送三条消息；空段、相邻空白行和
  长度预检遵循固定边界。
- 支持合法 friend/group `message_recall` 事件写入 context-only system context FIFO，不触发
  Agent、Will 或 Milky Action。
- 入站 face segment 支持使用插件内置 catalog 显示中文名称，并对 emoji pack、无效条目、
  冲突名称和缺失目录安全回退。
- 同一 trigger 内的重复入站图片支持按内容去重，并同步正文、媒体路径和 MIME 类型。
- 新增 `MILKY_MAX_LOCAL_MEDIA_BYTES`，默认值为 32 MiB，允许范围为 8–32 MiB，用于限制
  出站本地图片、音频、视频、CQ sticker 和文件上传的读取。

### 变更与修复

- 将 Milky 平台操作指引迁移到连接后渲染的 system prompt section，并注入已确认的 QQ UID
  和昵称；补充 `MEDIA:`、`[SILENT]`、`[SPLIT]` 和 CQ-compatible 语法说明。
- CQ sticker 的本地图片统一经过 materialization 后再发送，避免将本地路径直接交给 Milky。
- 修正自引用消息的 `your_previous_msg` 上下文标记，以及撤回事件的管理员文案判定。
- `/milky` 从返回原始 JSON 改为固定中文摘要，仅展示已确认的实现和协议字段。
- 统一 Milky QQ CQ reference 和 Action tools skill 命名，补充 face ID 和群文件参考资料。

### 已知边界

- Slash command 当前没有独立的发送者授权；ToolSpec 当前没有独立的调用者和目标授权，建议
  仅在成员可信且目标受控的会话中启用。
- 本版本自动化测试覆盖 fake Hermes、fake Milky transport 和脱敏 fixture；真实 Hermes 宿主
  与真实 Milky 服务的完整链路仍需在目标部署环境中验证。
