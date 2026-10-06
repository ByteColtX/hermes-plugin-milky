# Proposal

## Why

Dashboard 路由直接编排提交校验、上传候选检查、任务持久化和派发，上传层还直接读取任务存储判断活动引用。此次提案集中任务与上传协作，并修复重复导入在候选已消费或回收后可能无法返回原任务的契约差异。

## What Changes

- 加深管理任务 module，让路由面对签发请求、提交任务、查询、取消和关闭的小 interface；把手工派发、恢复、提交保护和进度持久化编排收进 implementation。
- 由任务 module 统一拥有请求标识去重、每 profile 单执行者与有限队列、owner 与启用状态复核、取消及关闭、终态保留、恢复时不自动重放。
- 上传活动引用与删除、回收的协调决策进入同一 module；上传实现不再理解任务存储字段或状态。
- 有效已接收请求的重提先按持久身份返回原任务；只有新导入任务才检查当前候选，不因原输入已被消费而拒绝查询原任务。
- 将图库执行适配器需要的提交保护与逐项确认保留为内部 seam；图库维护、受控上传和视觉工作继续拥有各自业务规则。
- 保留已确认项、在途 unknown、未执行项及视觉实际结束前的固定名额；关闭 Web 任务仍不影响独立 QQ 运行或其他 owner。
- 将分散测试收敛到 module interface，保留 HTTP/profile 和真实宿主专项，确保内部重组能由可观察结果验证。

## Capabilities

### New Capabilities

无；本 change 为架构重构与既有幂等契约修复。

### Modified Capabilities

- milky-web-dashboard：明确重提与当前上传输入状态无关的既有幂等契约，补充候选消费/回收后的验收场景。其他主规范保持。

## Impact

- 主要影响 dashboard/plugin_api.py、dashboard/jobs.py、任务调用的上传和贴纸执行适配，以及相应测试；HTTP 请求、响应、错误分类、任务状态、配额和保留策略按当前主规范保留。
- 当前本地测试证明任务去重、取消、关闭、恢复、停用和视觉迟到等已有行为；历史 Dashboard evidence 包含真实宿主与视觉记录，本轮规划不继承为新 implementation 已验收。相关基线命令为 `uv run pytest -q -rs tests/test_dashboard_jobs.py tests/test_dashboard_lifecycle_edges.py tests/test_dashboard_visual_worker.py`，结果 20 passed、无 skip，只提供本地合成依赖证据。
- 与未实施的自动贴纸库和群管 change 共用管理入口时，未来集成必须保持既有固定操作范围，不在本 change 中加入自动收集、案件、审批或状态变更。
- 非目标：新增页面或 endpoint、跨 profile 共享任务、改变贴纸业务语义、改动配置/凭证保存、替换宿主认证、修改 Hermes core、连接 Milky、重新定义视觉并发上限或提供分布式恰好一次执行。
