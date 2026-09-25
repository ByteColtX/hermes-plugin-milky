# Spec Delta

## MODIFIED Requirements

### Requirement: 配置页展示有效配置与保存状态

页面 SHALL 提供当前正式配置的结构化编辑、Will 的分组编辑与高级 JSON 视图，二者使用相同候选校验；不得丢弃当前未展开的合法字段。读取 SHALL 区分显式设置、有效值、来源、默认值和可写状态；凭证只展示存在状态。空白名单 SHALL 明示阻止全部普通入站会话，白名单管理命令仍可交给 Hermes core，core 允许的调用者可使用；不得将其解释为关闭插件或 SSE。全部放行 SHALL 提示显式使用 `group:*` 和 `dm:*`。保存 SHALL 遵守 configuration 规范并仅提交用户修改的键；错误反馈包含字段与安全分类，不回显凭证或原始异常。新保存配置 SHALL 展示待重新加载；只有宿主已确认运行实例使用该配置时才可显示已应用，未知运行态 SHALL 明确展示 unknown。

#### Scenario: 修改 Will 后切换编辑方式

- **WHEN** 用户在结构化表单与高级 JSON 之间切换并保存合法策略
- **THEN** 两种视图 SHALL 表示同一候选策略且保留未修改字段
- **AND** 非法字段 SHALL 定位到配置项，在持久化前拒绝

#### Scenario: 首次安装或配置损坏

- **WHEN** QQ 平台尚未能正常启动
- **THEN** 页面 SHALL 能显示配置缺失或错误并允许修正
- **AND** SHALL 不因为页面可访问而宣称 QQ 已连接

#### Scenario: 展示命令保存的白名单

- **WHEN** core 允许的调用者通过 QQ 指令保存白名单，随后刷新同一 profile 的配置页
- **THEN** 页面 SHALL 读取同一持久化设置，空列表显示全部普通入站已配置为阻止
- **AND** 页面无法确认在线版本时 SHALL 保持 unknown，不能因持久化成功宣称在线实例已应用

#### Scenario: Web 单独保存仍需加载

- **WHEN** 操作者在配置页修改白名单并保存
- **THEN** 页面 SHALL 按既有契约显示待重新加载
- **AND** SHALL 不声称本 change 提供跨进程实时推送
