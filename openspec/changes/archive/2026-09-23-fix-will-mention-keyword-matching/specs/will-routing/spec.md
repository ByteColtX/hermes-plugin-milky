# Spec Delta

## MODIFIED Requirements

### Requirement: routing 关键词命中确定性触发

`routing.keywords` MUST 是字符串数组。当前消息的可匹配连续文本包含任意一个非空配置关键词时，Will
SHALL 将关键词规则视为 `trigger` 命中；关键词规则不使用随机抽样、willingness 分数或
force 配置。关键词匹配 SHALL 使用当前消息的可匹配连续文本的直接子串匹配，不按命中次数累加，也不将
未知 raw、媒体引用或敏感字段加入匹配文本。关键词数组为空时 SHALL 不产生关键词命中，
最终结果 SHALL 由其他命中规则（包括 allMessage）决定。

关键词匹配 MUST 只使用当前消息顶层 text 与 markdown 的内容，连续文本片段 SHALL 按顺序拼接；任意非文本片段 MUST 隔断匹配，不得跨越该片段拼造关键词。结构化 mention 的名称、回退 QQ 号、mention_all 的展示文字、其他结构化展示与引用嵌套内容 MUST NOT 参与关键词匹配。用户手动输入普通文本形式的 @名称 SHALL 仍按文本匹配。展示正文和独立提及信号 MUST 保持原语义。

#### Scenario: 命中任意关键词

- **WHEN** `routing.keywords` 为 `["项目", "提醒"]`，当前消息的可匹配连续文本包含“提醒”，且
  allMessage 为 `wait`
- **THEN** Will SHALL 返回 `trigger`
- **AND** SHALL 不调用随机源或 willingness engine

#### Scenario: 关键词数组为空

- **WHEN** `routing.keywords` 为空数组，消息不命中其他配置为 `trigger` 的规则，且
  allMessage 为 `wait`
- **THEN** Will SHALL 返回 `wait`

#### Scenario: 关键词规则与等待规则同时命中

- **WHEN** 消息同时命中一个关键词和配置为 `wait` 的 direct、mention、mentionAll 或
  quote 规则
- **THEN** Will SHALL 返回 `trigger`
- **AND** SHALL 不因其他规则为 `wait` 而抵消关键词触发

#### Scenario: 图片仍可进入消息流水线但不再拥有 routing 分支

- **WHEN** 群消息包含 image segment，且没有 self/all mention、quote 或关键词命中
- **THEN** Will SHALL 只依据 allMessage 的配置返回 `wait` 或 `trigger`
- **AND** SHALL 不读取或要求 `routing.image`

#### Scenario: 结构化提及文字不产生关键词命中

- **WHEN** 关键词仅出现在结构化提及的名称、QQ 号或全体提及展示文字中
- **THEN** 该内容 SHALL 不命中任何关键词规则
- **AND** 普通文本和 Markdown 内的相同关键词 SHALL 仍可命中

#### Scenario: 非文本片段隔断关键词

- **WHEN** 当前消息为文本“提”、结构化提及、文本“醒”，关键词为“提醒”
- **THEN** 系统 SHALL 不因拼接两侧文本命中“提醒”
- **AND** 相邻 text 与 markdown 片段组成的“提醒” SHALL 正常命中
