# Evidence ledger

记录日期：2026-09-05（Asia/Shanghai）

## 已执行

- `uv run pytest -q tests/test_config.py tests/test_multimedia_outbound.py tests/test_outbound.py tests/test_adapter_lifecycle.py`：通过，177 passed，2 skipped。
- 新增配置、默认/自定义边界、CQ sticker、图片/语音/视频、独立文件上传、adapter/sender/FileUploader/standalone 传播和中间 `base64://` 单次读取回归：通过。
- `uv run pytest -q`：通过，765 passed，2 skipped。
- `uv run pytest -q -rs`：通过，765 passed，2 skipped；跳过项为当前环境未提供 Hermes host 的 adapter media dispatch 与 multimedia Hermes integration 测试。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过，283 files already formatted。
- `uv build`：通过，生成 source distribution 和 wheel。
- `git diff --check`：通过。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`：通过，2 passed，0 failed（本 change 及同时存在的 `map-face-id-to-chinese-name`）。

## Skip 与边界

- 未执行真实 Milky 连接、消息发送或文件上传；未获得相应写入授权。
- Hermes host 相关测试仅在 fake/可选 host 条件下覆盖；未将 fake 集成结果当作真实 Hermes host 证明。
- 入站 Hermes 资源下载、缓存、SSRF/权限规则和图片 hash 的既有 8 MiB 边界未修改；本 change 只改变出站本地 materialization 的启动配置上限。
- 测试使用合成凭证、目标、URI 和本地临时文件；不把凭证、Authorization、完整 URI、路径、文件内容或 Base64 写入日志、异常或发送结果。
