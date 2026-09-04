# Evidence ledger

记录日期：2026-09-04（Asia/Shanghai）

## 已执行

- 新增 `tests/test_inbound_image_dedup.py`，覆盖图片 occurrence 槽位、历史优先代表、当前正文、可见 reply、隐藏历史嵌套 reply、内容重复、不同 MIME、空文件、8 MiB 边界、超限文件、目录、符号链接、读取失败、读取变化、hash 异常、exact path fallback 和同 path 单次读取。
- `uv run pytest -q tests/test_inbound_image_dedup.py tests/test_hermes_pipeline.py tests/test_resources.py tests/test_inbound_context_rendering.py`：通过，56 passed。
- `uv run pytest -q`：通过，687 passed，2 skipped。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过，254 files already formatted。
- `uv build`：通过，生成 source distribution 和 wheel。
- `git diff --check`：通过。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`：通过，4 passed，0 failed；输出包含其他未归档 change 的既有 archive 信息提示。

## Skip 与边界

- 2 个既有测试因当前环境未提供真实 Hermes host 而跳过；本 change 的 resolver、mapper 和 pipeline 使用脱敏临时文件、fake Hermes helper 与 fake host 验证，不能替代真实 Hermes 入站 media seam 证据。
- 未执行真实 Milky 连接、消息发送、文件上传或其他写入操作；未修改 Hermes core。
- fixture 和测试只使用合成文本、合成资源标识与运行时临时路径；hash 值、文件内容、远端媒体 URL、Authorization、凭证和完整异常正文不进入结果、日志或仓库。
- 严格 OpenSpec 校验只验证 change artifacts 的结构和契约格式；不替代真实 Hermes host 或 Milky 服务验证。
