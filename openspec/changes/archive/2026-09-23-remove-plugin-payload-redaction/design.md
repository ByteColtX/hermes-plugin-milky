# Design

## Context

See proposal.md for the motivation. 当前同一份 Milky 协议对象会依次经过 parser、入站提取、normalizer 和 canonical；四处辅助函数同时负责递归冻结与按键名删除。Tool 结果还由既有独立 change 处理不透明交付。Hermes 的日志格式化器负责日志层脱敏，但 Tool 结果、模型上下文和会话存储的处理不应被假定为统一脱敏。

## Goals / Non-Goals

**Goals:**

- 将协议数据保真与秘密处理分开，保留已接收字段和值并继续提供不可变容器。
- 让 Tool、非 Tool Action 和入站 raw 对同一字段名遵循一致的保留规则。
- 保持现有协议校验、错误分类、未知 segment 降级、会话字段白名单和日志最小化。
- 与 preserve-milky-tool-results 的 Tool 透传边界衔接，避免两个变更互相覆盖。

**Non-Goals:**

- 不把原始 payload 写入日志、异常、smoke 输出或测试提交。
- 不把未知 segment 解释成正文、关键词、会话介绍、工具调用或授权信号。
- 不取消容器冻结、类型校验、Action 参数校验、认证、生命周期和副作用最多调用一次的限制。
- 不修改 Hermes core 或声称宿主会在所有出口自动清洗秘密。

## Decisions

### 1. 只移除通用键名过滤，保留冻结和解析校验

将四处递归辅助函数改为只做键和值的递归复制、不可变容器转换；不再根据统一敏感键集合删除字段。这样协议字段不会因命名碰撞消失，冻结语义也不受影响。备选方案是只修 parser 的 envelope 路径，但入站 extractor、normalizer 和 canonical 仍会继续丢字段，因此不采用。

### 2. 保持数据保真与业务解释边界分离

raw、extras 和未知 segment 可以保留任意字段，但正文、关键词、会话介绍和工具调用继续使用显式字段及白名单。备选方案是把所有 raw 交给正文或模型，这会扩大隐式指令和数据注入面，因此不采用。

### 3. 由输出出口负责最小化

日志继续只写固定分类、状态码、耗时、计数和必要关联 ID；本地错误继续映射为固定分类；配置摘要和 smoke 继续不输出凭证。插件不增加新的 payload 脱敏器。备选方案是保留黑名单并扩大词表，但无法可靠覆盖任意业务秘密，也继续破坏协议完整性。

### 4. 与 Tool 结果变更分阶段衔接

本 change 负责所有协议对象的通用字段保留；preserve-milky-tool-results 负责 Tool 在取得响应体后的透明交付和 HTTP/协议错误边界。实施时需要检查两者的 parser 调用关系和测试，避免一条路径透传、另一条路径仍过滤。

## Risks / Trade-offs

- [Risk] 凭证样式字段可能进入 raw、Tool 结果、session 或 core 落盘。→ 明确这是宿主内容策略的输入；插件继续禁止日志、异常、smoke 和测试资料复制原始 payload，并在文档中说明真实宿主出口需单独验证。
- [Risk] 旧调用方可能依赖字段被删除。→ 这是有意的 breaking change；用合成 fixture 覆盖字段保留，并更新受影响测试契约。
- [Risk] raw 保真可能增加对象大小。→ 继续沿用现有会话、事件和 Tool 结果容量边界；不新增无界缓存。
- [Risk] 现有“安全 raw”措辞会误导使用者。→ 更新主 spec、README 和 ARCHITECTURE，将“安全”改为“保真但不进入解释路径”，并区分日志安全。

## Migration Plan

1. 先为四处协议数据复制路径增加字段保留测试，确认冻结和类型校验仍在。
2. 移除四处通用敏感键过滤，并更新 parser、canonical、未知 segment 相关测试。
3. 复核 Tool 结果 change 的实现与测试，确保 Tool 和非 Tool 不再因同一键名产生分叉。
4. 更新 README、ARCHITECTURE 和主 spec 的 raw/脱敏责任表述。
5. 运行聚焦测试、完整质量门禁和 OpenSpec 严格校验；真实 Hermes/Milky 行为列为未验证边界。

## Open Questions

无。
