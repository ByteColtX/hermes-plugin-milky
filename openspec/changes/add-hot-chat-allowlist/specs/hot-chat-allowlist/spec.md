# Spec Delta

## Purpose

为经 Hermes core 允许的调用者提供可从未放行会话使用的显式白名单指令，统一当前会话推导、跨重启持久化和在线生效的可观察行为，并准确区分规则修改、入站授权、群可发送状态与失败结果。

## ADDED Requirements

### Requirement: 白名单管理的命令权限由 Hermes core 决定

系统 MUST 提供 /milky allowlist list、/milky allowlist add [目标] 和 /milky allowlist del [目标] 纯文本指令。remove MUST 作为 del 的等价别名接受，统一执行同一删除流程；帮助 SHALL 优先展示 del 并注明 remove。两种拼写 SHALL 具有相同的参数校验、缺省目标、字面集合操作、持久化、回执和 core 权限语义；单次调用不得重复执行。remove SHALL 同样属于直接白名单管理路由，不属于其他命令展开的别名。包括这些子命令在内的所有 slash 权限 MUST 由 Hermes core 决定。插件 MUST NOT 读取、解释或复制管理员名单、普通用户命令许可、QQ 角色或子命令权限规则，MUST NOT 在 core 放行后额外要求调用者命中管理员名单。core 对管理员配置缺省、为空、格式异常及作用域的处理 SHALL 保持其自身语义；插件不得另设默认授权或拒绝规则。

管理读写 MUST 经由 core 的命令分发；core 拒绝时 SHALL 不执行插件管理操作。core 放行后插件 SHALL 仅校验参数、可信来源会话、当前 profile、唯一活动实例及执行所需运行状态，不把这些校验用作角色或命令权限判断。来源与 profile SHALL 不从正文、参数或进程环境猜测，缺少必要上下文时 SHALL 返回 unsupported 且不读写设置。目标 SHALL 可为当前 profile 的合法 group/dm 规则。

#### Scenario: core 允许跨命名空间管理

- **WHEN** core 允许来源群的调用者执行 /milky allowlist add dm:123456，且运行条件满足
- **THEN** 插件 SHALL 将目标解释为指定私聊并执行管理流程
- **AND** SHALL 不另查来源或目标的管理员身份和 QQ 群角色

#### Scenario: core 允许普通用户使用 milky

- **WHEN** core 因普通用户命令许可允许调用者执行 milky，而调用者未命中管理员名单
- **THEN** 插件 SHALL 按同一 core 允许结果处理 list/add/del
- **AND** SHALL 不增设仅管理员可用的子命令门禁

#### Scenario: core 关闭 slash 权限门禁

- **WHEN** 对应作用域未配置管理员，core 按自身策略允许执行 milky
- **THEN** 插件 SHALL 遵从 core 的允许结果
- **AND** SHALL 不因缺少管理员配置拒绝白名单操作

#### Scenario: core 拒绝命令

- **WHEN** Hermes core 拒绝某来源的 milky 命令
- **THEN** 系统 SHALL 不执行管理 handler 的功能操作
- **AND** SHALL 不读取持久名单、不准备来源或目标群状态、不修改设置或运行规则

#### Scenario: 无法确定操作对象

- **WHEN** 管理调用缺少可信当前会话、profile 或唯一活动实例，或只能取得环境回退及过期上下文
- **THEN** 插件 SHALL 返回 unsupported，不执行管理读写
- **AND** SHALL 不选择默认 profile 或借用最近一次来源；该结果 SHALL 表示缺少执行上下文而非权限拒绝

### Requirement: 管理入口只豁免来源白名单匹配

规范的直接白名单管理指令 SHALL 能从未放行会话进入 Hermes core 命令分发，包括有效白名单为空的情况；路由资格 MUST NOT 依赖插件对发送者角色或命令权限的判断。canonical、自身消息拒绝、去重、同一 chat 的入站顺序和群禁言约束 MUST 保留。管理来源群状态 SHALL 在 core 放行和参数校验后、名单读写及目标准备之前检查；未跟踪时 SHALL 按需准备，准备成功且禁言条件允许后才执行管理操作。此检查 SHALL 不作为进入 core 授权入口的前置条件。准备 MUST NOT 自动放行来源群。已确认禁言或准备失败时 MUST 停止管理操作，不能先更改设置再尝试回复。

路由例外 MUST 只匹配规范化的直接 /milky allowlist 指令及固定子命令；其他子命令、普通正文、结构化 mention/图片消息、从其他命令展开的别名或未知子命令不获得此路由例外。已通过普通会话 Gate 的 slash 指令及别名 SHALL 继续交由 core 处理，插件不增设权限限制。管理命令 SHALL 不进入资源补全、Will、wait buffer 或普通 Agent turn。

#### Scenario: 从关闭的群启用自己

- **WHEN** 群未获准入站，调用者发送 /milky allowlist add，core 允许且后续群状态检查通过
- **THEN** 系统 SHALL 接受当前群为目标并执行一次管理流程
- **AND** 提交之前的普通消息 SHALL 不因发送者身份而被放行

#### Scenario: 路由例外不等于权限许可

- **WHEN** 白名单外调用者发送规范管理指令，但 core 拒绝，或发送其他命令
- **THEN** 前者 SHALL 由 core 拒绝且不执行管理操作，后者 SHALL 继续按普通会话白名单处理
- **AND** SHALL 不因此发起群状态准备、设置写入或普通 Agent turn

#### Scenario: 关闭群仍处于禁言

- **WHEN** core 已允许未放行群中的管理调用，但 Bot 已确认禁言或后续成员查询失败
- **THEN** 系统 SHALL 不执行名单读写及目标准备，不绕过发送禁言
- **AND** 调用者仍可从另一个由 core 允许且运行条件满足的来源管理该目标

### Requirement: 缺省目标与显式规则具有确定语义

add/del 省略目标时 MUST 使用可信来源的完整当前 chat key；群内发送者 QQ 号不得替代当前群号。显式参数 SHALL 接受一个合法 group:<十进制群号>、dm:<十进制 QQ 号>、group:* 或 dm:* 规则。裸数字、temp、未知命名空间、多余参数、畸形通配符 MUST 在网络及持久化前拒绝，不回退当前会话。list SHALL 不接受目标参数。

add SHALL 仅将指定字面规则加入集合；del SHALL 仅将指定字面规则从集合删除。具体规则与通配符 SHALL 作为独立条目处理，不按覆盖关系合并、展开或联动增减，不生成隐藏拒绝项。已有通配符 SHALL 不妨碍添加尚不存在的具体条目；添加或删除通配符 SHALL 保留其他具体条目。仅当添加的字面条目已存在或删除的字面条目不存在时 SHALL 返回 unchanged，不制造写入。增减回执 SHALL 只报告条目操作结果，不附带覆盖关系判断，不将删除条目表述为会话已关闭。删除最后一项 MUST 保存空列表并阻止全部普通入站。

#### Scenario: 省略群和私聊目标

- **WHEN** 调用者分别在 group:123456 和 dm:654321 发送无目标的 add/del
- **THEN** 目标 SHALL 分别为 group:123456 和 dm:654321
- **AND** SHALL 不把群内调用者 QQ 当作私聊目标

#### Scenario: 非法显式目标

- **WHEN** 指令为 /milky allowlist add 123456 或包含 temp、多个目标或非法通配符
- **THEN** 系统 SHALL 返回 invalid_input，不读写设置或准备群状态
- **AND** SHALL 不按缺省目标执行

#### Scenario: 已有通配符时添加具体条目

- **WHEN** 列表仅含 dm:*，调用者添加 dm:123
- **THEN** 候选集合 SHALL 包含 dm:* 和 dm:123
- **AND** SHALL 不因通配符覆盖该会话而返回 unchanged

#### Scenario: 添加通配符保留具体条目

- **WHEN** 列表包含 dm:123 和 dm:456，调用者添加 dm:*
- **THEN** 候选集合 SHALL 同时包含 dm:123、dm:456 和 dm:*
- **AND** SHALL 不合并或删除已有具体条目

#### Scenario: 删除具体条目保留通配符

- **WHEN** 列表包含 dm:* 和 dm:123，调用者移除 dm:123
- **THEN** 候选集合 SHALL 仅保留 dm:*
- **AND** 回执 SHALL 报告 dm:123 条目已删除，不附带覆盖关系判断

#### Scenario: 删除通配符保留具体条目

- **WHEN** 列表包含 dm:* 和 dm:123，调用者移除 dm:*
- **THEN** 候选集合 SHALL 仅保留 dm:123
- **AND** SHALL 不展开通配符或联动删除具体条目

#### Scenario: 字面条目决定重复操作

- **WHEN** 列表仅含 dm:*，调用者移除 dm:123 或再次添加 dm:*
- **THEN** 系统 SHALL 返回 unchanged，保留 dm:* 且不写入
- **AND** SHALL 不因 dm:123 被通配符覆盖而删除 dm:* 或新增黑名单

#### Scenario: 移除通配符和最后一项

- **WHEN** 调用者移除 group:*，或删除列表最后一项
- **THEN** 前者 SHALL 保留其他明确规则，后者 SHALL 得到空列表并阻止全部普通入站
- **AND** 白名单管理入口 SHALL 仍可到达 core，由 core 决定命令权限

#### Scenario: 删除别名与主指令等价

- **WHEN** core 允许的调用者在相同初始规则和运行条件下分别使用 del 或 remove，目标为省略、具体条目或命名空间通配符
- **THEN** 两种拼写 SHALL 得到相同目标、候选规则、持久化和运行结果及回执分类，单次调用只执行一次删除
- **AND** 白名单外的两种直接指令 SHALL 同样进入 core 分发；删除不存在条目均返回 unchanged，非法参数均拒绝且不产生操作

### Requirement: 指令持久化与运行生效分别核验

管理修改 MUST 使用当前 profile 的宿主设置机制，仅修改 plugins.entries.hermes-plugin-milky.settings.allowed_chats，不改环境文件、凭证或其他设置，不建立第二份持久化名单。候选 SHALL 基于当前 profile 最新有效配置计算；纯环境部署首次实际修改 SHALL 保存为更高优先级 settings。空 settings 列表 MUST 遮蔽低优先级环境授权。

同一活动实例的修改 SHALL 串行提交，新增授权群状态准备成功后才能持久化；保存前检查版本、托管限制和实例生命周期，保存后读回核验，确认持久化后才发布完整运行快照。无法确认唯一实例或 profile 时 MUST 在写入前返回 unsupported。保存失败或已发现竞争时 SHALL 不发布本次候选；保存已确认但发布失败 SHALL 分别报告 saved 与未应用。未知保存结果 SHALL 明示 unknown，不自动重试或盲目回滚。宿主无跨入口条件事务时 MUST 明示无法保证与人工/Web 并发完全原子。

#### Scenario: 从环境迁移到设置

- **WHEN** 当前白名单来自环境，调用者成功添加规则
- **THEN** 完整候选 SHALL 保存到当前 profile 的 settings 并在核验后在线应用
- **AND** 重启 SHALL 读取该设置，旧环境值保持原样且不覆盖设置

#### Scenario: 托管或准备失败

- **WHEN** 宿主禁止写入，或新增群状态准备失败
- **THEN** 系统 SHALL 返回 blocked 或明确准备失败状态，保持原名单
- **AND** SHALL 不报告 saved 或 applied

#### Scenario: 并发指令与 Web 竞争

- **WHEN** 两个调用者同时修改同一 profile，或 Web 在候选计算期间修改设置
- **THEN** 实例内命令 SHALL 串行基于最新设置计算；发现外部版本或读回冲突时 SHALL 返回 conflict
- **AND** SHALL 不自动覆盖重试、不承诺宿主未提供的跨入口事务

#### Scenario: 持久化后停止

- **WHEN** 保存已核验，但实例在发布运行快照前停止
- **THEN** 系统 SHALL 保留已保存设置并标明运行状态未应用或 unknown
- **AND** 后续连接 SHALL 恢复当前 profile 持久化设置，不使用旧注册快照覆盖新名单

### Requirement: 在线生效有明确的提交与撤销边界

系统 SHALL 在持久化核验及状态准备完成后发布完整有效策略版本。成功回执后的新消息 MUST 使用该版本或更新版本；命令接收和完成之间的消息 SHALL 以实际授权检查时的版本判断，不承诺命令一到就生效。

失去授权的会话 SHALL 清除插件尚未交接的等待消息、待附加系统上下文和 Will 累计状态；已分离但尚未交给 Hermes 的普通批次 MUST 在交接前检查授权是否曾被撤销，重新添加也不得复活旧批次。已交给 Hermes 的任务和历史 SHALL 不被撤销或删除。删除规则不限制出站工具、cron 或 home-channel 权限，不提前丢弃这些路径仍需要的群禁言状态。

#### Scenario: 删除后收到新消息

- **WHEN** del 已成功应用且会话不再匹配任何规则，随后收到普通消息
- **THEN** 消息 SHALL 被拒绝且不累计 Will 或缓冲
- **AND** 合法白名单管理命令 SHALL 仍按管理入口处理

#### Scenario: 撤销时仍在补全资源

- **WHEN** 某批次尚在插件内处理，所属会话失去授权后又被重新加入
- **THEN** 旧批次 SHALL 不再交给 Hermes，旧等待正文 SHALL 不在新消息中重新出现
- **AND** 已被 Hermes 接受的任务 SHALL 保持宿主原有生命周期

### Requirement: 管理回执区分规则和真实运行状态

list SHALL 稳定排序并分页返回当前 profile 的持久有效规则、配置来源、运行规则及二者是否一致；默认第一页，每页最多 50 条，可用 /milky allowlist list --page <正整数> 查询后续页。空列表 SHALL 明示全部普通入站阻止。反馈 SHALL 只发回原命令来源，不广播其他群。

add/del 回执 MUST 区分 saved、applied、unchanged、blocked、conflict、unsupported、invalid_input 和 unknown 等实际结果；目标群已授权但确认禁言时 SHALL 说明仍受禁言限制。回执发送失败 SHALL 不回滚配置、不重新执行修改或自动重发。诊断只保留操作、固定分类、版本或受限计数，不记录命令正文、完整列表、凭证、路径或底层异常正文。

#### Scenario: 持久值与在线值不同

- **WHEN** Web 已保存新白名单但实例尚未重新加载，调用者执行 list
- **THEN** 列表 SHALL 区分持久配置与运行策略，说明需要重新加载
- **AND** list SHALL 不隐式应用新配置或查询所有群状态

#### Scenario: 分页读取与回执失败

- **WHEN** 列表超过 50 条，或成功提交后的 QQ 回执发送失败
- **THEN** 前者 SHALL 返回有限页并提示后续页，后者 SHALL 保留提交结果
- **AND** SHALL 不无限发送列表或因回执失败重放修改
