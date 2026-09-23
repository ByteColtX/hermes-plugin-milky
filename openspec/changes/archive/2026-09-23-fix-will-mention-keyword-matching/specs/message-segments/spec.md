# Spec Delta

## MODIFIED Requirements

### Requirement: 规范化结果必须提供稳定策略特征

规范化 SHALL 在不重新读取 raw payload 的情况下提供稳定的有序正文和策略特征：至少包括事件
类型、场景、时间、正文/策略文本、独立的 self/all/here/none mention 信号、reply 存在性与
目标 ID、是否引用 Bot 的独立信号、image 存在性、typed segments、分类后的延迟引用
（`media_resource_references`、`file_attachment_references`、forward/reply references）和
安全诊断。text 与 markdown 内容 SHALL 按原顺序保留；合法的结构化 segment SHALL 使用可解释
占位；unknown segment SHALL 不进入正文或关键词内容。reply/forward 的嵌套内容 SHALL 保留为
引用数据，不得隐式并入当前消息正文。

关键词匹配 MUST 只使用当前消息顶层 text 与 markdown 的内容，连续文本片段 SHALL 按顺序拼接；任意非文本片段 MUST 隔断匹配，不得跨越该片段拼造关键词。结构化 mention 的名称、回退 QQ 号、mention_all 的展示文字、其他结构化展示与引用嵌套内容 MUST NOT 参与关键词匹配。用户手动输入普通文本形式的 @名称 SHALL 仍按文本匹配。展示正文和独立提及信号 MUST 保持原语义。

#### Scenario: 结构化 segment 生成稳定正文

- **WHEN** friend 或 group 消息按顺序包含 text、mention、reply、image、file、forward、light_app
  和 xml
- **THEN** 规范化正文 SHALL 保持受支持内容的顺序和对应 placeholder
- **AND** 策略特征 SHALL 独立报告 mention、reply 和 image
- **AND** light_app SHALL 只展示完整 `meta` 根对象

#### Scenario: 未知 segment 不进入正文

- **WHEN** 消息包含未知 segment 以及合法文本
- **THEN** 文本和已支持 placeholder SHALL 保持可处理
- **AND** 未知 segment SHALL 只进入安全诊断和 raw

#### Scenario: 只有未知内容

- **WHEN** 消息只包含未知 segment 或空 segments
- **THEN** 规范化 SHALL 记录明确丢弃原因
- **AND** SHALL NOT 创建空的 Hermes MessageEvent

#### Scenario: 复合 segment 生成策略特征

- **WHEN** friend 或 group 消息按顺序包含 text、mention、mention_all、reply、image 和 unknown
- **THEN** 规范化正文 SHALL 保持受支持内容顺序和可解释占位
- **AND** 策略特征 SHALL 独立报告 self/all mention、reply、self quote 和 image
- **AND** unknown SHALL 只进入安全诊断，不得进入正文或关键词匹配文本

#### Scenario: self quote 与普通 quote 可独立判断

- **WHEN** 一条消息的 reply segment 满足 `reply.data.sender_id == self_id`，另一条消息的 reply segment 指向其他用户
- **THEN** 两条结果 SHALL 都保留 reply 存在性和目标 ID
- **AND** 只有第一条结果 SHALL 报告 self quote

#### Scenario: 只有结构化内容

- **WHEN** 消息只包含合法 face、reply、image、record、video、file、forward、market_face、light_app、xml 或 markdown segment
- **THEN** 规范化结果 SHALL 保持为可处理的结构化消息
- **AND** SHALL 不因正文没有普通 text 而丢弃

#### Scenario: v1.3 不推断 mention here

- **WHEN** v1.3 消息只包含普通 text、mention 或 mention_all
- **THEN** mention 特征 SHALL 只报告 self、all 或 none
- **AND** SHALL 不从文本内容或 mention 名称生成 here 信号

#### Scenario: 结构化提及文字不产生关键词命中

- **WHEN** 关键词仅出现在结构化提及的名称、QQ 号或全体提及展示文字中
- **THEN** 该内容 SHALL 不命中任何关键词规则
- **AND** 普通文本和 Markdown 内的相同关键词 SHALL 仍可命中

#### Scenario: 非文本片段隔断关键词

- **WHEN** 当前消息为文本“提”、结构化提及、文本“醒”，关键词为“提醒”
- **THEN** 系统 SHALL 不因拼接两侧文本命中“提醒”
- **AND** 相邻 text 与 markdown 片段组成的“提醒” SHALL 正常命中
