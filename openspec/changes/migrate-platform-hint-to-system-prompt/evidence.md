# Evidence ledger

记录日期：2026-09-03（Asia/Shanghai）

## 已执行

- `uv run pytest -q tests/test_plugin_entry.py tests/test_adapter_lifecycle.py`：通过，34 passed，1 skipped。
- `uv run pytest -q -rs`：通过，640 passed，2 skipped。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过。
- `uv build`：通过，生成 source distribution 和 wheel。
- `git diff --check`：通过。
- `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`：通过，1 change validated。
- `uv run scripts/milky_smoke.py --help`：通过；仅检查本地 CLI 帮助，未连接 Milky，未发送消息，未上传文件。

## Skip 与边界

- `tests/test_adapter_lifecycle.py::test_actual_hermes_delivery_hook_returns_unknown_result_once`：跳过，当前测试环境未提供 Hermes host。
- `tests/test_multimedia_outbound.py::test_actual_hermes_media_hook_uses_host_helper`：跳过，当前测试环境未提供 Hermes host。
- section 行为使用可记录的 fake host 验证；未把 fake host 结果宣称为真实 Hermes 集成证明。
- 未执行真实 Milky 连接、消息发送、文件上传或其他写入操作。
- 本 change 的 diff 仅涉及插件实现、插件文档、测试和 change artifact；未修改 Hermes core，未新增凭证、响应正文、媒体 URL、远端路径或真实业务身份。工作区原有未跟踪的 `prompt-engineering.md` 未修改。
