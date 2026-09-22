# Proposal

## Why

插件当前在协议解析、入站规范化和 canonical 构建阶段，按通用键名递归删除 access_token、authorization、cookie、password、token。这会让合法业务字段在到达调用方前消失，同时又无法覆盖正文、URL 或其他命名的秘密。秘密处理应由宿主在日志、模型上下文和会话存储等具体出口按场景决定，协议插件应保留协议数据。

## What Changes

- **BREAKING** 移除插件对 Action envelope、事件、消息 segment、未知扩展、normalizer metadata 和 canonical raw/metadata 的通用敏感键过滤。
- 保留递归结构复制、容器不可变性、协议字段校验、错误分类和资源/消息边界；移除的是按键名删除数据的策略，不是所有数据校验或输出约束。
- 非 Tool Action 继续按既有协议契约判断 HTTP、envelope、必填字段和副作用结果；Tool 原样交付语义由现有 preserve-milky-tool-results change 继续覆盖，两个 change 的边界需要对齐。
- 入站 raw 和未知扩展保留远端字段，但未知内容仍不得进入正文、关键词、会话介绍或隐式工具调用。
- 日志、异常、配置摘要、smoke 输出、测试 fixture 和文档继续遵守既有最小化与合成数据边界；插件不新增日志脱敏器，也不把完整响应复制到日志。
- 明确记录 Hermes 对日志、Tool 结果、模型上下文和会话持久化的责任边界；不假设宿主会在所有出口自动清洗秘密。

## Capabilities

### New Capabilities

无。本 change 调整既有协议数据保真和责任边界。

### Modified Capabilities

- security-boundaries：协议数据不因通用敏感键名被插件删除；日志、异常、配置和测试资料继续受独立输出边界约束。
- canonical-messages：canonical raw 和未知扩展可保留完整协议字段，但仍不得把 raw 作为会话介绍或正文来源。
- message-segments：未知 segment 的 raw 保真与安全降级分离；保留类型、顺序和结构，不将未知内容变成正文或指令。
- milky-http-actions：Action envelope 的数据保留与 HTTP/协议成功判断解耦；非 Tool 校验继续有效，Tool 透传按已有关联 change 执行。
- adapter-observability：日志继续只记录选择后的低敏元数据；不依赖插件 payload 脱敏来保证日志安全。

## Impact

- 主要影响 milky/parser.py、inbound/extractor.py、inbound/normalizer.py 和 inbound/canonical.py 的数据冻结/复制辅助函数，以及相关测试和 fixture。
- 需要同步检查 outbound/tools.py、milky/client.py 与 preserve-milky-tool-results 的 Tool 结果边界，避免一个路径保留字段而另一个路径删除字段。
- 需要更新 README、ARCHITECTURE 和相关主 spec 中“raw 安全”的表述，并明确真实 Hermes host、日志配置和会话落盘仍需集成验证。
- 不修改 Hermes core，不新增网络访问、权限、Tool operationId、消息路由、资源下载或生命周期行为。
