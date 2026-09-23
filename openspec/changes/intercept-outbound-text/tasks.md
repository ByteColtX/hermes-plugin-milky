# Tasks

## 1. 精确文本拦截

- [ ] 1.1 新增可复用的完整字符串拦截器，并登记 Hermes silence-marker 兜底文案；在登记值旁添加中文注释，标明 `hermes-agent/gateway/run_turn.py::_UNEXPECTED_SILENCE_REPLY` 来源及上游改文案时更新的提醒；用单元测试验证完整相等匹配和可登记多条规则。
- [ ] 1.2 在普通文本调用现有 outbound sender 前应用拦截，保持连接检查、媒体和文件路径不变；命中时返回终止处理结果且不生成远端 message ID；用 fake sender/client 测试验证不触发 sender 或 Milky Action，并保留 Gateway ledger 可能记录为 delivered 的已知语义。

## 2. 回归与验证

- [ ] 2.1 补充不拦截回归测试，覆盖兜底文案嵌入较长文本、前后缀、空白/标点/大小写差异，以及媒体和文件入口不受影响；验证未命中文本继续走既有发送路径。
- [ ] 2.2 运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`openspec validate intercept-outbound-text --strict` 和 `git diff --check`；记录 fake host 测试仅证明插件未请求 Milky Action，不声称完成真实 Hermes/Milky 端到端投递验证。
