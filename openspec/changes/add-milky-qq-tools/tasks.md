## 1. 契约与脱敏协议 fixture

- [ ] 1.1 建立 8 个新增 ToolSpec 的合成 schema fixture，覆盖 operationId、必填/可选字段、nullable、数值范围和 `additionalProperties: false`；通过 fixture 断言确认不包含凭证、真实 QQ、真实媒体 URL、路径或 live 响应
- [ ] 1.2 建立 `get_forwarded_messages`、`get_private_file_download_url` 和 `get_friend_requests` 的成功 envelope fixture，覆盖 `messages`、`download_url`、`requests`、未知 envelope/data 字段及字段类型错误；通过协议 fixture 测试验证最小结构分类
- [ ] 1.3 建立 `kick_group_member`、`quit_group`、`delete_friend`、`accept_friend_request` 和 `reject_friend_request` 的成功空对象 envelope、协议拒绝、HTTP 错误、非 JSON 和传输未知 fixture；通过分类测试验证 HTTP 200 不等于协议成功
- [ ] 1.4 建立 8 个 Action 的请求 body 预期和日志安全输入/输出 fixture，覆盖可选字段省略、显式 null、`initiator_uid`、拒绝理由和下载链接；通过安全断言验证 fixture 不落入 token、Authorization、完整理由、URL 或本地路径

## 2. Milky client 与 sender 调用边界

- [ ] 2.1 将 8 个 operationId 纳入显式 Tool Action allowlist，并复用现有 POST、Bearer、path prefix、envelope 和 transport 分类；通过 fake transport 断言每个请求只访问对应 `/api/{operationId}`
- [ ] 2.2 补齐 8 个 Action 的 sender/client 委托和最小响应结构验证，同时保留完整成功 envelope 与未知字段；通过查询和空对象 fixture 测试验证 `data.messages`、`data.download_url`、`data.requests` 及管理 Action data 边界
- [ ] 2.3 在 sender 和 client 边界实现严格的 QQ ID、UID、文件字段、limit、布尔值、reason 和额外字段校验；通过非法类型、空值、越界值和额外字段测试验证网络访问前返回 `invalid_input`
- [ ] 2.4 让可能改变远端状态的 5 个管理 Action 每次显式调用最多提交一次，保留 `rejected` 和 `transport_unknown` 原分类，不回退目标、不更新本地 MuteTracker/缓存、不自动重试；通过超时/连接中断 fake transport 验证调用次数为 1

## 3. ToolSpec 注册与处理器

- [ ] 3.1 在现有显式工具注册边界增加 8 个 schema 和异步 handler，确保工具名、描述、toolset 和 Milky operationId 一一对应；通过注册 context 测试验证新增 8 项与既有工具同时存在且无重复注册
- [ ] 3.2 实现查询 handler 的参数映射和完整 raw envelope 返回，验证 forward 结果不进入普通 Hermes turn、私聊文件 Action 不下载/缓存/解码、好友请求结果不改变本地状态；通过 fake sender 和 handler 集成测试验证无隐式副作用
- [ ] 3.3 实现群/好友管理 handler 的显式调用边界，验证事件、正文、关键词和 Will 不会触发 Action，且未连接/已关闭 client 在网络前返回 `unsupported`；通过 fake pipeline、生命周期和未绑定 sender 测试验证
- [ ] 3.4 更新 `plugin.yaml`、根入口工具发现和 `skills/qq-tools/SKILL.md` 的工具清单与参数说明；通过根注册测试和静态清单断言验证只声明 17 个固定 ToolSpec，不出现任意 Action catalog

## 4. 安全日志与宿主集成回归

- [ ] 4.1 为 Tool 审计日志增加安全投影，保留工具名、非敏感业务 ID、布尔/数量字段和错误分类，排除下载/媒体 URL、本地路径、完整响应 body、文件内容、凭证和 `reason`；通过日志捕获测试验证 Tool 调用方仍收到完整 raw envelope
- [ ] 4.2 增加实际 Hermes Tool 注册/调用形状回归（宿主源码可用时），验证注册阶段无网络、工具 client 随 adapter 生命周期绑定/解绑；宿主不可用时记录 `blocked` 证据，不标记真实集成通过
- [ ] 4.3 增加 friend/group 事件 observe-only 回归，验证 `friend_request` 和群通知不自动调用接受、拒绝、踢人、退群或删好友 Action；通过 SSE fixture 和 fake client 调用记录验证
- [ ] 4.4 覆盖 client 未连接、关闭、非法参数、HTTP 失败、协议拒绝、非 JSON、最小 data 缺失和 `transport_unknown`；通过错误分类断言验证不伪造成功、不暴露底层异常、不创建第二次副作用请求

## 5. 文档、质量门禁与证据台账

- [ ] 5.1 更新 `ARCHITECTURE.md`、`README.md` 和 change evidence ledger，说明 17 个固定 ToolSpec、显式状态变更边界、raw envelope 结果和日志脱敏边界；通过文档扫描验证不把未实现能力或真实环境结果写成已交付
- [ ] 5.2 运行工具、client、sender、协议 fixture、注册和安全测试，并执行 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`；在 tasks 台账中记录完整命令结果及协议、权限、Hermes host 或测试基础设施分类
- [ ] 5.3 执行 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`，验证 proposal、两个 delta spec、design 和 tasks 一致；未获明确授权时不执行会改变好友/群状态或访问真实文件链接的 Milky smoke
