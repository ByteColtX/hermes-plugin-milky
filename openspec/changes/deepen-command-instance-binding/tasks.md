# Tasks

## 1. 建立实例归属 module

- [ ] 1.1 建立登记、就绪更新和撤销的窄 interface，隐藏三类绑定记录；登记与撤销使用一致的实例身份判断和现有同步机制，撤销一个实例不影响其他实例；用命令测试验证静态帮助、唯一实例、多实例降级和跨 profile 拒绝选择。
- [ ] 1.2 迁移运行生命周期登记与就绪更新，同时更新架构所有权说明；运行 tests/test_adapter_lifecycle.py 与 tests/test_runtime_status.py 验证初始化 status 可读、同步前协议访问拒绝、失败与停止准确表达。

## 2. 迁移选择与失效

- [ ] 2.1 迁移状态观察和协议信息的实例选择；以等待中解绑、运行代次变化和完整重连测试验证迟到结果降级、不借用旧实例。
- [ ] 2.2 迁移白名单管理者绑定并保留来源关联与单次消费；运行 tests/test_hot_allowlist.py、tests/test_slash_commands.py，验证 core 拒绝无操作、停止关联失效、多实例互不影响。
- [ ] 2.3 将内部集合断言替换为命令/生命周期 interface 的可观察结果，更新 ARCHITECTURE.md；核对回执、错误分类与原测试场景不丢失。

## 3. 综合验证

- [ ] 3.1 运行完整 pytest、Ruff 检查与格式检查、uv build、git diff --check 和 OpenSpec 严格校验，记录 skip 与外部阻塞。
- [ ] 3.2 在可用真实 Hermes host 核验命令分发、profile 归属和停止行为；以独立 evidence 区分 fake 与真实结果，宿主不可用不得报告集成成功。
