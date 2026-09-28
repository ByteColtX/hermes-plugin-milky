# Tasks

## 1. 入站视频上下文与惰性资源处理

- [ ] 1.1 更新视频 placeholder，按顺序显示 `resource_id` 和秒级 `duration`，缺失值使用 `NOT SUPPORTED` 且不展示 `temp_url`；为完整和缺字段场景增加合成 fixture/断言，并运行 `uv run pytest -q tests/test_inbound_context_rendering.py`。
- [ ] 1.2 调整 trigger 资源解析，使视频引用不自动查询临时 URL 或调用 materializer；增加断言验证含 `resource_id`、内嵌 `temp_url` 和缺失引用的路径均不触发视频资源网络请求，同时图片/语音行为不回归，并运行 `uv run pytest -q tests/test_resources.py tests/test_inbound_image_dedup.py`。
- [ ] 1.3 更新 README 与 ARCHITECTURE 的入站媒体说明，明确视频上下文展示字段、显式取链接工具及不含视频分析能力；核对文档不声称视频已可解析或理解。

## 2. 显式资源临时链接 Action 工具

- [ ] 2.1 将 `get_resource_temp_url` 加入固定 Action ToolSpec 目录和 manifest，并实现严格的单字段参数校验与显式调用路由；扩展注册断言确认工具名、工具集、参数 schema、目录数量一致，非法参数在网络前失败，并运行 `uv run pytest -q tests/test_qq_tools.py`。
- [ ] 2.2 为 Agent Tool 调用建立原始响应体交付路径，同时保留内部资源解析现有的 envelope 契约；增加合成传输断言覆盖精确 POST body、任意已取得响应体、未绑定 client、传输未知和不记录 URL/原始参数，并运行 `uv run pytest -q tests/test_qq_tools.py tests/test_milky_client.py tests/test_observability.py`。
- [ ] 2.3 更新 README 与 ARCHITECTURE 的固定 Action Tool 清单和行为说明；确认文档说明工具只返回临时链接、不自动下载或分析视频。

## 3. 集成验证

- [ ] 3.1 运行相关 OpenSpec 严格校验、`uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`；报告 fake host 覆盖与任何未执行的真实 Hermes/Milky 验证边界。
