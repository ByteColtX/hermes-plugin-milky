# Evidence ledger

记录日期：2026-09-06（Asia/Shanghai）

## 已执行

- uv run pytest -q tests/test_outbound_splitting.py：通过，41 passed。
- uv run pytest -q tests/test_outbound.py tests/test_outbound_splitting.py tests/test_multimedia_outbound.py tests/test_model_control_integration.py tests/test_plugin_entry.py：通过，145 passed，1 skipped。
- uv run ruff check .：通过。
- uv run ruff format --check .：通过，313 files already formatted。
- git diff --check：通过。
- uv run pytest -q：通过，811 passed，2 skipped。
- uv build：通过，生成 source distribution 和 wheel。
- npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict：通过，3 passed，0 failed。

## Skip 与边界

- tests/test_adapter_lifecycle.py:485：跳过，当前测试环境没有 Hermes host。
- tests/test_multimedia_outbound.py:625：跳过，当前测试环境没有 Hermes host。
- 未执行真实 Milky 连接、消息发送或文件上传；未修改 Hermes core。
- 测试使用合成文本、合成 CQ ID 和脱敏 URI，不包含 token、Authorization、真实 QQ、媒体 URL 或本地路径。

## CQ 保护边界修订

- `uv run pytest -q tests/test_outbound_splitting.py tests/test_cq_formatter.py tests/test_plugin_entry.py`：通过，105 passed。
- `uv run pytest -q`：通过，813 passed，2 skipped。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过，314 files already formatted。
- `git diff --check`：通过。
- `uv build`：通过，生成 source distribution 和 wheel。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`：通过，3 passed，0 failed。
- 保护边界现为仅保护基础语法完整的 CQ-compatible 候选（包括未知 type）；带原始方括号、基础语法无效或未闭合的 malformed CQ-like 内容按普通文本规则处理。
- 本次仍未执行真实 Milky 连接、消息发送或文件上传；未修改 Hermes core。
