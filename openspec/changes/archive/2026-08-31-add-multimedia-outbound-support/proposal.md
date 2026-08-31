## Why

当前 Milky 的 `MilkyOutboundSender` 已有图片、语音、视频和文件上传实现，但
`MilkyAdapter` 尚未覆盖 Hermes 的媒体发送入口，Hermes 将工作区资源交给 adapter 后会落入
基类的文本 fallback，用户因而收不到原生多媒体消息。当前已确认的本地文件兼容路径是将
显式选中的文件编码为 `base64://` 后交给 Milky upload 或 message Action；需要把这一边界
接通并在代码、文档和测试中固定下来。

## What Changes

- 将 `MilkyAdapter` 的图片 URL、本地图片、动画、语音、视频和文档发送入口接到现有
  `MilkyOutboundSender`，让 Hermes 的普通媒体投递路径实际执行 Milky Action。
- 为本地图片、语音、视频和文件建立统一的 `base64://` materialization 方案；显式的可达
  `http(s)://` URI 按已确认的远端 URI 契约处理，不把本地路径直接发送给 Milky。
- 保留图片、语音和视频的 native message segment；文件继续使用独立的
  `upload_group_file` / `upload_private_file`，不把 file 放入 message segment。
- 保持 `group:<id>` / `dm:<id>` 路由、文件名校验、远端 `message_seq` / `file_id` 结果和
  `rejected`、`transport_unknown`、`malformed`、`unsupported` 错误边界。
- 为 Hermes 的 `MEDIA:<path>` 和工作区明确文件路径增加安全、可观察的端到端测试，并避免
  日志、错误和用户可见文本泄露本地路径、凭证或完整资源内容。
- 更新 `ARCHITECTURE.md`、`README.md` 和相关 OpenSpec 说明，明确 `base64://` 是当前本地
  资源的临时兼容方案、会完整读入内存、存在大文件限制风险，并标记 adapter 接线完成状态。

## Capabilities

### New Capabilities

无。多媒体出站属于现有 `outbound-messaging` capability 的扩展。

### Modified Capabilities

- `outbound-messaging`: 将图片、语音、视频和本地文件从 sender 内部能力扩展为 Hermes
  adapter 可实际调用的出站能力，并固定本地资源使用 `base64://` 的 materialization、远端
  URI 边界和独立文件上传行为。

## Impact

- 影响 `adapter.py`、`outbound/sender.py`、`milky/client.py`、`outbound/file_upload.py`、
  相关 fake client/adapter 测试、`README.md` 和 `ARCHITECTURE.md`。
- 不修改 Hermes core；复用 Hermes 已有的 `MEDIA:` 解析、路径安全过滤和媒体投递入口。
- 不新增 Agent-callable 的任意 Milky Action，不改变入站资源补全、Gate/Will、SSE 或
  `channel_context` 契约。
- `base64://` 会使请求体随资源大小膨胀并增加内存、超时和代理限制风险；本 change 必须
  保留可诊断失败，并在文档中明确这是临时方案而非通用大文件传输方案。
