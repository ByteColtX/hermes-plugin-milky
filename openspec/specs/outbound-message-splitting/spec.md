# outbound-message-splitting Specification

## Purpose

为 Milky Agent 提供可选且可预测的文本分段投递能力，让一次回复能够在不暴露控制标记的前提下按聊天节奏发送最多三条文本消息。

## Requirements

### Requirement: `[SPLIT]` 只识别严格的独立行标记

Milky 出站文本 MUST 识别内容恰好为 [SPLIT] 的整行，以及普通正文行中未转义、大小写严格匹配的 [SPLIT] 标记。整行标记仍不得包含前导或尾随空格；行中标记所在行除标记外 MUST 至少包含一个非空白字符，只有空白包围的标记行仍作为普通文本保留。有效标记 MUST 从用户可见文本中删除，其他大小写变体 MUST 原样保留。行中标记两侧的非标记空白、普通换行和非空段内容 MUST 保持原样，不得自动 trim。

分段扫描 MUST 尊重语法完整的 CQ-compatible 候选边界（包括未知 type），并将该候选按既有规则交给结构化转换或原始文本 fallback；合法 CQ 参数不会原样包含方括号形式的 [SPLIT]。缺少闭合括号、参数包含原始方括号或基础语法无效的 malformed CQ-like 内容不属于受保护候选，其中的 [SPLIT] MUST 按普通文本控制语法处理。未转义的 [SPLIT] 作为控制语法后，发送方 MUST 支持使用 [[SPLIT]] 输出字面量 [SPLIT]，且该转义形式不得触发分段。

#### Scenario: 识别独立成行的有效标记

- **WHEN** 回复包含 `第一段`、单独一行的 `[SPLIT]` 和 `第二段`
- **THEN** 系统 SHALL 生成顺序为 `第一段`、`第二段` 的文本发送单元
- **AND** 用户可见文本 SHALL 不包含 `[SPLIT]`

#### Scenario: 标记大小写不匹配

- **WHEN** 回复包含单独一行的 `[split]`、`[Split]` 或其他大小写变体
- **THEN** 系统 SHALL 不把这些行当作控制标记
- **AND** 原始行内容 SHALL 保留为普通文本

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

#### Scenario: 标记不是完整独立行

- **WHEN** 回复包含 第一段[SPLIT]第二段
- **THEN** 系统 SHALL 生成顺序为 第一段、第二段的文本发送单元
- **AND** 不得要求标记独占一整行

#### Scenario: 行中标记保留两侧空白

- **WHEN** 回复包含 第一段 [SPLIT] 第二段
- **THEN** 系统 SHALL 删除标记本身并生成 第一段空格 和 空格第二段两个文本单元
- **AND** 系统 SHALL 不因分段而 trim 两侧空白

#### Scenario: 空文本段

- **WHEN** 回复开头、结尾或相邻位置出现有效 `[SPLIT]` 行
- **THEN** 空文本段 SHALL 不产生空白 QQ 消息
- **AND** 有内容的文本段 SHALL 保持原有相对顺序

#### Scenario: 标记相邻的空白行属于分隔边界

- **WHEN** 回复在有效 `[SPLIT]` 行前或后包含一个或多个只含空白字符的行
- **THEN** 这些相邻的空白行 SHALL 随标记的分隔边界一并移除，不得出现在相邻文本发送单元的开头或结尾
- **AND** 非空文本行中的前导或尾随空白以及段内换行 SHALL 保持原样
- **AND** 行中标记不得额外移除其所在普通文本行之外的空白行

### Requirement: 有效分段回复最多产生三条文本消息

当回复包含至少一个有效 `[SPLIT]` 行时，系统 MUST 将有效文本段整理为最多三个文本发送单元。超过三个逻辑文本段时 MUST 将尾部段按原顺序合并到第三个发送单元，且不得丢失、重排或改写可见文本。每个发送单元仍 MUST 遵守既有 Milky 文本长度边界。

#### Scenario: 两段文本按顺序投递

- **WHEN** 回复包含两段非空文本和一个有效 `[SPLIT]` 行
- **THEN** 系统 SHALL 先投递第一段，再投递第二段
- **AND** 两条文本消息 SHALL 分别保留对应段落内容

#### Scenario: 多于三段时合并尾部

- **WHEN** 回复经空段过滤后包含四个或更多非空逻辑文本段
- **THEN** 系统 SHALL 只生成三个文本发送单元
- **AND** 第三个发送单元 SHALL 按原顺序包含第三段及其后全部文本
- **AND** 任何逻辑段的可见内容 SHALL 不被丢弃

#### Scenario: 分段后的长度边界仍然有效

- **WHEN** 一个或多个文本发送单元超过既有 Milky 文本长度上限
- **THEN** 系统 SHALL 按既有安全边界计算实际发送单元
- **AND** 如果实际文本消息数因此超过三条，系统 SHALL 在任何网络 Action 前整体返回本地边界错误
- **AND** 系统 SHALL 不截断文本或先发送部分单元

#### Scenario: 只有控制标记没有可见文本

- **WHEN** 回复只包含有效 `[SPLIT]` 行和空白
- **THEN** 系统 SHALL 不发送空白文本消息
- **AND** 系统 SHALL 返回与空出站内容一致的本地结果

### Requirement: 分段文本按序且以原子批次投递

同一回复生成的文本发送单元 MUST 按回复中的顺序串行提交到同一 `group:` 或 `dm:` 目标。系统 MUST 在首个文本 Action 前完成目标、格式和全部分段边界校验；任一前置校验失败时不得提交任何文本 Action。发送过程中发生失败时，系统 MUST 保留既有部分成功结果和首个安全失败分类，不得为失败单元自动重试或发送不同内容的 fallback。

#### Scenario: 前置校验失败时不部分发送

- **WHEN** 分段文本无法满足长度、目标或格式边界
- **THEN** 系统 SHALL 在网络访问前返回可分类失败
- **AND** Milky 文本 Action 调用次数 SHALL 为零

#### Scenario: 中间文本发送失败

- **WHEN** 第二个文本发送单元的 Action 返回拒绝或传输未知
- **THEN** 系统 SHALL 保留第一个成功结果和第二个单元的安全失败分类
- **AND** 系统 SHALL 不发送后续文本单元、不改变正文重发或盲目重试已进入网络边界的 Action
