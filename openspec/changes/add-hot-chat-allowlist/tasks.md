# Tasks

## 1. 空白名单语义与运行策略

- [ ] 1.1 统一配置来源中的空值、缺省值和原生空列表为全部普通入站拒绝，保留具体规则/命名空间通配符及高优先级空列表遮蔽；通过配置与 Gate 聚焦测试验证 group/dm、同号隔离和非法规则网络前失败。
- [ ] 1.2 建立活动实例拥有的运行策略版本与撤销代次，让入站和群扫描读取一致规则；通过新策略单元测试验证完整快照替换、实际授权缩小判断和重复集合操作。
- [ ] 1.3 更新 README 配置段、manifest 提示与 CHANGELOG 的 BREAKING 迁移说明，明确全部放行需两个通配符、旧版本回滚空列表会放大权限；核对文档示例与配置测试一致。

## 2. 管理指令与 core 分发

- [ ] 2.1 在 slash_commands.py 明确加入 allowlist 顶层分支并更新注册帮助，保留无参数 get_impl_info 与 sticker 分支；测试三路分发、非法 allowlist 不调用协议摘要或 sticker、旧未知参数仍拒绝。实现固定纯文本 list/add/del 语法并将 remove 归一化为 del 的等价别名；帮助优先展示 del 并注明 remove，测试两种拼写在白名单内外、默认目标、显式/通配符目标、非法参数和 unchanged 时完全一致且单次调用只执行一次删除。实现、默认当前会话、单一显式规则与分页参数；用命令测试验证 group/dm 缺省目标、裸 ID/temp/多参数拒绝、字面条目重复操作 unchanged、已有通配符时仍可添加具体条目、添加/删除通配符保留具体条目、删除具体条目保留通配符，以及回执仅报告条目操作结果。
- [ ] 2.2 让所有 slash 权限完全由 core 分发处理，不实现插件额外的管理员/角色/子命令门禁；用宿主契约测试验证 core 允许普通用户 milky、无管理员关闭门禁、按作用域限制与拒绝等结果原样生效，core 拒绝时无管理读写和状态查询，插件不解析或复制权限配置。
- [ ] 2.3 通过既有宿主分发获取可信当前会话、profile 与唯一活动实例，必要时携带仅用于操作对象和生命周期的调用关联，不建立授权凭据；通过真实本地 Hermes 分发的无网络契约测试验证可达及 core 允许的别名正常执行，覆盖缺失上下文、环境回退、过期关联和多 profile/实例时准确返回 unsupported。
- [ ] 2.4 接入只按语法识别的白名单外管理路由，保留 canonical、自身消息、去重和其他命令的会话 Gate；将管理来源群状态检查移至 core 放行后、名单读写前。验证不同角色均可到 core、core 拒绝无管理操作、来源禁言不执行功能操作、普通消息/其他命令仍按原会话 Gate、命令不进入 Will/资源/Agent。
- [ ] 2.5 更新 README 指令示例与权限说明，包括全部 slash 权限归 core、顶层 milky 许可覆盖 allowlist、普通用户命令白名单示例不包含 milky、省略目标、管理范围、纯文本限制、list 分页和上下文能力缺失 unsupported；逐项核对命令 fixture 与文档。

## 3. 群状态准备与初始化

- [ ] 3.1 修改 state/mute_tracker.py 的 _select_group_ids 空分支为零目标，并同步初始化 scan_scope：空规则 scope=none，非空规则保留 scope=allowlist（含 group:* 与仅 dm）；更新 tests/test_mute_tracker.py 的旧 all_groups 日志断言，验证空名单零请求、所有计数为零、可 ready 且普通消息拒绝，显式 group:* 保留全群及并行初始同步。
- [ ] 3.2 在 state/mute_tracker.py 增加独立受控的未跟踪群准备入口，保留 refresh_group 只刷新已跟踪群；core 允许且参数合法后，确认归属、以 unknown 纳入跟踪并查询成员状态，来源与目标复用。测试 refresh_group 对未知群仍返回 False、新入口准备成功、失败/取消保持拒绝且不提交、查询期间事件保留、冷却重试、非成员拒绝、目标禁言可保存、来源禁言不执行和 group:* 整体准备。
- [ ] 3.3 保持准备期间禁言事件、TTL、冷却与并发限制，不以陈旧查询覆盖新事件；用受控异步测试验证查询/事件交错、取消与重复请求，以及移除授权后管理回执和既有出站仍有禁言状态。
- [ ] 3.4 更新 ARCHITECTURE 的空名单初始化、动态群状态与资源所有权说明；对照测试记录确认不新增后台全量扫描、注册网络调用或重复连接任务。

## 4. 持久化与在线提交

- [ ] 4.1 将宿主设置的读取、统一校验、托管检查、单键保存和读回核验整理为 Web 与 QQ 可共享的无 HTTP 边界，保留原 Web 行为；通过设置测试验证仅改 allowed_chats、环境提升为 settings、高优先级空列表和 profile 隔离。
- [ ] 4.2 串行处理管理修改，基于最新有效设置准备候选，保存前检查版本/生命周期，核验持久化后发布完整策略；测试双管理员竞争、外部 Web 冲突、保存拒绝、读回未知、保存成功但发布失败，不自动重试/回滚。
- [ ] 4.3 实现持久/运行规则差异查询及准确状态回执，区分 unchanged 与 applied，无变化操作不隐式 reload；测试稳定分页、空值提示、持久/在线分叉和回执失败不重放修改。
- [ ] 4.4 更新 Dashboard 源码与随包资源的空值文案，保持 Web 保存待重新加载与 unknown 状态；运行 Dashboard 对应测试及既有前端构建/检查，确认 QQ 保存后刷新同一 profile 可读到设置。
- [ ] 4.5 更新持久化与并发文档，明确单键核验不等于跨入口条件事务、其他配置仍需加载；对照保存失败测试核验状态说明不报告假成功。

## 5. 撤销、停止与恢复

- [ ] 5.1 在实际撤销授权时清理插件未交接等待正文、系统上下文和 Will 状态，交接前检查撤销代次；用受控异步 pipeline 测试覆盖补全期间撤销、删除再添加、通配符仍覆盖时不误清理及已被 Hermes 接受任务不被取消。
- [ ] 5.2 停止时关闭管理接收、失效调用关联并取消等待所属任务；测试准备/保存/发布各阶段断开、多次 disconnect、重启恢复及旧实例不能发布。完整连接的读取路径和注册闭包修正必须完成 5.4，不能依赖再次 register。
- [ ] 5.3 更新 ARCHITECTURE 的提交边界、撤销和恢复说明，并核对尚未实现 add-idle-session-wakeup 的共享白名单依赖；交付依赖说明，不把未实施主动唤醒写成当前能力、不顺带实现该 change。

- [ ] 5.4 改造 __init__.py::register 与 adapter_factory，向 adapter 注入绑定当前 profile 的 allowed_chats 读取器，避免把捕获的 milky_config.allowed_chats 当作重连事实来源；adapter.py 的每次完整 connect 在群扫描/Gate/SSE 前重新读取并初始化共享规则，失败不 ready、不用旧值。扩展 tests/test_plugin_entry.py 与 tests/test_adapter_lifecycle.py：只 register 一次，变更持久设置后同实例 disconnect/connect、同一 factory 新实例首次 connect 均取得新名单；覆盖高优先级空列表、读取失败、profile 隔离、其他配置快照不变，纯 SSE 重连不重读，注册无网络/后台任务。

## 6. 集成验证与交付证据

- [ ] 6.1 运行跨模块聚焦测试：uv run pytest -q tests/test_config.py tests/test_gate_registry.py tests/test_slash_commands.py tests/test_hermes_pipeline.py tests/test_mute_tracker.py tests/test_adapter_lifecycle.py tests/test_plugin_entry.py tests/test_dashboard_settings.py，以及新增管理测试；记录通过、失败和 skip，确认权限拒绝/保存失败无非预期副作用。
- [ ] 6.2 完成质量门禁：uv run pytest -q、uv run ruff check .、uv run ruff format --check .、uv build、git diff --check、openspec validate --changes --strict；修复本 change 引入的问题并记录无关外部阻塞。
- [ ] 6.3 在明确获准的测试 profile/QQ 会话执行真实集成验收：空名单管理员启用当前群/私聊、成功回执后普通入站、指定目标增减、删除最后一项仍可管理、重启保留、Web 刷新与禁言拒绝；外部配置修改和发送须有明确授权，smoke 写模式遵守 --allow-write 及目标限制，缺少条件记录 blocked/skip。
- [ ] 6.4 在本 change 的 evidence.md 记录合成场景、命令、结果、宿主版本与源码证据、真实集成边界、并发限制及回滚步骤；区分静态、fake host、真实宿主分发和真实 Milky，不以 skip 视为已验证，并核对 proposal/specs/design/tasks 与实现文档一致。
