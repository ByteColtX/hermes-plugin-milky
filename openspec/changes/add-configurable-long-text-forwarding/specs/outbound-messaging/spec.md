## ADDED Requirements

### Requirement: 超长文本和 native media 使用单一 forward segment

当 `MILKY_LONG_TEXT_FORWARD_THRESHOLD` 为正值且一次出站文本的可见规范化长度超过阈值时，系统 MUST 将本次批次原本会产生的所有非空文本发送单元，以及同一批次中的 native `image`、`record`、`video` 等 Milky `OutgoingSegment`，按原顺序放入同一个 `forward` segment 的 `messages` 数组。每个节点 MUST 包含安全的 `user_id`、`sender_name` 和 `segments`；节点身份优先使用已确认的 Bot 身份，身份缺失、读取失败或昵称不安全时 MUST 使用固定 fallback `user_id=10001`、`sender_name=QQ用户`。该路径 MUST 不受普通文本最多三条顶层消息预检限制。系统 MUST 在首个消息 Action 前完成所有 forward 节点、嵌套 segment、身份字段和本地限制的预检，并 MUST 只调用一次对应的 `send_group_message` 或 `send_private_message`。

#### Scenario: 普通超长文本收纳为一个合并转发

- **WHEN** 配置为正值，规范化文本总长度超过阈值，且文本按既有长度边界会产生多个发送单元
- **THEN** 系统 SHALL 发送一个包含多个 `messages` 节点的 `forward` segment
- **AND** SHALL 保留所有节点的原始顺序和完整可见文本
- **AND** SHALL 不发送多个顶层普通 text message

#### Scenario: 分段文本的所有单元进入同一 forward

- **WHEN** 配置为正值，文本超过阈值并包含一个或多个有效 `[SPLIT]`
- **THEN** 系统 SHALL 将每个非空逻辑段及其长度分块都作为同一个 `forward.messages` 数组中的节点
- **AND** SHALL 不将任一逻辑段单独发送为顶层消息
- **AND** SHALL 不因普通路径的三条顶层消息限制而拒绝该合并转发

#### Scenario: Native media 进入同一 forward

- **WHEN** 合并转发批次同时包含文本和 native `image`、`record` 或 `video` segment
- **THEN** 系统 SHALL 将这些 native segment 放在同一个 `forward.messages` 节点序列中
- **AND** SHALL 保留文本与 native segment 的原始顺序
- **AND** SHALL 不先发送文本再通过独立 media Action 发送这些 native segment

#### Scenario: 未超过阈值或配置关闭

- **WHEN** 配置为 `0`，或可见规范化文本长度不超过正阈值
- **THEN** 系统 SHALL 使用现有普通文本路径
- **AND** SHALL 保持当前普通分块、`[SPLIT]` 三条预检和失败位置语义

#### Scenario: Forward 节点优先使用已确认身份

- **WHEN** 系统构造自动合并转发节点
- **THEN** 每个节点 SHALL 使用已确认的 Bot `user_id` 和 `sender_name`
- **AND** 系统 SHALL 不从入站正文、forward ID 或未确认字段推断身份

#### Scenario: Forward 身份失败时使用固定 fallback

- **WHEN** live 连接身份不可用，或 standalone 的 `get_login_info({})` 被拒绝、超时、传输未知、响应 malformed，或返回的昵称为空/包含控制字符
- **THEN** 每个 forward 节点 SHALL 使用 `user_id=10001` 和 `sender_name=QQ用户`
- **AND** 系统 SHALL 继续执行单一 forward 消息 Action
- **AND** 系统 SHALL 不把身份失败改写为普通分块发送或推断动态身份

#### Scenario: 固定 fallback 仍须通过本地 schema 校验

- **WHEN** 系统选择固定 fallback 身份构造 forward 节点
- **THEN** fallback `user_id` 和 `sender_name` SHALL 与普通 forward 节点使用相同的 ID 和非空文本校验
- **AND** 若 fallback 无法通过校验，系统 SHALL 在任何消息 Action 前返回 `malformed`

#### Scenario: Forward 请求和成功响应

- **WHEN** 合并转发目标为 group
- **THEN** 请求 SHALL 使用 `POST /api/send_group_message`，body SHALL 包含 `group_id` 和只含一个 `forward` segment 的 `message`
- **AND** `forward.data.messages[]` 的每个节点 SHALL 包含 `user_id`、`sender_name` 和 `segments`
- **AND** 成功响应 SHALL 使用 `status=ok`、`retcode=0` 和 `data.message_seq`
- **AND** 插件 SHALL 将 `data.message_seq` 暴露为单一 `message_id`，不产生 `forward_id` 或 continuation ID

#### Scenario: 文档或文件不进入自动 forward

- **WHEN** 出站内容包含文档/文件，而不是 Milky outgoing `image`、`record` 或 `video` segment
- **THEN** 文档/文件 SHALL 不进入自动合并转发
- **AND** 既有独立 file upload 行为 SHALL 保持不变
- **AND** 系统 SHALL 不把文档/文件伪装成 outgoing forward segment

#### Scenario: Forward 预检失败

- **WHEN** 任一节点、嵌套 segment、身份字段或本地请求边界预检失败
- **THEN** 系统 SHALL 在任何消息 Action 前返回可分类的本地失败
- **AND** SHALL 不发送前序普通消息、不截断内容且不将失败伪装为成功

#### Scenario: 合并转发 Action 失败

- **WHEN** 单一 `forward` 消息 Action 返回协议拒绝、传输未知、超时或其他远端失败
- **THEN** 系统 SHALL 保留该失败分类
- **AND** SHALL 不自动改发普通分块、不盲目重试可能已产生副作用的 Action

#### Scenario: standalone 身份成功时复用查询结果

- **WHEN** standalone 选择合并转发且 `get_login_info({})` 成功返回安全的 `uin` 和昵称
- **THEN** 所有 forward 节点 SHALL 使用该次查询确认的身份
- **AND** `get_login_info` SHALL 最多调用一次
- **AND** 普通分块路径 SHALL 不调用 `get_login_info`

#### Scenario: 有序批次与独立 MEDIA handoff 的边界

- **WHEN** Hermes 提供一个带顺序的文本/native media 出站批次
- **THEN** 该批次的文本和 native media SHALL 一起进入同一个 `forward` segment
- **AND** 文档/文件 SHALL 继续由既有独立 file upload 路径处理，不进入该 forward
- **WHEN** Hermes 只提供已经分离的文本调用和 `MEDIA:` 附件调用
- **THEN** 插件 SHALL 不猜测两次调用属于同一 forward 批次
- **AND** SHALL 将缺少有序批次契约记录为前置能力边界，不通过延迟或重复发送伪造同一 forward
