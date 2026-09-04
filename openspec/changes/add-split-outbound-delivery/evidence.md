# Evidence ledger

记录日期：2026-09-04（Asia/Shanghai）

## 已执行

- `uv run pytest -q tests/test_outbound.py tests/test_multimedia_outbound.py tests/test_model_control_integration.py tests/test_plugin_entry.py tests/test_outbound_splitting.py`：通过，126 passed，1 skipped。
- 新增 `tests/test_outbound_splitting.py`：通过严格 `[SPLIT]` 行匹配、逻辑段合并、长度分块、三条总数预检、CQ 顺序、部分失败、文本先于附件和 `[SILENT]` core 交接测试。
- `uv run ruff check outbound/splitting.py outbound/sender.py tests/test_outbound_splitting.py tests/test_plugin_entry.py`：通过。
- `uv run ruff format --check outbound/splitting.py outbound/sender.py tests/test_outbound_splitting.py tests/test_plugin_entry.py`：通过。
- `uv run pytest -q`：通过，668 passed，2 skipped。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过，242 files already formatted。
- `uv build`：通过，生成 source distribution 和 wheel。
- `git diff --check`：通过。
- `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`：通过，2 passed，0 failed（本 change 及同时存在的 `migrate-platform-hint-to-system-prompt`）。

## Skip 与边界

- `tests/test_multimedia_outbound.py::test_actual_hermes_multiple_image_dispatch_uses_inherited_entries`：跳过，当前测试环境未提供 Hermes host。
- 有序媒体交接使用 fake Hermes/Milky；测试证明插件收到清理文本和独立附件列表时保持文本先行与附件提取顺序，不证明真实 Hermes core 的交接实现。
- `[SILENT]` 未加入插件解析；测试由 fake Hermes core 在进入 sender 前抑制该标记，验证插件 parser 不把它当作 `[SPLIT]` 控制码。
- 未执行真实 Milky 连接、消息发送、文件上传或其他写入操作；未修改 Hermes core。
- fixture 使用合成文本、合成 CQ ID 和 `base64://fixture-*` URI，不包含凭证、Authorization、真实业务身份、真实媒体 URL 或本地路径。
- OpenSpec 严格校验只验证 change artifacts 的结构和契约格式；不替代真实 Hermes host 或 Milky 服务验证。
