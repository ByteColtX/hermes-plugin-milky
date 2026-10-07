# Spec Delta

## ADDED Requirements

### Requirement: 托管凭证写入拒绝可安全识别

当 Hermes 明确拒绝修改托管 `.env` 凭证时，Milky Dashboard MUST 返回 `blocked`，不得将已知拒绝降级为 `unknown` 或 `saved`。响应 MUST 不包含拒绝异常正文、凭证值或托管文件路径；无法确认写入结果时仍 MUST 返回 `unknown`。

#### Scenario: 替换凭证被托管策略拒绝

- **WHEN** 操作者替换 access token，但 Hermes 拒绝写入托管 `.env`
- **THEN** API 和配置页 SHALL 显示 `blocked`
- **AND** SHALL 不回显 token、拒绝异常正文或路径
- **AND** SHALL 不报告凭证已保存或运行配置已应用

#### Scenario: 清除凭证被托管策略拒绝

- **WHEN** 操作者清除 access token，但 Hermes 拒绝删除托管 `.env` 值
- **THEN** API SHALL 返回 `blocked` 并保留当前凭证存在状态
- **AND** SHALL 不报告成功清除或运行配置已应用

#### Scenario: 写入后结果无法确认

- **WHEN** 凭证操作发生非明确拒绝且持久化结果无法核验
- **THEN** API SHALL 返回 `unknown`
- **AND** SHALL 不伪造 blocked、saved 或运行态已应用结果

### Requirement: plugin-host Dashboard API 按请求 profile 隔离

当 Hermes 在 `plugins.isolation: host` 下代理 Milky Dashboard HTTP API 时，每个请求 MUST 在该请求指定且由宿主确认的 profile 中解析插件启用状态、配置、凭证、图库和任务。代理不得回退到启动 profile；请求与响应遵循当前非流式 HTTP 接口，插件业务层继续执行既有文件数、字节数和暂存配额限制。

#### Scenario: 请求切换到另一个已启用 profile

- **WHEN** Dashboard 请求显式选择 profile B，而插件 API 路由最初由 profile A 挂载
- **THEN** 该请求 SHALL 只读取或修改 profile B 的配置、凭证、图库或任务
- **AND** SHALL 不读取或改变 profile A 的对应数据

#### Scenario: 请求 profile 未启用插件

- **WHEN** 请求指向宿主确认但未启用 Milky 的 profile
- **THEN** API SHALL 拒绝请求并返回 not-found 或 disabled 分类
- **AND** SHALL 不回退至启动 profile

#### Scenario: 隔离宿主代理上传批次

- **WHEN** profile-scoped plugin-host API 接收处于现有单文件及批次上限内的合法上传，或接收超过上限的内容
- **THEN** 合法内容 SHALL 保持现有批次和 profile 归属
- **AND** 超限内容 SHALL 在视觉分析和图库入库前被拒绝
- **AND** 两种结果 SHALL 不跨 profile 访问暂存文件
