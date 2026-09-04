## MODIFIED Requirements

### Requirement: 超长文本按明确边界拆分

超过 Milky 或 LLBot 限制的文本 MUST 按明确且可诊断的边界拆分为多个发送单元，每个单元的结果 SHALL 可独立观察。包含有效 `[SPLIT]` 行的回复 MUST 先按 `[SPLIT]` 形成最多三个逻辑文本单元，再应用既有长度边界；空逻辑单元不得发送，超过三个逻辑单元时尾部内容 MUST 合并到第三个单元。若长度拆分使实际文本消息数超过三条，系统 MUST 在网络访问前整体拒绝该分段回复，不得截断或部分发送。未包含有效 `[SPLIT]` 的普通长文本继续遵守既有长度拆分，不受三条分段上限影响。

#### Scenario: 超长普通文本

- **WHEN** 未包含有效 `[SPLIT]` 的文本超过配置或协议允许的长度
- **THEN** 系统 SHALL 按边界拆分而不是截断内容
- **AND** SHALL 依次处理每个发送单元并保留失败位置

#### Scenario: 超长文本

- **WHEN** 文本超过配置或协议允许的长度
- **THEN** 系统 SHALL 按边界拆分而不是截断内容
- **AND** SHALL 依次处理每个发送单元并保留失败位置

#### Scenario: 有效分段先于长度拆分

- **WHEN** 文本包含独立成行、大小写严格匹配的 `[SPLIT]` 且任一逻辑段超过长度上限
- **THEN** 系统 SHALL 先移除有效标记并确定逻辑段，再对逻辑段应用长度拆分
- **AND** SHALL 保持所有可见文本及其相对顺序

#### Scenario: 分段后的物理消息超过上限

- **WHEN** 有效 `[SPLIT]` 回复经长度拆分后需要四条或更多文本消息
- **THEN** 系统 SHALL 在任何消息 Action 前返回可分类的本地边界失败
- **AND** SHALL 不发送前序文本或截断后续文本

### Requirement: 文本分段与附件投递保持当前交接顺序

当 Hermes 从同一 Agent 回复中提取 `MEDIA:` 附件时，包含有效 `[SPLIT]` 的文本部分 MUST 先由 Hermes 的文本投递路径按顺序交给 Milky；随后附件 MUST 按 Hermes 提取顺序通过既有图片、语音、视频 native message Action 或独立文件 upload Action 投递。`[SPLIT]` MUST NOT 改写、吞并或重排 `MEDIA:` 指令。当前能力不支持文本段和附件在同一回复内交错投递；文本分段的最多三条限制只约束插件管理的文本发送单元，不把 Hermes 独立附件 Action 假装纳入同一文本批次。

#### Scenario: 文本、分段标记和媒体附件同现

- **WHEN** Agent 回复包含第一段文本、有效 `[SPLIT]` 行、第二段文本和一个有效 `MEDIA:` 附件指令
- **THEN** 用户 SHALL 先收到第一段文本，再收到第二段文本，最后收到该附件
- **AND** 有效 `[SPLIT]` 和 `MEDIA:` 指令 SHALL 不作为普通可见文本发送

#### Scenario: 多个附件跟随文本完成后发送

- **WHEN** Agent 回复包含多个文本段和多个按顺序提取的媒体或文件附件
- **THEN** 所有文本发送单元 SHALL 在第一个附件 Action 前完成其既定顺序提交
- **AND** 附件 SHALL 按 Hermes 提取顺序逐项投递
- **AND** 文本段与附件 SHALL 不交错

#### Scenario: 附件失败不伪造交错成功

- **WHEN** 文本已成功投递但后续媒体或文件 Action 失败
- **THEN** 系统 SHALL 保留文本成功结果和附件的安全失败分类
- **AND** SHALL 不将附件失败改写为文本成功或发送路径文本 fallback

#### Scenario: 需要交错交接时保持未支持边界

- **WHEN** 上游只提供文本正文和独立附件列表而没有带顺序的文本/附件事件流
- **THEN** Milky plugin SHALL 继续使用文本先于附件的固定顺序
- **AND** SHALL 不根据原始回复正文中的 `MEDIA:` 位置猜测或模拟交错顺序
- **AND** SHALL 将真正的交错投递保留为需要 Hermes core 有序交接契约的后续能力
