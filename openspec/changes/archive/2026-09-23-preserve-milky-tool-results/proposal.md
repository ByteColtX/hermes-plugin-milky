# Proposal

## Why

Milky Tool 的远端响应目前在 client、sender 和 Tool handler 三层被解析为 envelope、过滤敏感键、冻结容器、校验最小 `data` 结构，并按 HTTP 状态和协议状态改写为 `rejected`、`http_error`、`malformed` 等插件固定结果。远端真正返回的内容因此到不了 Hermes core：协议拒绝时的 `message`/`wording` 被吞掉，非 2xx 的响应体被丢弃，未知形状和未建模字段被替换成插件自造的错误对象。插件应当只在网络前把关参数，网络后把远端返回的任何内容原样交给 Hermes core，由 core 和 Agent 自行解读。

## What Changes

- **BREAKING** 全部已注册 Milky Tool（包括名片赞、戳一戳、撤回、群信息/成员查询、禁言、合并转发、文件链接、好友与群请求、踢人、退群、删好友和专属头衔）只要 transport 取得响应体，就把该响应体原样作为 Tool 结果交给 Hermes core：不看 HTTP 状态，不看 `status`/`retcode`，不校验 `data` 结构，不过滤 `token`、`authorization` 等字段，不冻结或转换容器，不附加状态码，不重建、包装或摘要。
- **BREAKING** 移除 Tool 结果脱敏。当前插件在解析 envelope 时递归剔除响应体任意层级中键名（大小写不敏感）为 `access_token`、`authorization`、`cookie`、`password`、`token` 的字段，这些字段因此从未到达 Hermes core。本 change 后 Tool 路径不再执行该剔除，这五类键与其他字段一样原样交付；该脱敏逻辑继续服务于入站事件和非 Tool Action 解析，不在本 change 内删除。
- **BREAKING** `rejected`、`http_error` 和 `malformed` 不再作为 Tool 结果出现。插件本地固定结果只剩两类：网络前失败（参数非法、Tool 未注册、client 未绑定或已关闭）和请求进入 HTTP 边界后未取得响应体（`transport_unknown`）。
- Hermes core 对 Tool 结果的后置处理（`transform_tool_result` hook、JSON `error` 字段截断、大结果落盘替换为预览）属于 core 所有；插件不注册该 hook、不规避、不还原，本 change 的契约只覆盖插件交付给 core 的值，不覆盖最终进入模型上下文的内容。
- 保留 Tool 参数校验、固定 operationId、Bearer 认证、可能有副作用的 Action 最多提交一次、生命周期绑定和低基数日志；日志只记录 Tool 名称、结果分类、已知 HTTP 状态码和耗时，不读取或复制响应体。
- Tool 路径与非 Tool 路径分离：登录、群列表、MuteTracker 的成员状态查询、消息发送和文件上传仍走既有 envelope 校验和错误分类；它们不受本 change 影响。
- 增加 fake Milky transport 和 fake Hermes host 证据，验证插件交付给 core 的值与 transport body 内容一致，并验证插件没有注册 `transform_tool_result`。

## Capabilities

### New Capabilities

无。本 change 收敛既有 Milky Tool 的结果交付边界，不新增 Tool 或 Milky operationId。

### Modified Capabilities

- `security-boundaries`: 将 Tool 结果从“成功 envelope 原样交付”扩展为“任何已取得的远端响应体原样交付，适用于全部已注册 Tool”，并声明 Hermes core 后置处理不在插件契约内。
- `qq-action-tools`: 移除插件对查询和状态变更 Tool 响应的校验、过滤和固定结果替换要求，保留网络前参数校验、无响应分类、显式调用和安全日志边界。
- `qq-group-action-tools`: 对群文件、群请求、群邀请和专属头衔 Tool 采用相同的原样交付语义，保留显式调用、单次副作用和无响应分类。
- `milky-http-actions`: 需要一条范围 delta，把“HTTP 和协议 envelope 错误必须分类”与“Action 数据满足最小结构才算成功”限定为非 Tool 路径；该 delta 尚未创建，见 tasks。

## Impact

- 主要影响 [`milky/client.py`](../../../milky/client.py) 的 Tool 调用入口、[`outbound/sender.py`](../../../outbound/sender.py) 的 Tool 包装方法和 [`outbound/tools.py`](../../../outbound/tools.py) 的结果序列化与日志分类，以及对应测试 fixture。[`milky/parser.py`](../../../milky/parser.py) 的敏感键过滤和冻结逻辑继续服务于入站事件和非 Tool Action，不在 Tool 路径上调用。
- sender 中 nudge、撤回和群管理 Tool 在远端失败时触发的 MuteTracker 只读刷新随本 change 消失，因为插件不再解读 Tool 响应体；`mute-tracking` 只对消息发送失败授权该刷新，语义不受影响。
- 需要同步更新 [`ARCHITECTURE.md`](../../../ARCHITECTURE.md) 和 [`README.md`](../../../README.md) 中“所有 Action 均经 envelope 校验并分类”的描述，并记录 Hermes core 的三种后置处理为已知行为。
- 入站事件解析、普通消息上下文、日志内容边界、资源下载权限、Tool allowlist 和副作用调用次数不改变。本 change 不修改 Hermes core。
- 响应体中的凭证或敏感业务字段（包括此前被脱敏剔除的 `access_token`、`authorization`、`cookie`、`password`、`token`）会进入 Tool 结果、Hermes session 转录和 core 的大结果落盘文件；这是本 change 明确接受的契约，由宿主的上下文策略负责。Milky v1.3 公开 schema 中已注册 Tool 的响应没有声明这些键，实际暴露面取决于 Milky 实现的扩展字段。
- 真实 Hermes host、真实 Milky 响应和可能产生副作用的 Action 仍不自动验证；相关证据使用 fake host、fake transport 和合成 fixture。
