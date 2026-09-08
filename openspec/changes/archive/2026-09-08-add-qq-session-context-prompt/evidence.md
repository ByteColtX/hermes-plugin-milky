# Evidence ledger

记录日期：2026-09-08（Asia/Shanghai）

## 已执行

- `uv run pytest -q tests/test_qq_context.py tests/test_canonical.py tests/test_hermes_pipeline.py tests/test_plugin_entry.py`：通过；覆盖 friend/group 白名单、身份不一致、snapshot 并发/淘汰/隔离、恶意 metadata、callback 无 I/O、pipeline 时序和旧宿主降级。
- `uv run pytest -q tests/test_qq_context.py tests/test_hermes_pipeline.py tests/test_plugin_entry.py tests/test_hermes_prompt_integration.py`：通过；46 passed，1 skipped。默认 skip 的真实集成需要显式环境变量。
- `RUN_HERMES_INTEGRATION=1` 的真实 Hermes 检查曾因外部 checkout 使用 Python 3.11 而无法解析 Python 3.13 `class` 语法；随后在临时 Python 3.13.5 环境中运行 `scripts/hermes_prompt_integration.py`，通过真实 Hermes `PluginManager`、`AIAgent`、prompt restore、冻结和显式 rebuild 验证。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过。
- `uv run pytest -q`：通过，824 passed，3 skipped。
- `uv build`：通过，生成 source distribution 和 wheel。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`：通过，3 changes validated，0 failed。

## 边界与未覆盖

- 未连接真实 Milky 服务；未发送消息、上传文件或执行任何远端写入。
- 真实 Hermes 检查使用外部源码 checkout 和临时 `HERMES_HOME`/SQLite，只验证宿主 section/prompt 生命周期；不会证明真实 Milky 网络或完整 Gateway platform registry 集成。
- Hermes 临时环境报告 SQLite WAL-reset 风险提示，自动使用 DELETE journal；该提示不影响 prompt section 检查。
- 测试、fixture 和 evidence 未写入 token、Authorization、真实 QQ/群身份、媒体 URL、文件路径、完整响应或敏感正文。
