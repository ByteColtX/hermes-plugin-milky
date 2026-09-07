## ADDED Requirements

### Requirement: 合并转发路径保留全部文本发送单元

出站路径 MUST 在普通文本长度分块和 `[SPLIT]` 的顶层消息数量限制之前，根据 `MILKY_LONG_TEXT_FORWARD_THRESHOLD` 判断是否选择合并转发。选择合并转发后，系统 MUST 删除有效控制标记、过滤空逻辑段，并将所有剩余逻辑段按既有长度边界拆分为 forward 节点；同一批次中的 native `image`、`record`、`video` segment MUST 保留在对应 forward 节点中；不得应用普通路径的“最多三个顶层文本消息”限制。未选择合并转发时，现有 `[SPLIT]` 解析、尾部合并、三条预检和普通长度分块 MUST 保持不变。

#### Scenario: 阈值按可见规范化文本计算

- **WHEN** 输入包含有效 `[SPLIT]`、空白分隔行或 `[[SPLIT]]`，且配置为正值
- **THEN** 阈值判断 SHALL 使用移除有效控制标记和空逻辑段后的可见规范化文本长度
- **AND** `[[SPLIT]]` SHALL 按可见字面量 `[SPLIT]` 计入长度
- **AND** 只有长度严格大于阈值时 SHALL 选择合并转发

#### Scenario: 合并转发保留多个逻辑段

- **WHEN** 选择合并转发且输入包含超过三个非空 `[SPLIT]` 逻辑段
- **THEN** 每个非空逻辑段 SHALL 保留为独立的顺序来源
- **AND** 系统 SHALL 不把尾部逻辑段合并到第三个逻辑段
- **AND** 长度分块后的全部节点 SHALL 进入同一个 `forward.messages` 数组

#### Scenario: 单个逻辑段继续遵守长度边界

- **WHEN** 选择合并转发且某个逻辑段超过当前文本长度边界
- **THEN** 该逻辑段 SHALL 被拆分为多个不超过既有边界的 forward 节点
- **AND** 所有节点拼接后的可见文本 SHALL 与原逻辑段一致

#### Scenario: Native media 不改变文本节点顺序

- **WHEN** 合并转发批次包含文本和 native media segment
- **THEN** 文本分块 SHALL 只拆分文本内容
- **AND** native media SHALL 按原始出站顺序附着到对应的 forward 节点
- **AND** 不得把 native media 发送为 forward 外的独立顶层消息

#### Scenario: 未选择合并转发保持旧分块

- **WHEN** 配置为 `0` 或长度不超过阈值
- **THEN** 系统 SHALL 继续使用现有普通分块算法
- **AND** 有效 `[SPLIT]` 回复经分块后超过三条时 SHALL 在网络访问前整体失败
