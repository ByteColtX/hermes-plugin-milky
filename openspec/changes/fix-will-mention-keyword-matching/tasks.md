# Tasks

## 1. 关键词边界

- [x] 1.1 规范化只提取顶层连续 text/markdown，非文本隔断；通过规范化测试验证展示正文、独立提及信号和空区间。
- [x] 1.2 routing、forceKeywords、interestKeywords 共用区间匹配；通过合成事件验证名称、QQ 号、全体提及不触发或提高倍率，手输文本与相邻文本仍命中。
- [x] 1.3 验证 self mention 的路由、force 和 mentionGain 保持原语义，且非文本两侧不拼造关键词；通过明确增益数值和策略断言验证。

## 2. 交付验证

- [x] 2.1 更新 README 的三类关键词匹配边界，核对配置字段和默认值未变，并将本地验证证据记录在 evidence.md。
- [x] 2.2 运行相关测试、全量测试、ruff、diff 检查和 OpenSpec 严格校验，记录 skip 与真实集成未验证边界。
