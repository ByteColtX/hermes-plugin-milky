## 1. 契约与脱敏 fixture

- [x] 1.1 确认目标服务对 `get_friend_info` 的 operation 契约至少接受 `user_id` 并以 object `data` 返回；若目标服务暂不支持或字段仍未确认，记录 `unsupported`/错误边界而不新增猜测字段，并用一条脱敏成功或失败测试验证该决定
- [x] 1.2 扩展 `tests/fixtures/qq_tools/schemas.json`，加入 `get_friend_info` 和 `set_group_member_special_title` 的必填字段、类型、QQ ID 范围、空字符串规则及 `additionalProperties: false`，并用 schema 测试验证两个名称与实现注册集合一致
- [x] 1.3 扩展 `tests/fixtures/qq_tools/requests/bodies.json` 和响应 fixture，覆盖精确 `user_id` body、三个专属头衔字段、空 `special_title`、好友 object/未知扩展、空管理 data、协议拒绝、malformed、HTTP 错误和 `transport_unknown`，并验证 fixture 不含 token、Authorization、可访问 URL、真实 QQ 号、路径或完整敏感文本

## 2. 固定 Action 与工具实现

- [x] 2.1 在 `milky/client.py` 将两个 operationId 加入固定 Action 白名单、参数集合和结果校验，验证保留 base path prefix 的单次 `POST`、非法参数网络前返回 `invalid_input`、`get_friend_info` 仅要求 object data、专属头衔仅接受空 object 成功和未知结果不重试
- [x] 2.2 在 `outbound/sender.py` 增加两个同名委托并复用统一错误分类和安全日志投影，验证完整成功 envelope 原样交付、HTTP 200 协议拒绝与 malformed 分类正确，且日志不包含好友资料、完整 `special_title`、凭证或响应正文
- [x] 2.3 在 `outbound/tools.py` 增加两个 schema、handler 和 `TOOL_SPECS` 项，验证 `get_friend_info` 只接受合法 `user_id`，`set_group_member_special_title` 只传递三个字段且保留空字符串，不从事件、正文、名称或本地状态补参数
- [x] 2.4 更新工具注册与 manifest 的固定清单，验证两个工具使用 `milky` toolset、注册阶段无 HTTP/SSE/长期任务副作用、既有工具不覆盖，公开工具总数从 23 增至 25

## 3. 行为与安全回归

- [x] 3.1 扩展 `tests/test_qq_tools.py` 和相关集成测试，验证两个工具各自只访问同名 `/api/{operationId}`、请求方法为 `POST`、body 字段精确、完整 envelope/未知字段保留且不写入普通入站上下文
- [x] 3.2 增加非法类型、布尔 QQ ID、越界 ID、缺失字段、额外字段和专属头衔非字符串的网络前拒绝测试，验证 client、sender 和 registered handler 三条入口均不产生 Milky 调用
- [x] 3.3 增加专属头衔显式调用和未知结果测试，验证群通知、普通正文、mention、关键词、Will 或其他事件不会自动调用该 Action，超时/连接/读写失败只提交一次并返回 `transport_unknown`
- [x] 3.4 运行 `uv run pytest -q tests/test_qq_tools.py tests/test_outbound.py tests/test_plugin_entry.py tests/test_milky_client.py`，确认新增契约通过且现有 23 个工具、注册无网络和安全日志行为无回归

## 4. 文档、质量门禁与交付证据

- [x] 4.1 更新 `README.md`、`ARCHITECTURE.md` 和必要的 manifest 文案，说明 25 个固定工具、两个 operationId 的参数/结果边界以及 `get_friend_info` 未列入公开 Milky v1.3 的兼容性限制，并检查不写入未确认字段或敏感值
- [x] 4.2 运行完整质量门禁 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`，将命令结果或最小失败复现写入 change evidence ledger
- [x] 4.3 运行 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`，确认 proposal、两份 delta spec、design 和 tasks 结构及契约一致，并记录 fake host 与真实 Milky/Hermes 未覆盖的边界
- [x] 4.4 仅在明确授权、目标命中运行时 `MILKY_ALLOWED_CHATS` 且获得目标服务契约后执行受控 smoke；只读好友查询可验证真实响应，专属头衔写入不得默认执行，所有未知结果和未执行项须在 evidence 中明确记录
