# Evidence

## 实现与测试依据

- `inbound/normalizer.py` 保留协议提供的视频 `resource_id` 和 `duration`，缺失字段使用 `NOT SUPPORTED`；不把 `temp_url` 放入正文。
- `milky/resources.py` 在视频资源解析分支直接返回 `unsupported`，不会查询临时链接或调用媒体 materializer。
- `outbound/tools.py` 注册固定 `get_resource_temp_url` ToolSpec，并在 Agent 显式调用时走 Tool 原始响应路径。
- `tests/test_inbound_context_rendering.py` 覆盖完整字段、缺失字段及正文不泄漏内嵌 URL；`tests/test_resources.py` 覆盖 trigger 中的视频引用不触发资源查询或 materializer；`tests/test_qq_tools.py` 覆盖固定工具注册与参数校验。

## 本次验证

- `uv run pytest -q tests/test_inbound_context_rendering.py tests/test_resources.py tests/test_qq_tools.py`：161 passed。该组使用 fake host、fixture 和合成 transport；不代表真实 Hermes 或 Milky 集成通过。
- `openspec validate --changes --strict`：6 项通过。
- `openspec validate --specs --strict`：30 项通过。
- `git diff --check`：通过。

本次没有执行真实 Hermes、真实 Milky 或 QQ 联调；视频下载与内容分析仍不属于已确认能力。
