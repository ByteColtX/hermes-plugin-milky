## Context

实际 `hermes-dev` 使用的 Hermes host 仍在 `gateway/platforms/base.py` 中将本地附件
路径传给 Milky adapter 的 native 入口；当前 host 没有 outbound materialization seam。
`61d99fc` 删除 plugin 的本地 materialization 后，本地图片、语音、视频和文档都在
Milky 网络边界前失败。

本次重构选择恢复 plugin-owned materialization。plugin 不负责 Hermes 入站附件的下载、
缓存或权限策略，但必须在自己的 Milky Action 边界将 host 传来的本地文件转换为 Milky
可接受的 URI，并提供一个有限、明确的本地文件安全边界。

## Goals / Non-Goals

**Goals:**

- 兼容当前 Hermes host 传入的本地路径、`Path` 和 `file://localhost`。
- 只读一次常规、非空且不超过 8 MiB 的本地文件，并生成 `base64://` URI。
- 保持远端 URI 零下载、显式 Base64 零解码、原生媒体 segment、独立文件 upload、
  group/dm 路由和单次 Action 语义。
- 让 direct sender、adapter 和真实 Hermes `BasePlatformAdapter` dispatch 都覆盖同一
  materialization 实现。
- 继续隐藏本地路径、URI、Base64 内容、完整异常和凭证。

**Non-Goals:**

- 不修改 Hermes core 或要求当前 host 提供额外 seam。
- 不下载 `http(s)://`，不解码或重新编码显式 `base64://`。
- 不创建持久化媒体缓存、HTTP 文件服务、SSRF 规则副本或任意 Action catalog。
- 不改变 Milky Action schema、入站资源 resolver、CQ 解析或 standalone 的文本范围。

## Decisions

### 1. plugin 拥有受限的本地 materialization

`milky.client.materialize_media_uri()` 是唯一的本地读取入口，并在工作线程执行阻塞
文件 I/O。输入支持 `Path`、普通本地路径和 `file://localhost/<path>`；路径必须能解析
为常规文件，文件必须非空且不超过 8 MiB。读取最多 `MAX_LOCAL_MEDIA_BYTES + 1`
字节，以防止并发或竞态绕过大小检查；成功后返回 `base64://` 加标准 Base64 内容。

`http(s)://` 和 `base64://` 输入只经过 URI 形状校验并原样返回。其他 scheme、远端
`file://`、目录、空文件、超限文件和无法读取的路径返回安全分类，不把输入写入异常。

### 2. 所有 native/file 入口复用同一 materializer

adapter 和 sender 都调用 outbound materialization helper：adapter 先做连接和目标门禁，
sender 也可独立处理本地输入；adapter 传出的已生成 Base64 URI 在 sender 中不会再次读
文件。文档先从原始本地路径确定安全文件名，再使用生成 URI 上传。

### 3. 保持媒体与文件的协议边界

图片、语音和视频只生成 `image`、`record`、`video` segment，并按目标选择
`send_group_message` 或 `send_private_message`。文档只调用 `upload_group_file` 或
`upload_private_file`，不生成 `file` message segment。每个附件的副作用 Action 最多
调用一次，失败不发送第二次纯文本 fallback。

### 4. 通过真实 host dispatch 锁定兼容性

真实 Hermes host 测试应验证其现有方法解析到 Milky 的覆盖入口，并使用临时文件验证
本地路径最终到达 native/upload Action。fake client 和 local HTTP fixture 验证请求体、
Base64、结果 ID、失败分类及敏感信息不泄露。

### 5. 把通用媒体入口作为 Agent 能力提示

Hermes 会解析普通 Agent 最终回复中的 `MEDIA:<local_path>`，也会解析显式
`send_message` 调用的 `message` 参数，再按扩展名调用 adapter 的 `send_image_file`、
`send_voice`、`send_video` 或 `send_document`。因此 plugin 的 `platform_hint` 必须直接说明
这两种入口，并明确它们独立于 23 个固定 QQ ToolSpec。QQ tools skill 也重复这条边界，避免
Agent 把“没有名为 `send_video` 的 ToolSpec”误判为“不能发视频”。只有发送入口返回失败时，
Agent 才能向用户报告能力或发送失败。

## Risks / Trade-offs

- [plugin 读取本地文件扩大资源边界] → 固定 8 MiB 上限、常规文件检查、非空检查、单次
  读取和错误脱敏；Hermes host 的路径过滤仍是上游输入门禁。
- [文件大小在检查后发生变化] → 从同一已打开文件描述符读取并额外读取一字节；超过上限
  即拒绝，不发送部分内容。
- [Base64 使请求体变大] → 保持历史 8 MiB 上限；不引入无法确认的远端文件服务。
- [多个附件部分成功] → 按顺序逐项发送，返回首个失败和已成功 ID，不重试未知结果。
- [文件名无法从 Base64 推导] → 要求显式安全文件名，在 Milky 网络前返回 `invalid_input`。

## Migration Plan

1. 用真实临时文件覆盖四类本地附件、URI 类型、空文件和 8 MiB 边界。
2. 恢复 plugin materializer，并让 adapter、sender 和 file uploader 复用它。
3. 通过实际 Hermes host dispatch 回归确认当前 host 无需 seam 即可调用 native/upload 入口。
4. 部署 plugin 后观察 `send_video` 对应的 Milky native segment；若失败只按 Action 分类
   诊断，不发送路径文本或告警 fallback。
