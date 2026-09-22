# Tasks

## 1. 协议数据复制边界

- [ ] 1.1 将 parser、inbound extractor、normalizer 和 canonical 的递归复制辅助函数改为只负责值复制与不可变容器转换，并验证不再按通用敏感键名删除字段
- [ ] 1.2 保持非 Tool Action 的 HTTP、envelope、必填字段和副作用结果校验，并用现有 client 测试验证 rejected、http_error、malformed 和 transport_unknown 分类未被改变
- [ ] 1.3 对 Tool 结果路径与 preserve-milky-tool-results change 做边界核对，验证同一响应字段不会在 Tool 与非 Tool 分支被不一致过滤

## 2. 入站 raw 与未知扩展

- [ ] 2.1 更新 parser、unknown segment、normalizer 和 canonical fixture，验证顶层、嵌套及大小写变体字段完整保留且冻结语义仍成立
- [ ] 2.2 更新 canonical 与 message-segments 测试，验证未知字段仍只进入 raw/metadata，不进入正文、关键词、会话介绍、工具调用或授权判断
- [ ] 2.3 更新相关主 spec、README 和 ARCHITECTURE 中“安全 raw/脱敏”的表述，明确协议保真与日志/输出最小化是两件事

## 3. 日志与宿主边界

- [ ] 3.1 审计 Action、Tool、入站、资源、出站、异常和 smoke 输出，验证它们只记录固定分类、状态码、耗时、计数和必要关联 ID，不复制响应或 raw
- [ ] 3.2 为含 token、authorization、password、cookie、完整 URL 和自由文本的合成响应补充日志回归测试，验证敏感内容不会进入插件日志或 smoke stdout
- [ ] 3.3 在文档中记录 Hermes logger、Tool 结果、模型上下文和 session 持久化的责任边界，并将真实 Hermes/Milky 集成验证标为待确认

## 4. 验证与交付

- [ ] 4.1 运行聚焦 parser、canonical、message-segments、client、Tool 和 observability 测试，确认字段保留与既有错误/日志契约
- [ ] 4.2 运行 uv 命令：pytest、ruff check、ruff format --check、build、git diff --check 和 openspec validate --changes --strict
- [ ] 4.3 使用 fake Hermes host、fake transport 和合成 fixture 记录证据；不把真实凭证、live 响应或真实媒体写入仓库，并注明真实宿主运行时仍未验证
