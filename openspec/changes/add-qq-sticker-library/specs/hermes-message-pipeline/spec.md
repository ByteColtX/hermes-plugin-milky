## ADDED Requirements

### Requirement: Resource resolution MUST feed only current-message images to automatic sticker collection

在既有资源 resolver 完成且 `MessageEvent` 交接前，pipeline MAY 为当前消息启动自动 sticker collection。
该旁路 SHALL 只消费已经由 Hermes helper materialize 的当前顶层图片，不得重新查询远端资源、复制下载器、
改变 `media_urls`/`media_types` 顺序或把自动收集 metadata 写入普通正文和历史 `channel_context`。
自动收集失败不得阻断原有 Hermes handoff。

#### Scenario: Trigger batch starts automatic collection

- **WHEN** batch 已通过 Gate/Will 并完成当前消息资源解析
- **THEN** pipeline SHALL 只把当前顶层图片提交给自动收集旁路
- **AND** 历史图片、forward 图片和 reply 图片 SHALL 不进入自动收集输入
- **AND** Hermes MessageEvent 的既有媒体契约 SHALL 保持不变

#### Scenario: Automatic collection stages a current image

- **WHEN** 当前顶层图片已 materialize 为有效本地附件
- **THEN** 系统 MAY 为视觉判定建立受大小和 TTL 限制的内部 staging
- **AND** staging 或质量判定结果 SHALL 不暴露为 Agent 可提交的 candidate ID
- **AND** 未通过质量门控的 staging SHALL 被清理且不得创建 library entry

#### Scenario: Collection side path fails

- **WHEN** staging、视觉判定、任务调度或 sticker store 失败
- **THEN** pipeline SHALL 继续执行既有 mapper 和 `handle_message()` handoff
- **AND** SHALL 不重新下载资源、不改变 Will/reply cost、不报告 sticker 收藏成功

### Requirement: Automatic sticker collection MUST respect existing ingress ordering

自动 sticker collection MUST 在 canonical、dedup、admission、Gate 和 Will trigger 之后启动；wait、Gate deny、
duplicate、temp 和非 `message_receive` 事件 SHALL 不进入自动收集流程。pipeline SHALL 不因 sticker library
复制 Hermes busy/follow-up/interrupt 队列。

#### Scenario: Gate deny does not collect

- **WHEN** SelfMessageGate、ChatAllowlistGate 或 MutedGroupGate 拒绝消息
- **THEN** 系统 SHALL 不创建 staging、不读取媒体文件且不改变 library

#### Scenario: Wait then trigger preserves boundary

- **WHEN** 图片消息先进入 wait buffer，后续消息使当前 chat trigger
- **THEN** 只有当前消息的顶层图片 SHALL 进入自动收集流程
- **AND** 之前 wait 的历史图片 SHALL 继续只作为历史上下文

#### Scenario: Collection finishes after handoff

- **WHEN** Hermes handoff 已完成而视觉判定任务仍在运行
- **THEN** 任务 MAY 在后台完成或被生命周期取消
- **AND** 任务结果 SHALL 不修改已经交接的正文、媒体顺序、Gate、Will 或 reply cost

### Requirement: Explicit manual sticker commands MUST remain separate from automatic collection

显式 `/milky sticker add`、`edit`、`reanalyze`、`del`、`cleanup` 和 `reindex` SHALL 继续走已交付的命令维护路径，
不进入普通 `message_receive` 的自动收集旁路。命令扫描的固定 inbox、library 和 junk 资源 SHALL 不被当作当前
消息顶层图片重复提交；自动收集也 SHALL 不隐式调用或模拟任一手动维护命令。

#### Scenario: Manual add does not double collect

- **WHEN** command handler 收到显式 `/milky sticker add` 并扫描人工 inbox
- **THEN** 系统 SHALL 只执行手动维护规范定义的校验、视觉和文件归宿
- **AND** SHALL 不为该命令创建当前消息自动 collection staging 或新的 Agent turn

#### Scenario: Automatic collection does not invoke maintenance

- **WHEN** 普通当前消息图片通过资源解析并进入自动收集
- **THEN** 系统 SHALL 只创建自动作用域条目或返回固定失败分类
- **AND** SHALL 不扫描 inbox、不移动 junk、不执行 edit/reanalyze/del/cleanup/reindex
