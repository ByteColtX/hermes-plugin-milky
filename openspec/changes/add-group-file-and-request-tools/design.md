## Context

动机见 `proposal.md`。当前工具边界已经通过显式 schema、handler、sender 和 Milky client
分层处理既有 operationId；当前入站 `FileSegment` 和 `FileAttachmentReference` 已经保存
可空的 `file_hash`，但 placeholder 生成只接收 `file_id` 和 `file_name`。Milky v1.3.0 OpenAPI
确认了本 change 六个 Action 的请求字段和最小成功 data 结构：群文件下载返回
`download_url`，群文件列表返回 `files`/`folders`，四个请求/邀请处理 Action 成功时返回
空对象。

## Goals / Non-Goals

**Goals:**

- 复用现有的显式 ToolSpec 生命周期，让 6 个新工具都经过同一套 schema、sender、client、
  HTTP、envelope 和错误分类边界。
- 让文件 placeholder 从已经规范化的 typed `file_hash` 生成，不重新读取 raw payload、
  不联网、不把缺失哈希伪造成可用值。
- 用合成 fixture 锁定 Milky v1.3.0 的请求字段、nullable 行为、最小响应结构、未知字段保留
  和管理 Action 的单次提交语义。
- 保持查询工具无文件下载/缓存副作用，保持群请求和群邀请处理的显式调用与
  `transport_unknown` 不重试边界。

**Non-Goals:**

- 不从 `file_id`、文件名、文件大小或群文件列表计算或补出私聊 `file_hash`。
- 不为群文件列表建立本地缓存，不把下载 URL直接转为 `MessageEvent.media_urls`，也不新增
  plugin 侧文件下载、SSRF 或权限规则。
- 不自动接受/拒绝群请求或邀请，不引入审批队列，不更新本地群成员、请求或邀请状态。
- 不开放未列出的 Milky Action，不修改 Hermes core 的工具注册或 Agent 队列契约。

## Decisions

### 1. 在现有显式工具分层中增加 6 个 operationId

为每个新增 operationId 增加独立 schema 和异步 handler；handler 只负责工具输入的字段集合、
类型、范围和枚举校验，sender 负责参数转发，client 负责统一 POST、认证、envelope 和协议
错误。client 的 Action allowlist 同步增加 6 个名称，确保即使绕过 ToolSpec 的调用入口也不会
使用未声明的参数集合。

采用该方案是为了保持注册阶段无网络、sender 生命周期绑定和既有错误分类一致。直接在
handler 中持有 client 会绕过生命周期边界；开放通用 Action catalog 会扩大 Agent 权限面，
两者都不采用。

新增字段映射固定如下：

| Action | 请求字段 |
|---|---|
| `get_group_file_download_url` | `group_id`、`file_id` |
| `accept_group_request` / `reject_group_request` | `notification_seq`、`notification_type`、`group_id`、可选 `is_filtered`；后者另有 `reason` |
| `accept_group_invitation` / `reject_group_invitation` | `group_id`、`invitation_seq` |
| `get_group_files` | `group_id`、可选 `parent_folder_id` |

`parent_folder_id` 的 OpenAPI 默认值不由插件预填；省略字段和显式 `null` 保持可区分。群请求
的 `notification_type` 只接受 OpenAPI 的两个枚举值，不能由通知正文或显示文本推断。

### 2. 使用 typed file reference 生成扩展 placeholder

将文件 marker 的输入扩展为 `file_id`、`file_name`、`file_hash` 三个值，并继续使用现有
placeholder 值归一化规则：空值、`null` 或不可用值展示为 `NOT SUPPORTED`。extractor 已经
从 `FileSegment` 复制 `file_hash` 到 `FileAttachmentReference`，因此只需让正文生成路径携带
该字段；不重新读取 raw、不访问文件系统、不调用 Milky Action。

placeholder 固定顺序为：

```text
[file:file_id=<file_id>,file_name=<file_name>,file_hash=<file_hash>]
```

该顺序和字段名同时用于当前消息与 wait buffer 的可观察正文；资源 resolver 仍从独立文件
引用读取字段，不能从正文反解析 hash。

### 3. 对查询和状态变更使用不同的最小响应校验

下载链接查询只确认 `data.download_url` 为字符串；群文件查询同时确认 `data.files` 与
`data.folders` 是对象数组。验证通过后保留完整 envelope 及未知字段，不创建摘要 DTO，也不
把 URL交给非确认的下载入口。

四个接受/拒绝 Action 只把成功的 `data` 确认为空对象，并原样返回完整成功 envelope。HTTP
200 但 `status`/`retcode` 表示失败仍分类为 `rejected`；结构缺失或类型错误分类为
`malformed`。这使响应校验不会把业务拒绝或未知扩展误报成成功。

### 4. 将群通知观察和群操作保持解耦

群请求、群邀请事件继续由入站系统事件路径 observe-only 处理；事件中携带的序号、类型或群号
只能作为 Agent 可见上下文，不能自动提交对应 Action。只有 Agent 显式提供完整 ToolSpec 参数
时才进入 sender/client。可能改变远端状态的四个 Action 每次调用最多提交一次；进入 HTTP 边界
后结果未知时返回 `transport_unknown`，不重试、不换目标、不写入本地状态。

这样可以复用既有的单次副作用与安全日志投影，而不把群请求事件升级为隐式授权来源。

### 5. 先扩展脱敏 fixture，再实现和回归

新增合成请求 body、成功 envelope、协议拒绝、HTTP 错误、非 JSON、缺少字段和传输未知 fixture。
查询结果 fixture 可以包含不可访问的占位 URL和未知字段，用于验证 Tool 调用方收到完整结果，
同时日志断言必须排除 URL、完整 `reason`、token、Authorization、路径和异常正文。文件
placeholder fixture 分别覆盖有效 hash、`null`、缺失和空值。

实现后按工具 handler/client/sender、normalizer、协议 fixture、注册和 fake pipeline 分层回归，
再执行完整 uv 质量门禁和 OpenSpec strict 校验；未获得明确授权时不调用真实群管理或文件 URL。

## Risks / Trade-offs

- [文件 hash 可能缺失或服务端返回 null] → placeholder 明确显示 `file_hash=NOT SUPPORTED`，
  不推算、不调用不满足必填参数的私聊 Action。
- [群管理请求的远端执行结果可能未知] → 区分 `transport_unknown` 与 `rejected`，单次请求不
  自动重试，不更新本地状态。
- [下载链接或群文件字段可能包含未来扩展] → Tool 成功结果保留 raw envelope，日志只保留
  安全结构投影；未确认字段不转成本地路径或自动下载。
- [OpenAPI nullable 字段与服务端默认值存在差异] → 请求 fixture 固定“省略”和显式 `null`
  的区别，插件不主动注入 `parent_folder_id`、`is_filtered` 或 `reason`。
- [新增工具会扩大 Agent 可见能力] → 只注册 6 个固定 operationId，拒绝额外字段和任意
  Action catalog，并保持事件/正文不能授予工具权限。

## Migration Plan

1. 建立并审查本 change 的协议、placeholder 和安全 fixture。
2. 增加 6 个 schema、handler、sender/client 委托、allowlist 和最小响应校验。
3. 更新 manifest、QQ tools skill、README、架构工具清单和相关注册/调用测试。
4. 运行聚焦测试、fake Hermes/Milky 集成、Ruff、构建、diff 检查和 OpenSpec strict 校验，
   在 tasks evidence ledger 中记录失败分类与实际 skip。
5. 发布后只在用户明确授权、目标和凭证已确认时执行真实查询 smoke；群请求/邀请处理和真实
   文件链接访问不因本 change 自动执行。
6. 回滚时移除新增 ToolSpec、allowlist、文档和 placeholder 字段即可，无远端数据迁移或本地
   状态迁移。
