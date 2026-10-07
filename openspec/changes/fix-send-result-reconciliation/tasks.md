# Tasks

## 1. 发送响应证据归一化

- [x] 1.1 盘点并实现发送类 Action 的四态结果边界，保留严格 HTTP、envelope 和字段校验；用 fake transport 覆盖标准成功、明确拒绝、响应结构异常和传输未知，并验证其他非发送 Action 分类不变。
- [x] 1.2 根据已确认的 Milky 协议证据补充异常状态下的发送成功判定；在证据未确认时保持 `unknown` 或既有拒绝，不凭 HTTP 200、单一 retcode 或猜测字段报告成功；用脱敏 fixture 和协议解析测试验证。
- [x] 1.3 更新 Action 日志分类和安全断言，使异常协议状态但确认发送、明确拒绝和未知结果在 Action 边界可区分；验证日志不包含响应正文、正文、凭证、URL 或路径。

## 2. 多段结果聚合

- [x] 2.1 调整普通多段发送的结果聚合，使所有段确认成功后才返回成功，最终段只提供最终消息 ID，前段序号继续作为 continuation；用 fake sender 覆盖两段和三段全成功场景。
- [x] 2.2 覆盖部分成功、前段明确失败、最终段成功和结果未知场景；验证首个安全失败分类、失败位置及已确认序号均保留，且不会盲目重复提交 Action。

## 3. 集成验证与边界回归

- [x] 3.1 运行发送、Milky Action 和 observability 聚焦测试，确认 fake host 只证明插件行为，并单独标注未连接真实 Hermes/Milky 的边界。
- [x] 3.2 运行 `uv run ruff check .`、`uv run ruff format --check .`、`uv run pytest -q`、`uv build`、`git diff --check` 和 `openspec validate --changes --strict`，确认实现没有修改 Hermes core 或其他未授权范围。
