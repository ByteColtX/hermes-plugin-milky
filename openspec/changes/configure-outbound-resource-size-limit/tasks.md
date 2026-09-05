## 1. 配置契约与 manifest

- [x] 1.1 在 `config/__init__.py` 增加 `MILKY_MAX_LOCAL_MEDIA_BYTES` 的默认值、`8 MiB` 至 `32 MiB` 值域、十进制字节解析和 `MilkyConfig.max_local_media_bytes`，验证 `tests/test_config.py` 覆盖省略默认值、`8 MiB`/`32 MiB` 边界、`16 MiB` 自定义值及空值/非整数/越界拒绝
- [x] 1.2 将 `MILKY_MAX_LOCAL_MEDIA_BYTES` 加入 `plugin.yaml` 的 optional env 和安全配置摘要，验证 manifest 配置检查与摘要不包含 token、Authorization、路径或资源内容

## 2. 出站 materialization 接线

- [x] 2.1 将本地 materialization 的大小上限改为显式参数，保留 `stat`、`limit + 1` 读取、常规文件/非空校验、`base64://` 编码和 `invalid_input` 分类，并验证 helper 默认值与显式值行为一致
- [x] 2.2 将已解析的配置值接入 adapter、`MilkyOutboundSender`、`FileUploader`、standalone sender 及 CQ sticker、`MEDIA:` 图片/语音/视频/文档路径，验证所有本地出站入口使用同一上限且不重复读取中间 `base64://`
- [x] 2.3 验证本地文件恰好达到配置上限时成功、超过配置上限时在网络访问前失败且不调用 message/upload Action；覆盖默认 `32 MiB` 和自定义 `16 MiB` 两组边界
- [x] 2.4 验证合法 `http(s)://` 与显式 `base64://` 仍原样传递，不下载、读取、解码或应用本地文件大小检查；验证远端 `file://`、目录、空文件和未知 scheme 的既有分类不变

## 3. 契约回归与安全边界

- [x] 3.1 更新 `tests/test_multimedia_outbound.py`、`tests/test_outbound.py` 及相关 adapter/standalone 测试，将原有 `8 MiB` 断言改为配置驱动，并覆盖 CQ sticker、图片、语音、视频和独立文件上传
- [x] 3.2 增加配置值向各出站入口传播的 fake 集成测试，验证超限时不生成部分 `base64://`、不发送路径文本、不触发 fallback/重试，并保持 group/dm 路由和 Action 至多一次
- [x] 3.3 更新安全边界回归，验证日志、异常和 `SendResult` 不包含路径、文件内容、Base64、完整 URI 或底层异常；确认入站 Hermes 资源下载、缓存和既有图片 hash `8 MiB` 边界未被修改

## 4. 文档、质量门禁与交付证据

- [x] 4.1 更新 `README.md`、`ARCHITECTURE.md` 和配置示例，说明 `MILKY_MAX_LOCAL_MEDIA_BYTES` 的字节单位、默认 `32 MiB`、合法范围、Base64 放大、内网不消除服务端限制，以及 `http(s)://`/显式 `base64://` 非本地限制边界
- [x] 4.2 运行聚焦测试 `uv run pytest -q tests/test_config.py tests/test_multimedia_outbound.py tests/test_outbound.py tests/test_adapter_lifecycle.py`，验证配置解析、各媒体入口、文件上传和生命周期边界
- [x] 4.3 运行完整质量门禁 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`，按配置解析、媒体 materialization、Hermes API、协议/服务端或测试基础设施分类失败
- [x] 4.4 运行 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`，记录 change artifacts 与主规范边界一致；未经明确授权不执行真实 Milky 发送或上传 smoke
