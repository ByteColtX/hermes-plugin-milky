# Spec Delta

## ADDED Requirements

### Requirement: 群管角色状态和任务必须由连接生命周期拥有

导入和注册 MUST 仅登记群管配置、辅助模型能力和生命周期绑定，不联网、不打开案件存储或创建长期任务。启用群管的连接 MUST 在开放消息入口前完成既有必要同步，并从已确认的自身群成员信息建立管理身份状态；单群角色缺失为 unknown，该群处置保持 blocked，不伪造管理员身份。审核网络工作和 Action 执行任务 MUST 属于持有连接的运行实例，与普通聊天提交解耦。

断开、重载和卸载 MUST 停止新审核与动作派发，取消并等待自身任务，关闭临时上下文与持久存储连接，保留已提交案件和未到期的独立短期证据，清理过期证据；不得关闭其他实例资源。在途处置无法确认时 MUST 保持 unknown，重连不重放；同一 profile/Bot 多实例 MUST 排他领取执行权。

#### Scenario: 注册与启动同步

- **WHEN** 插件注册后尚未进入连接生命周期，或必要同步未完成
- **THEN** 群管 SHALL 不运行网络任务或消费消息，角色未知不能放行处置

#### Scenario: 停止时有模型和在途 Action

- **WHEN** 连接停止时存在待审核、模型请求或可能已发出的 Action
- **THEN** 系统 SHALL 取消并等待自身可取消工作，保留案件，可能已发送的动作标为 unknown 且不自动重发

#### Scenario: 重启与多实例

- **WHEN** Web 和 Gateway 不在同一进程，或两个 Gateway 同时观察批准案件
- **THEN** 已批准元数据 SHALL 跨进程可见，最多一个合法执行者开始具体动作，其余不得重发

### Requirement: Web 群管入口不得依赖活跃 QQ 会话

Web 群管读写 MUST 受现有宿主认证、profile 和插件启用边界保护，按自身生命周期拥有并关闭存储资源；不创建 QQ 会话、不建立 Milky 处置连接。Gateway 离线时可查看/拒绝案件，合法批准 SHALL 显示等待运行实例核验；不得显示已执行。所需辅助模型或宿主存储能力不可用时 MUST 明示 unsupported，不能改走主 Agent、独立 Web 服务或聊天授权。

#### Scenario: Gateway 离线期间审批

- **WHEN** 操作者在 Gateway 离线期间批准尚有效案件
- **THEN** Web SHALL 只持久保存批准，显示未执行；Gateway 恢复后必须再次验证身份、版本和时效
