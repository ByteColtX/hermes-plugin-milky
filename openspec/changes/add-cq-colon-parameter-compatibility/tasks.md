# Tasks

## 1. CQ 参数解析与 fallback

- [x] 1.1 在出站 CQ 参数边界仅对 `reply`、`at`、`face` 按每个字段中最先出现的 ASCII `=` 或 `:` 选择分隔符，保留混用、重复键、空值、方括号、实体解码和现有字段/ID 校验语义；用 `uv run pytest -q tests/test_cq_formatter.py` 验证既有 canonical 输入保持原结果。
- [x] 1.2 让完整 CQ 候选判断复用兼容解析结果，覆盖 `face`、`at`、`reply` 的 native 冒号写法、字段值中后续冒号或等号、混合分隔符，以及 `text`、`image`、`record`、`video` 和未知类型的冒号写法原文 fallback；用新增 formatter 单元测试验证每个输入只产生预期 segment。
- [x] 1.3 增加非法兼容写法测试，覆盖缺少值、非法键、重复键、前导零/越界/非数字 ID、不支持字段、未闭合控制码，以及三类冒号 CQ 后紧邻 `[SPLIT]` 的分段边界；用 `uv run pytest -q tests/test_cq_formatter.py tests/test_outbound_splitting.py` 验证不丢正文、不触发额外发送。

## 2. Agent-facing 文案与测试资料

- [x] 2.1 从 `PLATFORM_GUIDANCE` 移除 “Use `id=`, never `id:`.”，保留 `[CQ:reply,id=<msg_seq>]`、`[CQ:at,qq=<uid>]` 和真实 ID 来源指引；更新 prompt snapshot/entry 测试，并用 `uv run pytest -q tests/test_plugin_entry.py tests/test_hermes_prompt_integration.py` 验证渲染结果。
- [x] 2.2 检查并保持 `skills/milky-qq-cq-reference/SKILL.md`、CQ 脱敏 fixture 和相关 README 示例只把 `=` 作为规范写法，不新增 `id:`、`qq:` 或 `large:` 教学；用 `rg -n '\[CQ:[^]]*,(id|qq|large):' skills/milky-qq-cq-reference tests/fixtures/cq_message_controls.json README.md` 复核未引入规范文案漂移，并运行对应文档/fixture 测试。

## 3. 集成与质量验证

- [x] 3.1 运行 `uv run pytest -q tests/test_cq_formatter.py tests/test_outbound.py tests/test_outbound_splitting.py tests/test_plugin_entry.py tests/test_hermes_prompt_integration.py`，确认 fake sender/host 证据覆盖 native 转换、原文 fallback、prompt 和分段边界；记录任何 skip，不把 fake host 结果表述为真实 Milky 集成。
- [x] 3.2 运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check` 和 `openspec validate --changes --strict`；逐项记录真实命令结果，确认没有网络、Action catalog 或 ToolSpec 范围扩张，并记录 parser 不验证 `id`/`qq` 是否来自上下文这一边界及其他 CQ 类型仍为 `=`-only。
