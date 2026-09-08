# Evidence ledger

记录日期：2026-09-08（Asia/Shanghai）

## 已执行

- `uv run pytest -q tests/test_inbound_context_rendering.py tests/test_hermes_pipeline.py tests/test_wait_buffer.py`：通过，50 passed。
- `uv run pytest -q`：通过，814 passed，2 skipped。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过，352 files already formatted。
- `uv build`：通过，生成 source distribution 和 wheel。
- `git diff --check`：通过。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`：通过，4 passed、0 failed。
- 聚焦测试覆盖 dm body-only 历史、dm reply header 省略、system event ingress 顺序、换行编码、空历史、group 输出稳定、batch/helper/resolved pipeline 三个 renderer 出口，以及当前消息的 Hermes reply metadata。

## 未覆盖与边界

- 未执行真实 Milky/Hermes host 连接；fake transport、fixture 和 fake Hermes 结果不能替代真实服务及宿主能力验证。
- 完整测试中的 2 个 skip 是当前环境缺少 Hermes host 的既有真实集成测试。
- 未执行真实消息发送、文件上传或其他远端写入；本 change 不新增远端 Action。
- 测试使用合成会话标识和正文；未记录凭证、Authorization、媒体 URL、真实业务身份、完整响应或敏感正文。
