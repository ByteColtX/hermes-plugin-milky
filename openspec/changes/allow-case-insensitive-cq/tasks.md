## 1. 契约与回归夹具

- [ ] 1.1 在 `tests/test_cq_formatter.py` 增加 `[CQ:]`、`[cq:]`、`[Cq:]` 和 `[cQ:]` 前缀的 at、reply 及已确认媒体转换断言，验证生成的 Milky segment 与大写形式一致
- [ ] 1.2 增加未知 CQ、非法字段、未闭合 CQ 和混合普通文本的大小写变体测试，验证 fallback 保留完整原始字符串、大小写和参数顺序
- [ ] 1.3 在 `tests/test_outbound_splitting.py` 及其脱敏 fixture 增加大小写变体 CQ 后接 `[SPLIT]`、未知 CQ 后接 `[SPLIT]` 和 malformed CQ 内含 `[SPLIT]` 的断言，验证完整候选受保护且损坏候选仍可分段

## 2. 出站解析实现

- [ ] 2.1 更新 CQ 前缀识别，使 `CQ` 的大小写变体进入现有解析和转换路径，同时保持 type、字段、ID 校验以及 raw fallback 语义；运行 formatter 聚焦测试验证旧的大写路径不回归
- [ ] 2.2 让 `[SPLIT]` 的完整 CQ 候选扫描复用相同的大小写不敏感识别边界，验证有效未知 CQ 不吞掉后续标记、malformed CQ 不获得保护
- [ ] 2.3 验证普通文本、结构化 text segment、组合 at/reply、长文本分块和 native media 入口都通过同一 CQ 解析行为，运行相关 outbound 测试确认无额外 Action 或发送次数

## 3. Agent-facing 文档与提示

- [ ] 3.1 更新 `__init__.py` 的平台提示，明确 `CQ` 前缀大小写不敏感但不扩大已确认 CQ 类型、字段和真实 ID 约束，并用 prompt 测试验证文案稳定且不含敏感身份
- [ ] 3.2 更新 `skills/milky-qq-cq-reference/SKILL.md` 及对应 OpenSpec 变更产物，说明小写/混合大小写 `CQ` 前缀与大写形式等价，并保留未知 CQ 的 fallback 限制

## 4. 质量门禁

- [ ] 4.1 运行 `uv run pytest -q tests/test_cq_formatter.py tests/test_outbound_splitting.py tests/test_outbound.py`、`uv run ruff check .`、`uv run ruff format --check .` 和 `git diff --check`，修复全部失败项
- [ ] 4.2 运行完整 `uv run pytest -q` 与 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`，确认实现、delta spec、任务清单和既有行为一致
