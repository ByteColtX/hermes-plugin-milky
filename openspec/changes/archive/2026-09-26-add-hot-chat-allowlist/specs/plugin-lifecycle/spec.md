# Spec Delta

## MODIFIED Requirements

### Requirement: 冷启动身份和群禁言扫描结果可观测

冷启动完成登录信息读取后 MUST 使用 `event=milky.lifecycle` 记录 ready 所需的必要身份关联
信息；已登记的 `uid` 和被记录的群 ID 可以原样保留，但昵称不作为常规运维字段。群禁言扫描
MUST 使用日志给出 `total`、`succeeded`、`failed`、`muted`、`unmuted` 和 `unknown` 汇总计数；
未禁言、全体禁言未知和查询失败的群不得逐群打印，除非 DEBUG 诊断确实需要安全的状态变更。
扫描日志的 scope SHALL 在空规则时为 none，非空规则时为 allowlist（包括显式 group:* 与仅 dm 规则）；空规则不得记录 all_groups。扫描 SHALL 只处理有效入站白名单中具体群或 `group:*` 所匹配的群；白名单为空时不查询群成员状态，
`dm:<id>` 不得触发群禁言扫描。动态身份、状态和统计值 SHALL 只出现一次，不得写入原始异常或正文。

#### Scenario: 冷启动打印身份和扫描结果

- **WHEN** 登录身份和群列表同步成功，且白名单包含一个群会话和一个私聊会话
- **THEN** 日志 SHALL 记录 ready、必要的 uid 和确认禁言群状态，以及 `total`、`succeeded`、`failed`、`muted`、`unmuted` 和 `unknown` 汇总
- **AND** 无法通过 Milky 初始 Action 确认的 whole 状态 SHALL 计入汇总的 `unknown`
- **AND** SHALL 不记录 nickname、响应正文、请求 body 或未确认的群状态

#### Scenario: 空白名单保持全群语义

本场景沿用既有标识以便规范迁移；原有全群扫描结果由本 BREAKING 变更替换为零成员扫描。

- **WHEN** `MILKY_ALLOWED_CHATS` 为空且群列表返回多个群
- **THEN** 群禁言扫描 SHALL 不查询任何群成员
- **AND** 扫描汇总 SHALL 显示 scope=none 且 total、succeeded、failed、muted、unmuted、unknown 全部为零，登录和群列表成功后可启动管理入口

#### Scenario: 冷启动日志不重复身份和状态字段

- **WHEN** 冷启动需要显示 UID 或确认禁言群的 member/whole 状态
- **THEN** 每个值 SHALL 通过一个规范字段输出一次
- **AND** 日志 SHALL 不同时输出 `uid`/`self_id` 或 `group`/`group_id` 这类同义字段

## ADDED Requirements

### Requirement: 动态入站策略由活动实例拥有并从持久设置恢复

空白名单 SHALL 允许完成必要登录和群列表初始化，跳过零目标成员扫描后启动 SSE，以接收白名单管理指令并交由 core 决定权限；普通消息仍全部拒绝。活动实例 SHALL 拥有当前规则版本、管理提交和调用关联，注册阶段不得启动这些操作或写入配置。断开时 MUST 停止接收新的管理变更、失效调用关联并取消和等待所属任务，防止已停止实例发布策略或借用新实例身份。

完整断开后的再次连接或插件重新加载 MUST 按当前 profile 的配置来源重新读取白名单；仅 SSE 传输重连 SHALL 保留已发布策略和既有状态，不重做全部扫描。完整连接 SHALL 包括同一实例断开后重连与原注册工厂创建新实例后的首次连接，MUST NOT 依赖再次执行插件注册或强制插件发现。读取失败或白名单非法时 MUST 不进入 ready，不使用注册旧值继续接收；本读取 SHALL 仅更新白名单，其他配置仍遵守其现有快照生命周期。已经确认持久化的规则 SHALL 跨进程重启保留，未知提交或回执失败 SHALL 不自动重放。唯一活动实例或 profile 无法确认时 MUST 拒绝在线管理。

#### Scenario: 空名单启动后自助开启

- **WHEN** 白名单为空且登录、群列表初始化成功
- **THEN** 系统 SHALL 启动 SSE 并接受由 core 允许的管理指令
- **AND** SHALL 不因空名单停止插件，也不为所有群查询成员

#### Scenario: 停止与保存竞争

- **WHEN** 一个管理命令正在准备或保存时活动实例断开
- **THEN** 实例 SHALL 停止发布新策略并释放所属任务与调用关联
- **AND** 若已保存 SHALL 保留持久值并在后续完整连接时恢复，不报告当前实例已应用

#### Scenario: 完整连接与 SSE 重连

- **WHEN** 热修改后分别发生完整断开再连接，或仅 SSE 传输重连
- **THEN** 前者 SHALL 读取最新持久白名单，后者 SHALL 保留已发布运行策略
- **AND** SHALL 不恢复注册阶段的旧规则，不重放上次命令

#### Scenario: 一次注册后同实例完整重连

- **WHEN** 插件仅注册一次，当前 profile 的持久白名单已变化，同一实例完整断开后再次连接
- **THEN** 群扫描与入站 Gate SHALL 使用重新读取的规则，包含显式空列表覆盖旧非空值的情况
- **AND** SHALL 不要求再次注册，不影响其他配置快照

#### Scenario: 原注册工厂创建新实例

- **WHEN** 插件仅注册一次，持久白名单变化后由该次注册的工厂创建新 adapter 并连接
- **THEN** 新实例 SHALL 在扫描与接收前读取最新白名单
- **AND** SHALL 不使用原注册闭包捕获的旧白名单或依赖强制插件发现

#### Scenario: 完整连接读取失败

- **WHEN** 完整连接不能读取或校验当前 profile 的有效白名单
- **THEN** 系统 SHALL 不开放普通入站或 SSE，不报告 ready
- **AND** SHALL 不回退注册旧规则，不影响纯 SSE 重连保持现有策略的契约
