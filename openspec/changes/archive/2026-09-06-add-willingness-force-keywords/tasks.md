## 1. 契约与回归用例

- [x] 1.1 在配置测试中覆盖 `interestKeywords`、`forceKeywords` 的默认空数组、合法非空字符串数组、非法数组和旧 `willingness.keywords` 拒绝，并验证 `uv run pytest -q tests/test_config.py` 通过
- [x] 1.2 在 willingness 测试中覆盖兴趣关键词仍使用 `keywordMultiplier`、强制关键词命中直接返回 `trigger` 且不调用随机源、强制关键词不额外改变 score，以及两类关键词同时命中的组合语义
- [x] 1.3 在 pipeline 或相关边界测试中验证强制关键词只对通过 Gate 的普通 friend/group `message_receive` 生效，temp、命令、系统事件、Gate deny 和 wait 不触发普通 Agent 流程或 reply cost

## 2. 配置与 willingness 实现

- [x] 2.1 将 Will policy 默认值、字段白名单和数组校验从 `willingness.keywords` 迁移到 `interestKeywords` 与 `forceKeywords`，并验证旧字段不会被兼容或静默转换
- [x] 2.2 更新 willingness 配置快照和字段映射，使 `interestKeywords` 仅控制 `keywordMultiplier`，并新增 `forceKeywords` 的直接子串匹配；验证两类关键词均只消费规范化正文且不执行网络 I/O
- [x] 2.3 将 `forceKeywords` 接入现有 force 决策，使命中时跳过概率抽样并复用既有 trigger reply cost；验证一次 trigger 只扣一次且后续交接失败不回滚

## 3. 文档与迁移说明

- [x] 3.1 更新 `README.md` 的 Will policy 表格、示例、完整默认配置和迁移说明，区分 `routing.keywords`、`willingness.interestKeywords` 与 `willingness.forceKeywords`
- [x] 3.2 更新 `ARCHITECTURE.md` 的 Will 配置和决策边界，明确强制关键词不绕过 Gate、不参与 score 增益且不改变 reply cost 语义

## 4. 验证与交付

- [x] 4.1 运行 `uv run pytest -q tests/test_config.py tests/test_will_willingness.py tests/test_hermes_pipeline.py tests/test_wait_buffer.py`，确认聚焦回归通过
- [x] 4.2 运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`，确认完整质量门禁通过
- [x] 4.3 运行 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`，确认 change artifacts 与实现契约一致；将未覆盖的实机边界记录到 evidence
