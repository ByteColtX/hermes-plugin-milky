# Tasks

## 1. 固定当前行为与 module interface

- [ ] 1.1 形成请求签发、提交、查询、取消、上传删除/回收和关闭的调用契约；验证主规范覆盖，明确路由先检查上传候选造成的重提差异，交付输入已消费/回收后仍返回原任务且无新增执行的测试。
- [ ] 1.2 通过真实临时存储及合成执行 adapter 增补 module interface 行为测试，覆盖相同标识去重、不同内容 conflict、非法候选不持久化、队列/历史有界、缺失库只读不创建；验证聚焦测试通过且无需直接操纵 worker 或存储对象才能断言结果。
- [ ] 1.3 在架构文档中记录 module 的 state/resource ownership、外部 interface 与内部提交保护 seam；验证文档对照当前设计，不将未实现 interface 写为已交付。

## 2. 收拢管理任务运行编排

- [ ] 2.1 将持久请求身份判定放在新候选校验之前；通过 endpoint 验证同内容重提返回原任务、不同内容 conflict、过期 expired；分别覆盖输入仍存在但已消费和批次已回收的重提，确认不创建新任务、不重复执行，新任务非法候选不持久化，并同步更新架构说明。
- [ ] 2.2 将活动上传引用、删除与回收的协调决策收进 module，移除上传实现对任务存储字段的直接知识；验证排队/运行任务和未结束视觉读取均保护输入，并发提交与回收不产生引用空隙。
- [ ] 2.3 将恢复、启动与单执行者/owner 判定收进 module，迁移路由到固定请求 interface；验证同一任务重提只返回原 ID，两个 owner 仍按既有规则串行且不接管存活实例任务。
- [ ] 2.4 将 operation 执行 adapter、逐项保护和进度确认收进内部 seam，保留图库、上传与视觉业务行为；验证 import 只使用已选 batch，逐项成功/conflict/unknown/未执行结果与当前 fixture 一致。
- [ ] 2.5 通过同一 module interface 接入取消、停用、关闭和保守恢复；验证已完成项保留、后续提交被阻止、在途 unknown 不自动重放、另一个 owner/profile 不受关闭影响。
- [ ] 2.6 将接口测试已完整覆盖的私有状态测试替换为可观察结果断言，保留存储完整性与线程名额专项；验证原契约覆盖不减少，并更新架构文档中的调用方向和运行时所有权。

## 3. 验证视觉与宿主 seam

- [ ] 3.1 运行视觉迟到、实际线程名额与上传引用保护专项；验证取消等待后迟到结果不入库、线程实际结束前不回收输入或提前释放名额，明确这些为本地合成 provider 证据。
- [ ] 3.2 在可用真实 Hermes 环境重跑既有 Dashboard probe，使用隔离合成 profile 验证 profile 归属、停用拒绝与路由关闭；验证 evidence 分开记录 fake/真实宿主结果及 skip/unsupported，不要求本 change 连接 Milky 或真实视觉提供者。
- [ ] 3.3 运行 `uv run pytest -q -rs`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check` 和 `openspec validate --changes --strict`；验证本轮代码、文档、主规范和 manifest 的行为一致，真实环境阻塞单独记录。
