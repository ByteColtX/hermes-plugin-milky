## MODIFIED Requirements

### Requirement: `[SPLIT]` 只识别严格的独立行标记

Milky 出站文本 MUST 识别内容恰好为 [SPLIT] 的整行，以及普通正文行中未转义、大小写严格匹配的 [SPLIT] 标记。整行标记仍不得包含前导或尾随空格；行中标记所在行除标记外 MUST 至少包含一个非空白字符，只有空白包围的标记行仍作为普通文本保留。有效标记 MUST 从用户可见文本中删除，其他大小写变体 MUST 原样保留。行中标记两侧的非标记空白、普通换行和非空段内容 MUST 保持原样，不得自动 trim。

分段扫描 MUST 尊重语法完整的 CQ-compatible 候选边界（包括未知 type），并将该候选按既有规则交给结构化转换或原始文本 fallback；合法 CQ 参数不会原样包含方括号形式的 [SPLIT]。缺少闭合括号、参数包含原始方括号或基础语法无效的 malformed CQ-like 内容不属于受保护候选，其中的 [SPLIT] MUST 按普通文本控制语法处理。未转义的 [SPLIT] 作为控制语法后，发送方 MUST 支持使用 [[SPLIT]] 输出字面量 [SPLIT]，且该转义形式不得触发分段。

#### Scenario: 识别独立成行的有效标记

- **WHEN** 回复包含 第一段、单独一行的 [SPLIT] 和 第二段
- **THEN** 系统 SHALL 生成顺序为 第一段、第二段的文本发送单元
- **AND** 用户可见文本 SHALL 不包含 [SPLIT]

#### Scenario: 标记不是完整独立行

- **WHEN** 回复包含 第一段[SPLIT]第二段
- **THEN** 系统 SHALL 生成顺序为 第一段、第二段的文本发送单元
- **AND** 不得要求标记独占一整行

#### Scenario: 行中标记保留两侧空白

- **WHEN** 回复包含 第一段 [SPLIT] 第二段
- **THEN** 系统 SHALL 删除标记本身并生成 第一段空格 和 空格第二段两个文本单元
- **AND** 系统 SHALL 不因分段而 trim 两侧空白

#### Scenario: 标记大小写不匹配

- **WHEN** 回复包含 [split]、[Split] 或其他大小写变体
- **THEN** 系统 SHALL 不把这些内容当作控制标记
- **AND** 原始内容 SHALL 保留为普通文本

#### Scenario: 只有空白包围的标记行不触发行中语义

- **WHEN** 回复包含一行仅由空格、[SPLIT] 和制表符组成的内容
- **THEN** 系统 SHALL 不把该行当作独立行或行中控制标记
- **AND** 原始行内容 SHALL 保留为普通文本

#### Scenario: 字面量转义

- **WHEN** 回复包含 [[SPLIT]]，且没有其他有效分段标记
- **THEN** 系统 SHALL 发送一个包含可见文本 [SPLIT] 的消息
- **AND** 系统 SHALL 不产生额外文本消息

#### Scenario: 完整 CQ 候选后的标记

- **WHEN** 回复包含一个语法完整的 CQ-compatible 或 unknown type CQ 候选，后面紧邻未转义 [SPLIT]
- **THEN** 系统 SHALL 在 CQ 候选闭合后识别该 [SPLIT] 并形成分段
- **AND** CQ 候选 SHALL 按既有结构化转换或原始文本 fallback 规则保留

#### Scenario: malformed CQ-like 内容中的标记

- **WHEN** 回复包含缺少闭合括号、参数含原始方括号或基础语法无效的 malformed CQ-like 内容，且其中出现 [SPLIT]
- **THEN** 系统 SHALL 按普通文本规则识别该 [SPLIT] 并形成分段
- **AND** SHALL 不因未闭合或无效的 `[CQ:` 前缀保护后续正文

#### Scenario: 空文本段

- **WHEN** 回复开头、结尾或相邻位置出现有效 [SPLIT] 标记
- **THEN** 空文本段 SHALL 不产生空白 QQ 消息
- **AND** 有内容的文本段 SHALL 保持原有相对顺序

#### Scenario: 标记相邻的空白行属于分隔边界

- **WHEN** 回复在有效独立行 [SPLIT] 前或后包含一个或多个只含空白字符的行
- **THEN** 这些相邻的空白行 SHALL 随独立行标记的分隔边界一并移除
- **AND** 行中标记不得额外移除其所在普通文本行之外的空白行
- **AND** 非空文本行中的前导或尾随空白以及段内换行 SHALL 保持原样
