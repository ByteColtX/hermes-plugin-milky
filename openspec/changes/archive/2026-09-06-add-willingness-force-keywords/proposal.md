## Why

当前 `willingness.keywords` 同时使用了过于宽泛的名称，但它实际只用于命中后的增益倍率；
新增“包含即触发”后继续沿用这个名称会让两种完全不同的行为难以区分。需要通过明确的
配置字段拆分兴趣加分和强制触发，同时保持 Will 只消费规范化后的安全正文。

## What Changes

- **BREAKING** 将 `willingness.keywords` 重命名为 `willingness.interestKeywords`；该字段
  命中后使用 `keywordMultiplier`，不直接返回 `trigger`。
- 新增 `willingness.forceKeywords` 字符串数组；规范化正文包含任意一项时直接返回
  `trigger`，跳过 willingness 概率抽样。
- `interestKeywords` 和 `forceKeywords` 省略或为空时分别关闭对应行为；两者均只接受
  非空字符串数组。
- `forceKeywords` 命中不额外增加 willingness 分数；若同一消息同时命中
  `interestKeywords`，仍按既有规则使用 `keywordMultiplier`，并由强制命中决定最终触发。
- 旧 `willingness.keywords` 不保留兼容别名，启动配置应明确拒绝，避免部署者误以为旧语义
  仍然有效。
- 不改变 `routing.keywords` 的字段名和确定性 routing 语义，也不改变 Gate、temp、命令、
  系统事件、reply cost 或 routing engine 的边界。

## Capabilities

### New Capabilities

无。该 change 扩展已有 Will 配置和 willingness capability。

### Modified Capabilities

- `configuration`: 更新 `willingness` 字段集合、默认值、数组校验和旧字段拒绝行为。
- `will-willingness`: 区分兴趣关键词的增益倍率语义与强制关键词的确定性 trigger 语义。

## Impact

- 影响 `config/__init__.py` 的 Will policy 默认值和配置解析、`will/willingness.py` 的配置
  与决策，以及相关单元测试、README 和 `ARCHITECTURE.md`。
- 影响 `MILKY_WILL_POLICY.willingness` 的公开 JSON schema；使用旧 `keywords` 的部署配置
  需要迁移到 `interestKeywords`。
- 不新增网络请求、Milky Action、Hermes API、持久化状态或第三方依赖。
