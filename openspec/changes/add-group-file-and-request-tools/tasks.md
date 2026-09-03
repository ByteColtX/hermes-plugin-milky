## 1. 契约与脱敏 fixture

- [x] 1.1 建立 6 个新增 operationId 的合成 ToolSpec/schema fixture，覆盖必填字段、可选 nullable 字段、`notification_type` 枚举、序号和 QQ 号范围、空字符串与 `additionalProperties: false`，并用 fixture 测试验证不含凭证、真实身份、真实 URL 或路径
- [x] 1.2 建立 `get_group_file_download_url`、`get_group_files` 的成功 envelope，以及 4 个群请求/邀请处理 Action 的成功空对象、协议拒绝、HTTP 错误、非 JSON、malformed 和 `transport_unknown` fixture，并用协议测试验证最小 data 结构和未知字段保留
- [x] 1.3 建立文件 placeholder 的有效 `file_hash`、`null`、缺失和空值合成输入，验证期望格式为 `[file:file_id=<file_id>,file_name=<file_name>,file_hash=<file_hash>]` 且缺失值为 `NOT SUPPORTED`

## 2. 入站文件 placeholder

- [x] 2.1 让文件正文生成逻辑接收已规范化的 `file_hash` 并按固定字段顺序生成 placeholder，运行 normalizer 和上下文渲染测试验证不重新读取 raw、不联网且不改变文件引用分类
- [x] 2.2 增加带 hash、可空 hash 和不完整 file segment 的回归断言，验证 `file_attachment_references` 与正文 placeholder 使用同一协议字段且不会从正文反解析哈希

## 3. Milky client 与 sender 边界

- [x] 3.1 为 6 个 operationId 增加 client/sender 委托和显式 Action allowlist，复用统一 POST、Bearer、path prefix、envelope 与错误分类，并用 fake transport 验证每个请求只访问对应 `/api/{operationId}`
- [x] 3.2 实现新增工具的严格参数校验，覆盖 QQ ID、序号、文件 ID、通知类型、`parent_folder_id`、`is_filtered` 和 `reason` 的类型/范围/省略/null 行为，并用网络前置测试验证非法输入不触网
- [x] 3.3 增加查询结果的最小结构校验：下载链接要求字符串 `data.download_url`，群文件列表要求对象数组 `data.files` 与 `data.folders`，4 个管理 Action 要求成功 data 为空对象；用 fixture 测试验证未知字段仍保留
- [x] 3.4 验证 4 个接受/拒绝 Action 每次显式调用最多提交一次，协议拒绝返回 `rejected`，响应未知返回 `transport_unknown` 且不重试、不换目标、不更新本地群状态

## 4. ToolSpec 注册与显式调用边界

- [x] 4.1 增加 6 个 schema、异步 handler、工具注册和 manifest 清单，验证 23 个固定 ToolSpec 与既有工具共存、无重复、toolset 为 `milky` 且注册阶段无网络
- [x] 4.2 验证群请求、群邀请和群通知保持 observe-only，普通正文、关键词、Will 和入站事件均不自动调用接受/拒绝 Action；用 fake pipeline/SSE 调用记录断言零隐式副作用
- [x] 4.3 扩展 Tool 安全日志投影，保留必要业务 ID、数量、布尔值和错误分类，排除下载 URL、完整 `reason`、token、Authorization、路径、完整响应和异常正文，并用日志捕获测试验证

## 5. 文档、集成与质量门禁

- [x] 5.1 更新 `README.md`、`ARCHITECTURE.md`、`skills/qq-tools/SKILL.md` 和相关 OpenSpec 说明，明确 23 个固定工具、6 个新接口的参数、文件 placeholder 的 hash 规则及查询/状态变更边界，并用静态清单检查验证内容一致
- [x] 5.2 运行工具、client、sender、normalizer、上下文渲染、协议 fixture、注册和 fake Hermes pipeline 聚焦测试，记录失败分类并修复回归
- [x] 5.3 运行 `uv run pytest -q -rs`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check`，在本任务 evidence ledger 记录命令结果及 Hermes/Milky 基础设施 skip
- [x] 5.4 运行 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`，验证本 change 的 proposal、两个 delta spec、design 和 tasks 一致；未获明确授权时不执行真实群管理、真实文件下载链接或其他可能产生外部副作用的 smoke

## Evidence ledger

| 阶段 | 命令/证据 | 结果 | 反馈分类与下一步 |
|---|---|---|---|
| 规划 | 已读取项目基线、相关 active change、主 specs、本 change proposal/specs/design 和 Milky v1.3.0 OpenAPI MCP | 已完成 | 以 OpenAPI 确认的字段作为契约；实现阶段按 1→5 推进 |
| fixture/实现 | `uv run pytest -q tests/test_qq_tools.py tests/test_milky_client.py tests/test_normalizer.py tests/test_resources.py tests/test_inbound_context_rendering.py` | 168 passed；随后扩展回归为 195 passed | 首次旧断言仍期望 17 个工具，归类为注册清单回归；更新 adapter/home/outbound 清单为 23 项 |
| 集成与安全 | `uv run pytest -q tests/test_qq_tools.py tests/test_milky_client.py tests/test_normalizer.py tests/test_resources.py tests/test_inbound_context_rendering.py tests/test_hermes_pipeline.py tests/test_plugin_entry.py`；`uv run pytest -q -rs` | 聚焦 195 passed；全量 633 passed、2 skipped；覆盖 fake transport 单次提交、raw envelope、日志投影、observe-only pipeline；skip 为 Hermes host 和 multimedia host 不可用 | 未发现协议/安全回归；未执行真实 Milky 管理、下载或上传 smoke |
| 质量门禁 | `uv run ruff check .`；`uv run ruff format --check .`；`uv build`；`git diff --check` | 全部 exit 0；构建产出 sdist/wheel | format check 首次发现并修复 `tests/test_outbound.py` 的 23 项清单格式；Hermes/Milky 真实基础设施仍按上项 skip 记录 |
| OpenSpec | `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict` | 6 passed、0 failed | 本 change proposal、两个 delta spec、design 和 tasks 一致；未执行可能改变群/请求状态或访问真实文件 URL 的 smoke |
