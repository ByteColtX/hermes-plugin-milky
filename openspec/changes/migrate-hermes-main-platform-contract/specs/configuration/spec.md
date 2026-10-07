# Spec Delta

## ADDED Requirements

### Requirement: Hermes 配置和 secret 绑定到当前平台 profile

插件从 Hermes 读取普通设置、兼容环境来源和 secret 时 MUST 使用当前注册或请求所属的 profile scope；不得从 Hermes 进程的 launch/default profile 环境回填另一个 profile 缺失的值。设置来源优先级和非法高优先级值的 fail-closed 语义 SHALL 沿用 configuration 主规范。插件数据目录和运行期配置快照 MUST 与同一 profile 归属。

#### Scenario: 次级 profile 缺少配置值

- **WHEN** Gateway 正在处理 profile B，而 profile B 未配置某个 Milky 字段、profile A 有同名环境值
- **THEN** profile B SHALL 按自身合法来源和默认值解析
- **AND** SHALL 不读取 profile A 的进程环境值
- **AND** 必需值缺失时 SHALL 以安全分类拒绝启动

#### Scenario: profile B 使用自身凭证和图库

- **WHEN** 两个 profile 分别配置 Milky token 和贴纸图库
- **THEN** profile B 的 adapter、命令和本地图库操作 SHALL 只使用 profile B 的凭证及数据根
- **AND** SHALL 不因进程共用或 adapter 替换访问 profile A 的数据

#### Scenario: 托管范围覆盖普通 profile 设置

- **WHEN** Hermes 对当前 profile 的配置键或 secret 有托管来源/写入限制
- **THEN** 插件 SHALL 保留宿主提供的有效值和拒绝结果
- **AND** SHALL 不通过 raw file write、进程环境回退或异常吞并绕过该限制
