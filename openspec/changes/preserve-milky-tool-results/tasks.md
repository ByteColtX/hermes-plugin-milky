# Tasks

## 1. 建立 Tool 响应的不透明交付边界

- [ ] 1.1 在 Tool 调用入口建立独立于通用 Action 入口的响应路径：网络前保留参数、operationId 和 client 状态校验，网络后取得 transport 响应即交付，不调用 envelope 解析、敏感键脱敏、容器冻结、最小 `data` 校验或 HTTP/协议状态判断；移除 Tool 路径上的结果脱敏，但保留 parser 中的脱敏逻辑供入站事件和非 Tool Action 使用；用测试断言 Tool 路径不再触发 parser 的 envelope/DTO 函数，且登录、群列表、成员状态查询、发送和上传路径行为不变
- [ ] 1.2 用合成 fixture 验证交付内容与 transport body 一致：成功 envelope、`retcode` 非零、HTTP 4xx/5xx 及 HTML body、非 JSON 文本、JSON 数组、标量、显式 `null`、在顶层和嵌套对象中含 `access_token`、`authorization`、`cookie`、`password`、`token` 及其大小写变体的对象（验证脱敏已移除）、空 body、含非 UTF-8 字节的 body（替换字符解码）
- [ ] 1.3 保留参数非法 `invalid_input`、Tool 未注册和 client 未绑定/已关闭 `unsupported`、未取得响应体 `transport_unknown` 三类本地结果，删除 Tool 路径上的 `rejected`、`http_error`、`malformed` 分类；用 fake transport 验证副作用 Action 在每种情况下最多调用一次

## 2. 对齐 sender、Tool handler 和日志

- [ ] 2.1 更新 sender 中全部 25 个 Tool 包装方法，删除 `_action_success`、sender 侧 `_validate_tool_response` 和远端失败驱动的 MuteTracker 刷新调度；验证 nudge、撤回和群管理 Tool 在协议拒绝、HTTP 错误和 `transport_unknown` 时均不调度刷新
- [ ] 2.2 更新 Tool handler 的结果序列化，删除 envelope 重建和 `_json_value` 转换，直接交付 transport 解码后的字符串；验证 `get_forwarded_messages`、文件下载链接、好友请求、好友信息、群文件、群管理和专属头衔 Tool 的 fixture 逐字符一致
- [ ] 2.3 将 Tool 日志分类改为反映交付状态（已取得响应、`transport_unknown`、`invalid_input`、`unsupported`），协议拒绝和 HTTP 错误使用已取得响应分类并附状态码；断言日志记录不含响应体字段、参数、凭证、URL、路径或自由文本

## 3. 验证插件到 Hermes core 的交付边界

- [ ] 3.1 增加 fake Hermes host，在未注册任何 `transform_tool_result` 时调用至少一个查询 Tool 和一个状态变更 Tool，验证 host 收到的字符串与 transport body 内容一致，覆盖成功、协议拒绝、HTTP 500 和含 `token` 字段四种响应
- [ ] 3.2 断言插件 `register(ctx)` 未注册 `transform_tool_result` hook，且 Tool 路径不导入或调用 Hermes core 的结果变换、截断或落盘函数

## 4. 同步规格、文档和回归

- [ ] 4.1 创建 `milky-http-actions` 范围 delta（`openspec instructions specs --change preserve-milky-tool-results --json`），把“HTTP 和协议 envelope 错误必须分类”与“Action 数据满足最小结构才算成功”限定为非 Tool 路径，并运行 `openspec validate --changes --strict`
- [ ] 4.2 更新 `ARCHITECTURE.md` 中 Action 调用链、错误分类和集成说明，以及 `README.md` 中 Tool 结果分类描述，区分 Tool 路径原样交付与非 Tool 路径校验分类；在 README 明确记录 Tool 结果不再脱敏（列出此前被剔除的五类键名）并说明上下文策略由宿主负责；记录 Hermes core 的 `transform_tool_result`、`error` 字段截断和大结果落盘为插件之外的已知后置处理
- [ ] 4.3 更新现有 Tool 单元、集成和 fixture 断言，删除把远端拒绝/结构错误视为插件固定结果的旧预期；运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`git diff --check`，区分 fake host 通过与真实环境 skip
- [ ] 4.4 在交付 evidence 中记录原样交付边界、非 UTF-8 替换字符解码、core 后置处理不在契约内和未进行真实 Milky 副作用调用；确认改动不扩展 operationId、生命周期、资源下载或日志隐私范围
