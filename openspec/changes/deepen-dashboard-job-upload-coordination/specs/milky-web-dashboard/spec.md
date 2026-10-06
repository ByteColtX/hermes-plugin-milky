## MODIFIED Requirements

### Requirement: 维护任务可查询且不会因重试重复执行

上传导入、单项或批量编辑、人工覆盖清除、重新分析、删除、清理及索引修复 SHALL 返回不透明任务 ID；任务持久记录创建时 profile、操作、有限目标、逐项状态和汇总，不保存凭证、绝对路径、媒体 bytes、视觉原文或异常正文。状态 SHALL 区分 queued、running、succeeded、partial、failed、cancelled、interrupted，未知外部结果 SHALL 在对应项中明确标示。每 profile 同时执行最多一个维护批次、最多排队 10 个，单批视觉并发沿用已有上限；超限返回 busy。

同一 profile 内相同请求标识和相同操作内容的重提 MUST 返回原任务而不重复执行；相同标识但不同内容 MUST 返回 conflict。页面断开和重复轮询 SHALL 不再次提交操作。重启恢复时 SHALL 只将已确认失去执行者的未终结任务标为 interrupted，不修改其他仍存活实例拥有的任务，也不自动重放未确认步骤；用户可对确认未完成的项发起新的显式任务。取消 SHALL 停止未开始项，保留已完成项，无法撤销的在途结果不得伪称未执行。终态记录保留 7 天，每 profile 最多保留 1000 条终态记录并淘汰最早记录；活动任务不得被历史清理删除。已过期记录对应的旧请求标识 SHALL 返回 expired，不自动作为新请求重执行。

#### Scenario: 双击与断线重提

- **WHEN** 用户对同一导入请求双击或因断线用同一请求标识重提
- **THEN** 系统 SHALL 返回同一个任务及当前进度
- **AND** SHALL 不再次调用视觉、不重复入库或重复删除

#### Scenario: 批次中断和恢复查看

- **WHEN** Dashboard 在部分文件完成之后停止并重新启动
- **THEN** 查询 SHALL 显示已完成项和 interrupted 的未完成项
- **AND** SHALL 不自动把不确定视觉请求或文件变更重新执行

#### Scenario: 队列和历史有界

- **WHEN** 队列已满或请求引用过期任务标识
- **THEN** 系统 SHALL 分别返回 busy 或 expired
- **AND** SHALL 不创建无限任务、自动重放旧操作或删除尚在执行的任务

#### Scenario: 导入输入已消费或回收后重提

- **WHEN** 同一 profile 的请求标识和内容仍有效且已绑定原任务，操作者在其上传输入已消费或回收后再次提交相同请求
- **THEN** 系统 SHALL 返回原任务标识，不要求重新上传或重新确认已经消费的候选
- **AND** SHALL 不创建新任务、不再次调用视觉或重复变更；相同标识不同内容仍返回 conflict，过期标识仍返回 expired
