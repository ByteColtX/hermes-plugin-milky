## Why

`61d99fc` 将本地附件 materialization 完全移出 Milky plugin，但当前 Hermes host
仍按既有 `BasePlatformAdapter` 契约把本地路径传给 `send_image_file()`、
`send_voice()`、`send_video()` 和 `send_document()`。实际部署因此在进入 Milky
Action 前统一得到 `unsupported`，而不是发送附件。

这不是 Milky 协议拒绝，也不是 Hermes host 未正确识别附件；是 plugin 删除了当前
host 仍需要的本地路径转换。应当重构当前方案，恢复 plugin 内受限、可审计的本地
文件读取和 `base64://` 编码，而不是要求当前 Hermes host 先升级一个不存在的 seam。

## What Changes

- 在 plugin 的 outbound materialization 边界恢复本地路径、`Path` 和
  `file://localhost` 的受限读取。
- 对本地文件执行一次常规文件检查、非空检查和 8 MiB 大小上限，再生成
  `base64://` URI；不把本地路径或文件内容写入日志、异常或 `SendResult`。
- 保持 `http(s)://` 和显式 `base64://` 原样传递，不在 plugin 下载远端 URI 或重复解码。
- 删除对 Hermes outbound materialization seam 的运行时依赖；当前 Hermes host 无需修改
  即可进入 Milky native media/file 发送边界。
- 图片、语音和视频继续发送 native message segment，文档继续使用独立 file upload。
- 补充真实本地临时文件、路径格式、大小边界、失败分类和 host dispatch 回归。

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `outbound-messaging`: plugin-owned local attachment materialization and native delivery.

## Impact

- Affects `milky/client.py`, `outbound/materialization.py`, `outbound/sender.py`,
  `outbound/file_upload.py` and `adapter.py`.
- Hermes core 不需要修改；其现有本地路径安全过滤仍在调用 plugin 前生效，plugin 只在
  Milky 传输边界负责常规文件、空值和大小检查。
- 不新增配置项，不下载 URL，不建立第二套持久化媒体缓存，不把文件塞进 message segment。
- 更新脱敏 fixture、local HTTP integration、文档和 OpenSpec 证据台账。
