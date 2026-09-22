# 验证证据

记录日期：2026-09-23（Asia/Shanghai）

## 已验证行为

- parser、inbound extractor、normalizer 和 canonical 的递归复制只负责协议值复制与容器冻结；合成 fixture 覆盖顶层、嵌套和大小写变体字段，字段保留且未知 segment 仍不进入正文或策略文本。
- 通用 Action 与 Tool 路径对同一响应字段保持一致；非 Tool 的 `rejected`、`http_error`、`malformed` 和 `transport_unknown` 分类未改变。
- fake transport、fake Hermes host 和合成响应验证日志只记录固定分类、状态码、耗时、计数和必要关联 ID；协议 raw、响应正文、完整 URL、自由文本和合成敏感字段未进入插件日志或 smoke 摘要。
- 会话介绍继续使用显式实体白名单；raw 和未知扩展未进入正文、关键词、会话介绍、隐式工具调用或授权判断。

## 检查记录

- 聚焦协议/Tool/日志回归：`uv run pytest tests/test_milky_parser.py tests/test_normalizer.py tests/test_canonical.py tests/test_qq_context.py tests/test_will_keyword_boundaries.py tests/test_qq_tools.py -q` → 204 passed。
- 跨 Action、Tool、SSE、入站、资源、出站、异常和 smoke 回归 → 281 passed、1 skipped。
- 完整测试：`uv run pytest -q -rs` → 973 passed、3 skipped；skip 分别为 Hermes host 不可用、真实 Hermes 集成未显式启用，以及媒体测试缺少 Hermes host。
- `uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check` 均通过；`openspec validate --changes --strict` → 7 passed、0 failed。
- 源码检索确认四处旧敏感键过滤表和 `safe` 复制辅助函数已移除；日志调用未新增 payload/raw 遍历或复制路径。

## 验证范围与未确认边界

- 所有行为证据来自本地合成 fixture、fake transport 和 fake Hermes host；未写入真实凭证、live 响应、真实媒体或生产路径。
- 未连接真实 Hermes/Milky 宿主，未执行真实发送、上传或其他可能产生副作用的 Action；真实 logger 路由、Tool 结果后处理、模型上下文和 session 持久化仍待宿主集成验证。
