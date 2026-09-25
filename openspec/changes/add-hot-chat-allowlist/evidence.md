# 热白名单实现与验证记录

验证日期：2026-09-25。变更：add-hot-chat-allowlist。

本地实现、合成验证、真实本地 Hermes 命令分发契约和质量门禁已完成。
真实 Milky/QQ 验收尚未执行，任务 6.3 保持未完成。本文记录实测证据；
设计文档 Context 中的“仅静态源码”描述是实施前基线，不代表当前验证进度。

## 已实现行为与证据分层

| 范围 | 结果与证据 | 验证层次 |
| --- | --- | --- |
| 空规则与命名空间 | 缺省、空值与空列表拒绝普通入站；高优先级空列表遮蔽其他来源；两个通配符显式全放行 | 配置、Gate 和策略单元测试 |
| 指令 | list 分页、add、del/remove 等价、默认当前会话、非法目标拒绝、字面集合操作、unchanged 不重载 | 合成命令测试 |
| 管理路由 | 白名单内外直接合法管理语法进入宿主，保留去重；绕过 Will/资源补全；其他命令保留普通 Gate | 合成 pipeline 测试 |
| core 权限 | 群/私聊无管理员名单、管理员范围拒绝、普通用户获 milky 许可、别名展开；拒绝时无群状态操作和持久修改 | 真实本地 Hermes 分发器，合成事件和群状态 |
| 来源与实例 | 仅使用任务已绑定会话，缺失上下文、环境回退、旧关联、多活动实例拒绝；注册 profile 绑定 | 合成测试及真实宿主临时 profile 契约 |
| 群状态 | 空名单零成员请求，scope=none，各扫描计数为零；未知群独立准备；查询期间事件保留；失败/取消拒绝；成员重试冷却；通配符整体准备；目标禁言不等于禁止保存 | 合成异步 tracker 测试 |
| 保存与发布 | 仅保存 allowed_chats；环境提升为 settings；串行修改、外部冲突、失败/未知不发布或重试；保存后发布失败准确回执 | 共享设置、管理服务测试及真实宿主临时设置写入 |
| 撤销 | 资源等待期间删除及删除再添加均阻止旧批次交接；保留通配符覆盖不误撤销；清理等待正文、系统上下文、Will | 受控异步 pipeline 测试 |
| 生命周期 | 停止失效关联并取消所属准备；单次 register 后原 factory 新实例、同实例完整重连均读取新规则；读取失败不 ready；其他配置仍为启动快照 | 注册及 adapter 生命周期测试 |
| Dashboard | 共享同一设置读写边界，空值提示已同步到源码和随包资源；保存仍提示待重新加载 | 设置测试、前端测试与构建检查 |

新增管理测试集中在 tests/test_hot_allowlist.py；其余证据位于任务 6.1 列出的
配置、Gate、命令、pipeline、tracker、注册、生命周期和 Dashboard 设置测试。
合成通过不能代替实际群身份、Milky 事件时序或 QQ 回执送达的验证。

## 验证命令与结果

跨模块聚焦命令：

    uv run pytest -q tests/test_config.py tests/test_gate_registry.py tests/test_slash_commands.py tests/test_hermes_pipeline.py tests/test_mute_tracker.py tests/test_adapter_lifecycle.py tests/test_plugin_entry.py tests/test_dashboard_settings.py tests/test_hot_allowlist.py

阶段结果：300 passed、1 skipped。随后补充的准备取消事件与通配符准备场景已单独通过，
并被最终全量测试覆盖。最终质量门禁：

| 命令 | 结果 |
| --- | --- |
| uv run pytest -q -rs | 1222 passed、3 skipped |
| uv run ruff check . | 通过 |
| uv run ruff format --check . | 521 files already formatted |
| uv build | sdist 与 wheel 构建通过；实际部署仍是 directory plugin |
| git diff --check | 通过 |
| openspec validate --changes --strict | 4 个 change 全部通过 |
| npm ci --prefix dashboard | 通过 |
| npm run build --prefix dashboard | 通过，已更新随包资源 |
| npm run test --prefix dashboard | 3 passed |
| npm run check --prefix dashboard | 通过 |

全量测试的三个跳过项不能计为集成通过：

- tests/test_adapter_lifecycle.py:637：普通测试环境未加载真实 Hermes host。
- tests/test_hermes_prompt_integration.py:17：需要显式设置 RUN_HERMES_INTEGRATION=1。
- tests/test_multimedia_outbound.py:625：普通测试环境未加载真实 Hermes host。

## 真实本地 Hermes 分发契约

宿主提交：b3a1900e72a16da450ff637aaa37cc23f68992a6。
使用插件 Python 3.13 环境和真实宿主 editable 依赖运行：

    uv run --with-editable /Users/bytecolt/PythonProjects/hermes-agent scripts/hermes_allowlist_contract.py

结果：real Hermes allowlist dispatch contract: passed (no Milky network)。
脚本支持通过 HERMES_SOURCE_ROOT 指定其他源码位置；依赖路径也应相应替换。
首次探测发现宿主已有环境为 Python 3.11，不满足插件语法要求；普通依赖构建又被宿主
wheel 构建策略拒绝。改用上述 editable 方式后成功，不修改宿主源码或真实 profile。

契约使用真实插件注册、core 的空闲命令分发、权限判断、别名展开、任务会话作用域，
以及真实设置读写。事件、身份与群状态均为合成值，设置位于临时目录。
管理分发验证期间禁止 socket connect；没有调用真实 Milky 或发送 QQ 消息。

对应宿主源码证据（行号对应上述提交）：

- gateway/run_inbound.py:793：命令解析与 core 权限判断。
- gateway/run_inbound.py:1024：快捷命令/插件分发，包含 handler 会话作用域。
- gateway/run_inbound.py:1222：空闲命令分发入口。
- gateway/run_busy.py:1081：slash 权限检查。
- gateway/run.py:4266、4295：宿主会话变量和作用域绑定。
- gateway/session_context.py：任务上下文及带环境回退的 accessor；管理实现不使用环境回退。
- gateway/platforms/base.py:3950：消息交接；Milky 空闲路径在首次等待前登记任务。
- gateway/platforms/base.py:3992：忙碌会话路由；后续队列、调度归宿主所有。

此脚本证明分发器内的 handler 可达与上下文兼容；它没有端到端驱动真实 SSE、完整
Gateway 生命周期或忙碌会话队列，也没有验证实际 QQ 回执送达。插件在资源补全后、
调用宿主前无等待地检查授权和撤销代次；已经交给宿主的消息不由插件取消。

## 真实 Milky/QQ 验收：blocked

当前未指定明确获准的测试 profile、QQ 群/私聊目标及发送/配置修改范围。
依照本 change 任务 6.3 和项目工作边界，没有改写真实配置，没有执行真实发送或上传。
仍需在明确授权后逐项验收：

1. 空名单冷启动后，从 core 允许的群与私聊执行省略目标的 add；收到成功回执后普通入站生效。
2. 指定目标及通配符增减，del/remove 等价；删除最后一项后仍能管理，普通入站拒绝。
3. 完整重启保留设置；同 profile Web 刷新显示 QQ 修改后的值；Web 保存仍需重新加载。
4. 来源禁言拒绝读写，目标禁言可保存但不能普通交互；查询期间真实禁言事件保持。
5. 持久化后进程终止、QQ 回执失败和外部设置竞争的实际表现；回执失败不得重复修改。

如使用 smoke 写模式，必须显式传 --allow-write 且目标命中运行时
MILKY_ALLOWED_CHATS。真实验收通过之前，不将上述待验收项报告为成功。

## 并发、依赖及回滚

管理修改只在单个活动实例内串行。保存前版本检查和读回核验能发现部分外部竞争，
不能替代宿主未提供的跨入口条件事务，不保证与 Web/人工编辑完全原子，也不广播到
其他进程。保存结果未知不自动重试或回滚；已保存未发布应重新加载并查询差异。

已核对 proposal、七份 delta spec、design、tasks 与 README、ARCHITECTURE、manifest、
Dashboard 文案：空值、语法、core 权限、保存/在线状态和完整重连语义一致。
未实施的 add-idle-session-wakeup 必须使用共享最新白名单、空名单无候选；
本次没有实现该 change，也不将其规划写为当前能力。

升级时，如需全部放行，应显式配置 group:* 与 dm:*。
回滚旧插件前先停止接收，审阅当前有效配置并改为明确的非空受限名单；
需要拒绝全部时在宿主停用平台。旧版本把空列表解释为全部放行，不能保留空列表直接回滚。
