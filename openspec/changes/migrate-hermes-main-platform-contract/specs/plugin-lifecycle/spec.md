# Spec Delta

## ADDED Requirements

### Requirement: Milky platform requires in-process plugin isolation

Milky 的平台 adapter MUST 在 Hermes `plugins.isolation: in_process` 模式下注册和运行。`host` 模式不提供平台 adapter 所需的进程内 Gateway 对象；该模式下 Hermes MUST 明确报告平台能力 unsupported，且不得留下部分平台注册、连接或伪 ready 状态。

#### Scenario: 使用 plugin host 隔离启动平台插件

- **WHEN** 当前 profile 将第三方插件隔离设为 `host`
- **THEN** Hermes SHALL 报告 Milky 平台能力 unsupported 并保持未注册、未连接
- **AND** SHALL 不打开 Milky HTTP/SSE 或报告平台 ready

#### Scenario: 使用进程内模式启动平台插件

- **WHEN** 当前 profile 将第三方插件隔离设为 `in_process` 且目标 Hermes 注册契约可用
- **THEN** Milky SHALL 完成唯一平台注册并按既有生命周期等待连接初始化
- **AND** 普通消息入口 SHALL 仍遵守登录和初始状态同步门槛

### Requirement: Milky Gateway 平台 adapter 与 Agent client tools 分开注册

Gateway 为 Milky 会话准备 Agent toolset 时，Hermes MUST 注册 Milky manifest 声明的 outbound client tools。工具注册 SHALL 与平台 adapter 注册分开完成；adapter 尚未连接时，工具仍 SHALL 出现在 Milky Agent toolset。任一能力无法提供时 MUST 明确反映缺失，不得将 adapter 的 deferred 或连接状态当成工具不存在的依据。

#### Scenario: Gateway 为 Milky 会话准备 Agent 工具集

- **WHEN** Gateway 加载 Milky 插件并为 Milky 会话准备 Agent toolset
- **THEN** Milky 平台能力 SHALL 只注册一次
- **AND** manifest 声明的 client tools SHALL 在 Milky Agent toolset 中各注册一次
- **AND** 工具注册本身 SHALL 不发起 Milky HTTP 请求或 SSE 连接

### Requirement: 当前平台注册契约缺失时不部分启用

Milky MUST 使用目标 Hermes 文档化的平台注册能力。必需的平台或 prompt 注册能力缺失时，插件 MUST 在连接或启动长期任务前明确报告 unsupported；不得静默跳过必要注册后，仅留下工具、命令或 skills 并把插件报告为完整可用。

#### Scenario: 当前平台注册 API 缺失

- **WHEN** Hermes 上下文缺少 Milky 平台所需的注册能力
- **THEN** 插件 SHALL 明确报告 unsupported 并停止平台注册
- **AND** SHALL 不创建连接、SSE 或长期任务

#### Scenario: 当前注册契约完整

- **WHEN** Hermes 提供当前平台和 system prompt 注册能力
- **THEN** 插件 SHALL 完成平台注册与 Milky prompt section 登记
- **AND** 注册 SHALL 保持无网络、无 SSE 和无长期任务

### Requirement: 安装声明与目标 Hermes 依赖流程一致

Milky manifest MUST 继续声明原生平台插件类型，并声明与目标 Hermes 加载契约相符的最低版本和完整运行依赖。安装、更新或启用 SHALL 通过目标 Hermes 的依赖准备与环境发布流程；拒绝或准备失败时 SHALL 不导入为已启用插件，不得在 import/register 阶段自行安装或切换旧加载路径。最低版本声明只代表版本下限，不得宣称锁定某个 Hermes commit。

#### Scenario: 目标版本验证 manifest

- **WHEN** 目标 Hermes 校验 Milky manifest 与依赖声明
- **THEN** 插件 SHALL 被识别为原生 platform 插件
- **AND** 当前版本约束及运行依赖 SHALL 通过目标校验
- **AND** SHALL 不依靠旧 manifest alias 或旧插件依赖安装模块

#### Scenario: 依赖未获准或未能准备

- **WHEN** 安装/启用时用户未同意依赖准备，或目标依赖环境准备失败
- **THEN** 插件 SHALL 保持未启用或保留原有已发布环境
- **AND** SHALL 不加载一个依赖不满足却报告 ready 的 Milky platform

#### Scenario: Hermes 版本低于声明下限

- **WHEN** Hermes 版本低于 manifest 声明的最低版本
- **THEN** 加载 SHALL 在运行插件入口前拒绝
- **AND** 拒绝说明 SHALL 不声称相同版本号的旧 commit 一定兼容目标 API
