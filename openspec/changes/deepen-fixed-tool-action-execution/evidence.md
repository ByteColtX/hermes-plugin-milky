# Evidence ledger

## Fixed Action baseline

- 注册入口位于 `outbound/tools.py::register_tools`，manifest 的 26 个固定 Action 与注册顺序保持一致；`sticker_search` 和 `sticker_send` 仍是独立语义工具。
- 请求与结果基线由 `tests/test_qq_tools.py`、`tests/test_tool_result_passthrough.py`、`tests/test_milky_client.py` 和 `tests/test_outbound.py` 覆盖。覆盖省略、显式 `null`、`false`、合法空字符串、错误类型、范围、未知字段、未绑定/关闭 client、取消、HTTP/协议拒绝、非 JSON、原始文本/数组/null 结果以及无响应分类。
- `milky/fixed_actions.py` 集中固定 Action 目录和网络前参数集合校验；`outbound/fixed_actions.py` 提供固定执行窄 interface，复用已绑定 client，不重试、不建立连接，取消继续传播，未确认结果只降级为安全分类。
- `MilkyClient.call_tool` 继续负责 raw transport 响应交付；非 Tool Action 继续通过 typed `call`/DTO 路径。sender 保留既有字段投影，因此 `no_cache=false` 仍省略请求字段。

## Known differences retained

- 三个群查询入口显式 `no_cache=false` 时仍省略该字段；这是当前运行行为，未按 schema 自动补字段。
- `send_profile_like.count` 的运行校验仍接受既有的非负安全整数及显式 `null` 投影；未按 manifest 声明的 1–50 范围收紧。

## Verification

- `uv run pytest -q tests/test_qq_tools.py tests/test_tool_result_passthrough.py`: 133 passed。
- 固定 Action、client 和生命周期聚焦测试：289 passed, 2 skipped。
- `uv run pytest -q`: 1406 passed, 3 skipped。
- `uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check` 与 `openspec validate --changes --strict` 在交付前运行并记录最终结果。
- 真实 Hermes 宿主和副作用 smoke 未在本环境确认；保持 `unsupported`/`blocked`，不宣称集成通过。
