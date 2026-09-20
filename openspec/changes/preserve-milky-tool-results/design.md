# Design

## Context

See `proposal.md` for the motivation and scope. 当前 Milky Tool 响应路径在多个层次把 HTTP body
解码为 envelope/DTO，执行敏感键过滤和容器冻结，再通过 JSON 重建或固定错误分类交给 Hermes。
这些行为与本 change 的 raw passthrough 契约冲突。Hermes core 在 Tool handler 和
`post_tool_call` 之后、结果进入上下文之前调用 `transform_tool_result`；第一个字符串返回值可以
替换结果。core 的 Tool registry 还可能截断 JSON `error` 字段。插件不能修改 core，因此最终模型
可见结果的完全一致性必须作为 core 配置/版本的外部前置条件验证。

## Goals / Non-Goals

**Goals:**

- 将插件的 Milky Tool 响应路径划分为“网络前输入校验”和“网络后不透明响应交付”两个边界。
- 对任何已取得的远端响应体保留字节/内容语义，包括拒绝、HTTP 错误、未知字段、数组、显式
  `null`、敏感键和非预期 JSON 形状。
- 在没有远端响应体时继续提供本地参数、未绑定 client 和 `transport_unknown` 分类，并保持可能
  有副作用的 Action 单次调用且不重试。
- 让日志只观察低基数元数据，不复制或遍历 raw 响应；让 fake Hermes 证据明确区分插件交付边界
  与 core 的后置 transform 边界。

**Non-Goals:**

- 不修改 Hermes core、`transform_tool_result` 的实现、Tool registry 的截断策略或其他插件的 hook。
- 不取消工具参数校验、固定 operationId、认证、生命周期、显式调用和副作用安全边界。
- 不改变入站事件 DTO 解析、资源下载、普通消息上下文、日志命名空间或非 Tool 的出站结果契约。
- 不把原始响应写入日志、fixture 中的真实凭证或真实 Milky 环境。

## Decisions

### 1. 远端响应体采用不透明交付边界

网络请求前仍校验工具参数、operationId 和 client 状态；请求完成后不再调用面向 Tool 响应的
envelope/业务字段校验，不再使用 DTO 解析器作为交付前置条件。传输层取得的 body 保持其原始
内容表示并直接交给 Tool 结果序列化边界；HTTP 状态和协议状态只作为日志元数据，不能改变
Tool 结果。响应体中的 `token`、`authorization`、数组和未知字段因此不会被插件过滤或转换。

备选方案是继续解析后重建一个“完整 envelope”，但该方案无法保留未知顶层形状、显式字段顺序/表示、
非对象响应和未建模值，也会重新引入敏感字段过滤与容器转换，故不采用。

### 2. 本地错误与远端结果严格分开

只有网络前输入/可用性错误，或请求完成但没有取得响应体时，才生成 `invalid_input`、`unsupported`
或 `transport_unknown` 等插件固定结果。取得 body 后即使状态是 HTTP 错误、Milky 拒绝、JSON
损坏或结构未知，也交付该 body；副作用 Action 只允许一次调用，不能以“未能解析”作为重试理由。

备选方案是把 HTTP/协议拒绝继续压缩为 `rejected`、`http_error` 或 `malformed`，但这会丢失远端
语义并让插件介入 Tool 结果，故不采用。

### 3. `transform_tool_result` 作为 Hermes core 的外部后置边界

插件不注册、不拦截、也不反向覆盖 `transform_tool_result`。验证分两层：fake Hermes 在没有该 hook
时确认插件交付结果与 Milky body 一致；另一个 fake host 安装会返回替换字符串的 transform，确认
替换发生在插件交付之后，并将该差异标记为 core 行为，而不是插件 raw passthrough 失败。
部署要声明：若要求最终进入模型上下文的结果仍原样，则 core 必须不为这些 Tool 注册替换型
`transform_tool_result`，并提供跳过/保留 raw 结果的配置或版本能力。

同理，core registry 对 JSON `error` 字段的截断属于插件之外的后置限制；需要在兼容矩阵中记录，
并在可用的 core 环境中关闭、绕过或显式接受该截断后，才能宣称最终 Agent 可见结果完全一致。

### 4. 日志只记录旁路元数据

Tool 日志从 raw 结果中只产生固定的成功/远端响应/本地错误分类、Tool 名称、已知状态码和耗时，
不读取用于生成日志的 body 内容，不在日志对象中保留响应引用，也不回显参数或异常正文。日志行为
与交付行为分离，避免“为安全过滤而先解析结果”的实现路径。

## Risks / Trade-offs

- [Risk] 原始响应可能包含凭证或敏感业务字段，Tool 调用方仍会看到它们。→ 这是明确的 raw
  passthrough 契约；日志、异常和测试资料继续禁止复制，调用方权限与 Hermes core 的上下文策略
  由宿主负责。
- [Risk] 远端响应不再由插件提前发现 malformed 或协议拒绝。→ 保留网络前参数校验、无响应分类、
  低基数日志和 fake transport 覆盖；协议语义交由 Milky/Agent 侧处理。
- [Risk] core 的 transform 或 error 截断仍可能改变最终模型输入。→ 在 fake Hermes 中分别验证
  无 hook 与有替换 hook 的两种边界，并把 core opt-out/版本能力列为发布前置检查；插件不宣称能
  控制外部后置变换。
- [Risk] 响应 body 的字节表示与 Hermes Tool 结果要求可能存在适配差异。→ 先固定 transport、
  Tool handler 和 fake host 的结果载体契约；若 core 只能接受字符串，应由唯一的边界序列化步骤
  保持内容一致，禁止再次解析成 DTO 或重建 envelope。

## Migration Plan

1. 先新增 raw body、拒绝/HTTP 错误、空响应和未知 JSON 形状的合成 fixture 与 fake transport 断言。
2. 将 Tool 响应路径改为 opaque passthrough，保留入站 parser 和网络前参数校验；同步删除只服务于
   Tool 结果交付的过滤、冻结、最小 data 校验和 envelope 重建路径。
3. 增加 fake Hermes 无 transform 与有 transform 的对照证据，并在真实 Hermes 集成检查中确认 core
   的 transform/truncation opt-out；真实 Milky 和有副作用 Action 不作为自动测试前提。
4. 若发现 core 后置变换导致 Agent 可见结果不一致，回滚插件的 passthrough change 或暂停发布，
   不在插件内添加第二套过滤/还原逻辑。

## Open Questions

无。Hermes core 是否提供适用于这些 Tool 的 transform/truncation opt-out 是发布前置依赖，而不是
本插件可以延后决定的规格问题。
