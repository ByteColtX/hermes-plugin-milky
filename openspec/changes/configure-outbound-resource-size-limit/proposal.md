## Why

当前出站本地资源的 `8 MiB` 上限硬编码在 materialization 边界，无法适配默认通过内网连接
Milky、需要发送更大图片或媒体的部署。应将该限制纳入启动配置，并将默认值提高到 `32 MiB`，
同时保留在网络访问前拒绝超限本地文件的安全行为。

## What Changes

- 新增可选启动配置 `MILKY_MAX_LOCAL_MEDIA_BYTES`，以字节数配置本地出站资源上限，默认
  `33554432`（`32 MiB`），合法范围为 `8 MiB` 到 `32 MiB`（含边界）。
- 将解析后的上限传递给图片、语音、视频、文档和 CQ sticker 的本地 materialization；文件在
  超限前拒绝读取完整内容和调用 Milky Action，并继续返回 `invalid_input`。
- 将配置值纳入安全配置摘要和 manifest/README 配置说明；配置错误只指出配置名和固定错误类别。
- 更新出站契约和测试，将原来写死的 `8 MiB` 边界改为启动配置值，覆盖默认值、合法边界、非法
  值、准确上限和超限文件。
- 保持合法 `http(s)://` 与显式 `base64://` URI 原样传递；插件不下载、解码或探测远端资源，
  本 change 不新增单条消息附件总量限制。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `configuration`：增加 `MILKY_MAX_LOCAL_MEDIA_BYTES` 的启动解析、默认值、值域和 manifest
  配置契约。
- `outbound-messaging`：将本地出站资源和 CQ sticker 的固定 `8 MiB` 限制改为配置值，并保留
  本地超限的网络前拒绝及远端/显式 URI 的既有边界。
- `security-boundaries`：将出站本地 materialization 的固定 `8 MiB` 安全边界改为启动配置
  值，并保持不下载远端资源、不记录路径和内容的约束。

## Impact

- 影响 `config/__init__.py`、`plugin.yaml`、`milky/client.py`、adapter/sender/file upload 的
  materialization 接线，以及相关配置、媒体和出站测试。
- 影响 `openspec/specs/configuration/spec.md`、`openspec/specs/outbound-messaging/spec.md`、
  `README.md` 和 `ARCHITECTURE.md` 中的配置与大小限制说明。
- 不改变 Milky HTTP Action、SSE、消息 segment、文件 upload schema、远端 URI 处理或 Hermes
  入站资源所有权；当前实现仍需在后续 apply 阶段修改，以上能力不是本 proposal 已交付行为。
