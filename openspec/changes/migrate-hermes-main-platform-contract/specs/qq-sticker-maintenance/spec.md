# Spec Delta

## ADDED Requirements

### Requirement: 贴纸视觉维护使用目标 Hermes profile-local 视觉能力

贴纸维护的图像分析 MUST 使用目标 Hermes 当前支持的视觉入口，并沿调用所属的 profile scope 读取视觉配置及缓存。插件 MUST 将受控图库中的本地候选交给该入口，不得复制 Hermes 下载、路径验证、缓存或 profile routing 逻辑。视觉能力不可用、超限或结果不完整时 SHALL 按现有安全错误分类处理，不得创建成功条目或暴露异常正文。

#### Scenario: 在当前 profile 分析受控候选

- **WHEN** profile B 的贴纸维护任务提交一个经过插件校验的本地图片候选进行分析
- **THEN** 视觉入口 SHALL 在 profile B 的宿主作用域运行
- **AND** SHALL 不读取 profile A 的视觉配置、缓存或凭证
- **AND** 图库提交 SHALL 仍由插件自己的校验和事务边界决定

#### Scenario: 目标视觉能力拒绝或不可用

- **WHEN** Hermes 视觉能力缺失、拒绝输入或返回无法解析的结果
- **THEN** 维护操作 SHALL 保留现有的 visual-unavailable、malformed 或 storage 分类
- **AND** SHALL 不报告视觉分析成功或写入伪造元数据
- **AND** SHALL 不将路径、异常正文或分析原文写入日志/API
