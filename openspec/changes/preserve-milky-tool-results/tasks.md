# Tasks

## 1. 建立插件 raw passthrough 边界

- [ ] 1.1 梳理所有已注册 Milky Tool 的响应路径，区分网络前参数/可用性校验与网络后响应交付，并保留入站事件解析；通过代码审查确认 Tool 响应路径不再依赖业务 envelope、最小 data 或 DTO 校验
- [ ] 1.2 在 HTTP transport 到 Tool handler 的唯一交付边界保留已取得响应体的原始内容，禁止敏感键过滤、数组容器转换、响应遍历、JSON 重建和 envelope 摘要；用合成 object、array、scalar、显式 `null`、未知字段及 `token`/`authorization` 字段 fixture 验证内容一致
- [ ] 1.3 保留参数非法、Tool 未注册、client 未绑定/已关闭和未取得响应体时的固定分类，并确保可能产生副作用的 Action 只提交一次且不重试；运行对应单元测试并检查 fake transport 的调用次数

## 2. 对齐各类 QQ Tool 和日志行为

- [ ] 2.1 更新查询类 Tool，使成功、协议拒绝、非成功 HTTP 状态、非预期 JSON 形状和未知 envelope 均返回原始响应体；验证 `get_forwarded_messages`、文件下载链接、好友请求、好友信息和群文件 Tool 的 fixture 均未丢字段
- [ ] 2.2 更新状态变更类 Tool，使取得响应体时不替换为 `rejected`、`http_error` 或 `malformed`，无响应体时仍为 `transport_unknown`，并保持显式调用、目标绑定和单次副作用边界；运行好友/群请求、群邀请和专属头衔的 fake transport 测试
- [ ] 2.3 保持 Tool 日志只含名称、低基数分类、已知状态码、耗时和必要关联 ID，不读取或写入 raw body、参数、凭证、URL、路径或自由文本；运行日志断言并确认合成响应字段不出现在日志记录中

## 3. 验证 Hermes core 后置边界

- [ ] 3.1 增加 fake Hermes host，在未注册 `transform_tool_result` 时调用至少一个查询和一个状态变更 Tool，验证插件交付结果与 transport body 内容一致；验证插件没有注册、拦截或替换该 hook
- [ ] 3.2 增加带替换型 `transform_tool_result` 的 fake host，对同一 raw 结果验证替换只发生在插件交付之后，并将断言限定为记录 Hermes core 的后置行为，不把它写成插件 passthrough 失败；运行 fake host 集成测试
- [ ] 3.3 在兼容性检查中验证 Hermes core Tool registry 对超长 JSON `error` 字段的截断边界，并记录可用的 opt-out/版本要求；真实 Hermes 未提供该能力时将检查标记为 skip/blocked，不在插件中添加还原逻辑

## 4. 完成回归、文档和交付证据

- [ ] 4.1 更新现有 Milky Tool 单元、集成和 fixture 断言，删除把远端拒绝/结构错误视为插件固定结果的旧预期；运行 `uv run pytest -q` 并区分 fake host 通过、真实环境 skip 和外部阻塞
- [ ] 4.2 运行 `uv run ruff check .`、`uv run ruff format --check .`、`git diff --check` 和 `openspec validate --changes --strict`，修复所有格式、规范和 delta 完整性问题
- [ ] 4.3 在交付 evidence 中记录插件 raw passthrough、Hermes core transform/truncation 外部依赖和未进行真实 Milky 副作用调用的边界；确认改动不扩展 operationId、生命周期、资源下载或日志隐私范围
