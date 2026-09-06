## 1. 契约夹具与聚焦测试

- [x] 1.1 扩展脱敏 split fixture，覆盖独立行、普通行中、连续/空段、大小写变体、只有空白包围的标记行、行中两侧空白、[[SPLIT]]、完整 unknown type CQ 和 malformed CQ-like 内容；验证 fixture 不含凭证、真实 QQ、媒体 URL 或本地路径。
- [x] 1.2 增加 parser 契约测试，验证未转义行中 [SPLIT] 被删除并形成有序段、[[SPLIT]] 还原为字面量、完整 CQ 候选边界不吞掉外部标记、malformed CQ 中标记按普通文本处理、既有独立行空白边界不回归；验证 uv run pytest -q tests/test_outbound_splitting.py。
- [x] 1.3 增加 sender 契约测试，验证行中分段经过 CQ formatter、连续分段过滤、三条合并、长度预检、无有效标记的长文本不受三条限制、网络前零 Action 和中间失败部分结果；验证聚焦 outbound 测试通过。

## 2. 出站文本实现

- [x] 2.1 在现有 split 解析边界实现受保护扫描，区分有效行中标记、独立行边界、[[SPLIT]] 字面量和语法完整 CQ 候选；malformed/未闭合 CQ 回到普通文本规则，验证 parser 测试及 CQ fallback 测试通过。
- [x] 2.2 将解析结果的有效控制标记状态接入普通文本分块，确保只有有效分段才启用三条上限，字面量归一化仍沿用普通长文本分块；验证 tests/test_outbound.py、tests/test_outbound_splitting.py 和媒体出站回归通过。
- [x] 2.3 保持目标校验、formatter、materialization、按序 Action、部分失败和不重试边界不变；验证 group/dm、CQ、媒体入口和 SendResult 相关聚焦测试通过。

## 3. Agent 指引与稳定文档

- [x] 3.1 更新根入口 PLATFORM_GUIDANCE 和 system prompt section，说明行中 [SPLIT]、[[SPLIT]] 字面量、完整 CQ 按整体解析、malformed CQ 按普通文本处理、最多三条和附件顺序；验证 tests/test_plugin_entry.py 及提示文案断言通过。
- [x] 3.2 更新 ARCHITECTURE.md、README.md 和对应 OpenSpec 事实来源，明确 BREAKING 字面量变化、普通空白处理、非目标和回滚边界；验证文档不包含敏感数据且与 delta specs 一致。

## 4. 质量门禁

- [x] 4.1 运行 uv run pytest -q tests/test_outbound.py tests/test_outbound_splitting.py tests/test_multimedia_outbound.py tests/test_model_control_integration.py tests/test_plugin_entry.py、uv run ruff check .、uv run ruff format --check . 和 git diff --check，记录结果与任何受控 skip。
- [x] 4.2 运行 uv run pytest -q、uv build 和 npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict，确认没有真实 Milky 写入、没有 Hermes core 修改，并把验证结果记录到 change evidence。

## 5. 收窄 CQ 保护边界

- [x] 5.1 将 CQ fixture 和 parser/sender 测试改为覆盖语法完整的 unknown type CQ、合法 CQ 后的 `[SPLIT]`、带原始方括号的 malformed CQ 和未闭合 `[CQ:`；验证 malformed 内容中的标记会按普通文本分段。
- [x] 5.2 复用现有 CQ 基础语法校验，仅保护完整且语法有效的 CQ 候选；移除 malformed/未闭合 CQ 对后续 `[SPLIT]` 的宽泛保护，不改变 formatter fallback 和合法 CQ 发送顺序。
- [x] 5.3 更新根入口提示、README、ARCHITECTURE 和对应 delta spec，明确完整 CQ 保护与 malformed CQ 普通文本处理边界。
- [x] 5.4 运行 split/formatter/entry 聚焦测试、Ruff、format、diff 检查和 OpenSpec strict validate，并更新 evidence；不执行真实 Milky 写入。
