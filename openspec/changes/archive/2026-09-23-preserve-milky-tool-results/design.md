# Design

## Context

See `proposal.md` for the motivation and scope. 当前 Milky Tool 响应路径在 client、sender 和 Tool
handler 三层把 HTTP body 解码为 envelope/DTO，执行敏感键脱敏（递归剔除键名为 `access_token`、
`authorization`、`cookie`、`password`、`token` 的字段）、容器冻结和最小 `data` 校验，再按
HTTP 状态和协议状态改写为 `rejected`、`http_error`、`malformed`，最后由 Tool handler 重建 JSON。
这条路径与登录、群列表、MuteTracker 成员查询、消息发送和文件上传共用同一个 Action 调用入口。
Hermes core 只接受字符串（或多模态信封）作为 Tool 结果，并在插件 handler 之后运行
`transform_tool_result` hook、截断超长 JSON `error` 字段、把超过阈值的结果落盘替换为预览。
这些 core 行为没有按 Tool 的 opt-out；插件不能修改 core。

## Goals / Non-Goals

**Goals:**

- Tool 路径分成两段：网络前校验参数、operationId 和 client 状态；网络后把已取得的响应体不透明地
  交给 Hermes core。
- 对任何已取得的响应体保留内容语义，包括协议拒绝、非 2xx 状态、未知字段、数组、标量、显式
  `null`、敏感键、非 JSON 文本和非预期形状；HTTP 状态和协议状态只进入日志。
- 只在没有远端响应体时产生插件本地结果，并保持可能有副作用的 Action 最多提交一次。
- 非 Tool 路径保持既有 envelope 校验和错误分类，不被 Tool 透传牵连。
- 日志只观察低基数元数据，不读取、遍历或保留响应体。

**Non-Goals:**

- 不修改 Hermes core，不规避或还原 core 的后置处理，不承诺最终进入模型上下文的内容与 Milky
  响应一致。
- 不取消工具参数校验、固定 operationId、认证、生命周期、显式调用和单次副作用边界。
- 不改变入站事件 DTO 解析、资源下载、普通消息上下文、日志命名空间或非 Tool 的出站结果契约。
- 不把原始响应写入日志、fixture 中的真实凭证或真实 Milky 环境。

## Decisions

### 1. Tool 路径是唯一的不透明交付边界，与非 Tool 路径分离

Tool 调用入口在取得 transport 响应后直接把 body 交给 Tool 结果序列化边界，不再调用 envelope
解析、敏感键脱敏、容器冻结、最小 `data` 校验或 HTTP/协议状态判断。Tool 结果脱敏因此被整体
移除，而不是缩减键名列表或改为掩码；脱敏逻辑本身保留在 parser 中，继续作用于入站事件和非
Tool Action。登录、群列表、MuteTracker
的 `get_group_member_info`、消息发送和文件上传继续走既有校验和分类路径；两条路径不共享响应
处理代码。由于 Tool 入口的语义现在与通用 Action 入口不同，需要给 `milky-http-actions` 补一条
范围 delta，把“HTTP 和协议 envelope 错误必须分类”和“Action 数据满足最小结构才算成功”限定为
非 Tool 路径。

备选方案是继续解析后重建“完整 envelope”，但该方案无法保留未知顶层形状、非对象响应和未建模值，
且仍要求插件判断成功与失败，故不采用。

### 2. 插件本地结果只在没有远端响应体时出现

只有网络前失败（参数非法、Tool 未注册、client 未绑定或已关闭）和请求进入 HTTP 边界后未取得
响应体（超时、连接中断、写入或读取失败）才返回插件固定结果，前者沿用 `invalid_input` 和
`unsupported`，后者是 `transport_unknown`。取得 body 之后不存在任何插件错误分类：HTTP 500 的
HTML 页面、`retcode` 非零的 envelope、损坏的 JSON、空 body 都按原样交付。副作用 Action 不因
“无法解析”而重试。

Hermes core 只接受字符串结果，所以字节到字符串的转换是唯一不可避免的一步。body 以 UTF-8 解码
交付；无法解码的字节用替换字符表示，仍然交付而不返回本地错误。这是有意接受的最小偏差，因为
返回 `malformed` 就重新引入了插件对响应的解读。

备选方案是把非 2xx 或非 JSON 响应包装成 `{"status_code": ..., "body": ...}`，让 Agent 能看到状态码。
这会让 Tool 结果形状依赖插件判断，与“原样交付”冲突，故不采用；状态码只出现在日志。

### 3. Hermes core 的后置处理不在插件契约内

插件不注册、不拦截、也不反向覆盖 `transform_tool_result`，不绕过 `error` 字段截断，不阻止大结果
落盘。本 change 的可验证契约是“插件交付给 core 的值与 transport body 内容一致”，用 fake Hermes
host 在无 hook 时断言。core 之后做什么由 core 版本和已启用的其他插件决定，在 README 中记录为
已知行为，不作为发布门，也不因 core 改写结果而回滚本 change。

### 4. 日志只记录旁路元数据

Tool 日志从 transport 层取 Tool 名称、结果分类（`delivered`、`transport_unknown`、`invalid_input`、
`unsupported`）、已知 HTTP 状态码和耗时，不读取 body 内容，不在日志对象中保留响应引用，不回显
参数或异常正文。分类反映的是“是否取得响应体”，不是远端成功与否，所以协议拒绝和 HTTP 错误在
日志里都是 `delivered` 加状态码。

### 5. 远端失败驱动的 MuteTracker 刷新随透传消失

sender 中 nudge、撤回和群管理 Tool 目前在 `rejected`/`http_error`/`malformed` 时调度一次 MuteTracker
只读刷新。透传后插件不再知道远端是否失败，这条刷新链自然消失。`mute-tracking` 只对消息发送
失败授权刷新，消息发送不在 Tool 路径上，所以不需要替代机制；`transport_unknown` 时也不刷新，
以免把传输故障误读为群状态变化。

## Risks / Trade-offs

- [Risk] 移除 Tool 结果脱敏后，此前被剔除的 `access_token`、`authorization`、`cookie`、
  `password`、`token` 字段和其他敏感业务字段会进入 Tool 结果、session 转录和 core 落盘文件。→
  这是明确接受的契约；插件不再对 Tool 结果做任何脱敏、掩码或键名过滤，日志、异常和测试资料
  继续禁止复制，上下文策略由宿主负责。
- [Risk] Agent 收到 HTTP 502 的 HTML 页面时看不到状态码，无法区分远端拒绝与代理故障。→ 状态码
  在日志中可查；插件不为此包装结果。副作用 Action 仍只提交一次。
- [Risk] core 的 transform、截断或落盘改变最终模型输入。→ 契约止于插件交付值；在 README 记录
  三种 core 后置处理，插件不宣称能控制它们。
- [Risk] 去掉 Tool 响应校验后，Milky 协议漂移不再被插件提前发现。→ 非 Tool 路径的校验仍在，
  入站 parser 和 smoke 检查继续覆盖协议形状。
- [Risk] 非 UTF-8 body 用替换字符解码后与原字节不一致。→ core 只接受字符串，这是唯一的强制转换；
  Milky 实际返回 JSON，该路径只在异常代理下出现。

## Migration Plan

1. 新增 fixture 和 fake transport 断言：成功 envelope、`retcode` 非零、HTTP 4xx/5xx、非 JSON 文本、
   JSON 数组/标量/`null`、含 `token`/`authorization` 的对象、空 body。
2. 给 Tool 调用入口建立独立的响应交付路径，删除只服务于 Tool 结果的 envelope 解析、过滤、冻结、
   最小 `data` 校验、状态判断和 JSON 重建；非 Tool 路径保持不变。
3. 更新 sender 的 Tool 包装方法和 Tool handler，删除远端失败驱动的 MuteTracker 刷新和固定错误
   替换；更新日志分类。
4. 增加 fake Hermes host 断言插件交付值与 body 一致且未注册 `transform_tool_result`。
5. 更新 `ARCHITECTURE.md`、`README.md` 和主 spec；创建 `milky-http-actions` 范围 delta。

## Open Questions

无。
