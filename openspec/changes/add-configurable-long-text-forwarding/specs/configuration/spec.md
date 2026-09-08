## ADDED Requirements

### Requirement: 超长文本合并转发阈值配置可验证

启动配置 MUST 解析可选的 `MILKY_LONG_TEXT_FORWARD_THRESHOLD`。未配置时值 MUST 为 `0`；值 MUST 是十进制整数且范围为 `0` 至 `4096`（含边界）。值为 `0` 时 MUST 禁用超长文本合并转发；正值 MUST 表示当一次出站文本的可见规范化长度超过该阈值时选择合并转发。配置 MUST 在启动时一次性解析并保存在运行时配置中，且 MUST 出现在配置文档和不含凭证的配置摘要中。

#### Scenario: 未配置时保持普通分块

- **WHEN** `MILKY_LONG_TEXT_FORWARD_THRESHOLD` 未配置
- **THEN** 配置值 SHALL 为 `0`
- **AND** 超长文本 SHALL 继续使用普通文本分块出站

#### Scenario: 零值显式禁用

- **WHEN** `MILKY_LONG_TEXT_FORWARD_THRESHOLD` 配置为 `0`
- **THEN** 启动 SHALL 成功
- **AND** 任意长度的文本 SHALL 不选择合并转发路径

#### Scenario: 正值启用阈值

- **WHEN** `MILKY_LONG_TEXT_FORWARD_THRESHOLD` 配置为 `300`
- **THEN** 启动 SHALL 保存数值 `300`
- **AND** 只有一次出站文本的可见规范化长度大于 `300` 时才允许选择合并转发

#### Scenario: 范围边界值

- **WHEN** 配置值分别为 `1` 或 `4096`
- **THEN** 启动 SHALL 接受对应配置
- **AND** `1` SHALL 表示大于 1 个字符时可选择合并转发，`4096` SHALL 表示大于 4096 个字符时可选择合并转发

#### Scenario: 非法阈值拒绝启动

- **WHEN** 配置为空、不是十进制整数、为负数或大于 `4096`
- **THEN** 启动 SHALL 返回配置错误
- **AND** SHALL 不建立 Milky 网络连接、不读取本地媒体且不创建出站目标
