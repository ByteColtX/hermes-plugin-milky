# 热白名单实现与验证记录

首次验证：2026-09-25；本轮修订验证：2026-09-26。变更：add-hot-chat-allowlist。

本轮按用户确认调整：中文回执、原始来源名称、完整列表无分页；管理操作不查询群状态，
新授权群改在首次获准入站时准备。以下旧版测试数字保留为历史记录，以文末本轮证据为准。

本地实现、合成验证、真实本地 Hermes 命令分发契约和质量门禁已完成。
用户已在本会话明确确认“我已完成实机验收了”，任务 6.3 据此完成。该结论是用户确认，
不是代理执行或观测的真实 Milky/QQ 测试；未提供逐项日志或环境详情。本文区分证据来源；
设计文档 Context 中的“仅静态源码”描述是实施前基线，不代表当前验证进度。

## 已实现行为与证据分层

| 范围 | 结果与证据 | 验证层次 |
| --- | --- | --- |
| 空规则与命名空间 | 缺省、空值与空列表拒绝普通入站；高优先级空列表遮蔽其他来源；两个通配符显式全放行 | 配置、Gate 和策略单元测试 |
| 指令 | list 完整输出（本轮取消分页）、add、del/remove 等价、默认当前会话、非法目标拒绝、字面集合操作、unchanged 不重载 | 合成命令测试 |
| 管理路由 | 白名单内外直接合法管理语法进入宿主，保留去重；绕过 Will/资源补全；其他命令保留普通 Gate | 合成 pipeline 测试 |
| core 权限 | 群/私聊无管理员名单、管理员范围拒绝、普通用户获 milky 许可、别名展开；拒绝时无群状态操作和持久修改 | 真实本地 Hermes 分发器，合成事件和群状态 |
| 来源与实例 | 仅使用任务已绑定会话，缺失上下文、环境回退、旧关联、多活动实例拒绝；注册 profile 绑定 | 合成测试及真实宿主临时 profile 契约 |
| 群状态 | 空名单零成员请求，scope=none，各扫描计数为零；未知群独立准备；查询期间事件保留；失败/取消拒绝；成员重试冷却；通配符保存无扫描；首次获准入站按需准备，禁言拒绝普通消息 | 合成异步 tracker 测试 |
| 保存与发布 | 仅保存 allowed_chats；环境提升为 settings；串行修改、外部冲突、失败/未知不发布或重试；保存后发布失败准确回执 | 共享设置、管理服务测试及真实宿主临时设置写入 |
| 撤销 | 资源等待期间删除及删除再添加均阻止旧批次交接；保留通配符覆盖不误撤销；清理等待正文、系统上下文、Will | 受控异步 pipeline 测试 |
| 生命周期 | 停止失效关联并取消所属排队操作；单次 register 后原 factory 新实例、同实例完整重连均读取新规则；读取失败不 ready；其他配置仍为启动快照 | 注册及 adapter 生命周期测试 |
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

## 真实 Milky/QQ 验收：早期 blocked 记录（已由后续用户确认解除）

当时未指定明确获准的测试 profile、QQ 群/私聊目标及发送/配置修改范围。
依照本 change 任务 6.3 和项目工作边界，没有改写真实配置，没有执行真实发送或上传。
当时列出的待验收范围如下；后续仅收到用户整体完成确认，不据此虚构各项详细结果：

1. 空名单冷启动后，从 core 允许的群与私聊执行省略目标的 add；收到成功回执后普通入站生效。
2. 指定目标及通配符增减，del/remove 等价；删除最后一项后仍能管理，普通入站拒绝。
3. 完整重启保留设置；同 profile Web 刷新显示 QQ 修改后的值；Web 保存仍需重新加载。
4. 管理命令不查询来源/目标群状态；首次获准入站按需准备，普通消息仍受禁言限制；查询期间真实禁言事件保持。
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

## 2026-09-26 文案与管理流程修订

本轮按用户确认的 mock 落地：成功、重复、配置差异和失败结果统一中文提示；原始来源名称
保持不变。list 不接受 --page，完整排序输出；配置与运行不同则分别展示，明确提示重启
Gateway。Web 保留现有保存与刷新按钮，不新增重启操作。

管理服务已移除群状态依赖，路由也不读取缓存禁言状态。规则修改不触发群列表/成员查询，
不生成禁言提示。普通入站在自身与白名单检查后，按需准备新增群状态；等待期间撤销或
删除再添加均拒绝旧消息，未知/失败/禁言继续拒绝普通消息。回执沿既有发送限制处理。

本轮验证：

| 命令 | 结果 |
| --- | --- |
| uv run pytest -q -rs | 1244 passed、3 skipped（跳过原因同上） |
| uv run ruff check . | 通过 |
| uv run ruff format --check . | 534 files already formatted |
| uv build | sdist、wheel 通过 |
| git diff --check | 通过 |
| openspec validate --changes --strict | 当前主工作区 5 个 change 全部通过 |
| uv run --with-editable /Users/bytecolt/PythonProjects/hermes-agent scripts/hermes_allowlist_contract.py | 真实本地 Hermes 分发契约通过，无 Milky 网络 |

新增/调整覆盖：合法分页参数也拒绝；101 条名单完整排序；200 条名单经真实 sender 的
普通分块与合并转发两种路径均完整保留文本；配置与运行分组；保存未应用、外部冲突与
未知结果；群/私聊白名单内外管理路由不读取或查询群状态；普通消息按需准备成功、失败、
禁言、撤销、删除再添加、自身及未授权场景。首次全量中新增发送测试因使用不满足发送
协议最小值的合成 QQ 号失败，修正测试目标后最终全量通过，未改动发送实现。

以上修订验证结束时，代理尚未执行真实 QQ 验收，任务 6.3 当时保持 blocked；代理未重启 Gateway、修改真实配置或发送消息。后续用户确认见下节。

## 2026-09-26 帮助收尾、用户验收确认与规格同步

用户明确确认“我已完成实机验收了”，据此完成任务 6.3。此项标记为用户报告，
未提供逐项日志、测试 profile 或协议端版本，代理没有重复执行真实 Milky/QQ 操作。
该确认早于本节 help 文案改动，本节新增行为的证据为以下自动化验证。

新增空参数及 help 静态帮助，标题统一为 Milky · 会话白名单，使用 Usage、Commands、
Targets、Examples 与 e.g. 示例；非法参数使用紧凑 Usage/Help 提示。list 使用 Source
标签及原始配置来源。按用户要求，帮助不加并发 Note，异常提示不附加查看命令。

| 命令 | 结果 |
| --- | --- |
| uv run pytest -q tests/test_hot_allowlist.py tests/test_slash_commands.py tests/test_plugin_entry.py | 137 passed |
| uv run pytest -q -rs | 1262 passed、3 skipped，原因同前述记录 |
| uv run --with-editable /Users/bytecolt/PythonProjects/hermes-agent scripts/hermes_allowlist_contract.py | 真实本地 Hermes 分发契约通过；新增群/私聊帮助权限允许、拒绝及配置零读写检查，无 Milky 网络 |
| uv run ruff check . | 通过 |
| uv run ruff format --check . | 534 files already formatted |
| uv build | sdist 与 wheel 通过 |
| openspec validate --specs --strict | 30 passed、0 failed |
| openspec validate --changes --strict | 4 passed、1 failed；当前白名单 change 通过，关联差异见下文 |

七份 delta 已合并到主规格，新增 hot-chat-allowlist，其余六份更新对应要求；
核验全部 delta 要求及场景落入主规格，未涉及的要求保持原内容。
同时修正本 change 两处残留的“管理操作须检查来源群状态”描述，与已实现及用户确认的边界一致。

同步使未实施的 add-group-moderation-workflow 的 inbound-gates MODIFIED 块落后于
新主规格：缺少“空名单仍能管理”场景。联合 change 校验因此失败；该关联 change 需在
后续实施前更新，当前没有修改其规划或代码。当前白名单 change 与所有主规格校验通过。
