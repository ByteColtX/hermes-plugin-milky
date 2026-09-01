## Context

详见 `proposal.md` 的 Why。当前插件已有 9 个显式 Milky ToolSpec，工具通过生命周期绑定的
出站 sender 调用 Milky client；client 已具备通用 POST、Bearer、path prefix、envelope 和
传输错误边界。当前 client 已有转发查询和私聊文件下载链接的 Action 方法，但它们尚未被
工具白名单和 ToolSpec 暴露；群成员踢出、退群以及好友关系操作尚未完成工具边界。

本 change 必须保持 `ARCHITECTURE.md` 的三层边界：工具是显式能力，不是任意 Action catalog；
普通入站事件不授予工具权限；Hermes 仍拥有 Agent turn 和入站媒体资源处理。Milky v1.3.0
OpenAPI 已确认本 change 的 8 个 operationId、请求字段和最小响应结构。

## Goals / Non-Goals

**Goals:**

- 在现有工具注册机制中增加 8 个稳定的 operationId 对齐工具，并让工具 schema 与 OpenAPI
  参数边界一致。
- 让查询工具返回完整、可验证的 Milky 成功 envelope，同时保留未知字段；让状态变更工具
  只使用显式调用并保留未知执行结果。
- 在 transport、协议和响应字段错误之间保持现有可观察分类，并在请求前完成参数和 client
  生命周期校验。
- 为包含下载链接、文件信息和自由文本的工具调用建立不泄露凭证、媒体 URL、本地路径和
  敏感理由的安全审计投影。

**Non-Goals:**

- 不自动消费 `friend_request` 或其他 notice/request 事件，不从事件、正文、关键词或 Will
  决策推导好友批准、拒绝、删好友、踢人或退群操作。
- 不新增 friend/group 列表、群请求、群公告、文件管理或其他未在本 change 列明的 ToolSpec。
- 不把 `get_forwarded_messages` 的结果自动展开到普通入站正文、`channel_context` 或
  Hermes transcript；不在 `get_private_file_download_url` 内下载、缓存、解码或改写文件。
- 不新增权限数据库、审批系统、重试队列、持久化状态或 Hermes core 修改。

## Decisions

### 1. 沿用现有工具到 sender 到 client 的调用链

新增 schema 和 handler 放在现有的工具注册边界；handler 负责严格校验工具输入，sender 负责
目标/参数到 Milky Action 的映射，client 负责 HTTP 和协议 envelope。当前已存在的转发和私聊
文件 client 方法复用同一实现，并将新增 operationId 纳入显式 Tool allowlist；新增的管理
Action 也通过同一条链路调用。这样可以保持注册阶段不联网、生命周期绑定一致和错误分类一致。

备选方案是在 handler 中直接持有 client 或开放通用 Action 调用。前者会绕过 sender 生命周期
和统一校验，后者会扩大 Agent 权限面，因此不采用。

### 2. 以 OpenAPI 字段名为唯一工具参数名

ToolSpec 直接公开 Milky schema 的字段名：QQ 号使用 `user_id`/`group_id`，好友请求操作使用
字符串 `initiator_uid`，文件查询使用 `file_id`/`file_hash`。工具层拒绝字符串伪装的整数、
布尔伪装的整数、空字符串、越界值和额外字段；可选 nullable 字段只有显式提供时才进入请求。
不把昵称、好友列表、当前消息 sender 或入站 allowlist 当作参数补全来源。

备选方案是接受多种别名并在插件内部改名。该方案会掩盖调用错误，也容易把 UID 和 QQ 号
混用，因此不采用。

### 3. 查询结果保留 raw envelope，响应结构只做最小验证

查询工具验证 `data.messages`、`data.download_url` 和 `data.requests` 的最小容器/字段形状，
管理工具验证成功 data 是确认的空对象，然后仍以完整 envelope 返回给 Tool 调用方。不会把
好友请求或转发消息转换成插件自有摘要 DTO，也不会丢弃未知字段。解析器或 client 只增加
必要的最小验证；任何不能确认的扩展字段保持 raw 数据，不解释其业务语义。

备选方案是把结果映射成固定 DTO。该方案会丢失协议扩展，并与现有 Tool raw envelope 契约
冲突，因此不采用。

### 4. 把副作用控制在一次显式 Action 调用

踢人、退群、删好友、接受好友请求和拒绝好友请求不更新本地 MuteTracker、好友缓存或群
缓存，也不通过备用目标补发。Action 已进入 HTTP 边界后遇到超时、连接中断或响应不确定时，
只返回 `transport_unknown`；工具层不自动重试。确认结果为协议拒绝时返回 `rejected`，不把
HTTP 200 当作成功。

该设计不发明新的 Hermes 确认 API；它只保证没有隐式事件触发和客户端重试。后续若 Hermes
提供独立的高风险工具审批扩展，应另立 change 确认其注册契约。

### 5. 分离 Tool 返回和安全审计日志

成功 envelope 仍完整交给 Tool 调用方，以便 Agent 使用协议确认的结果。日志采用 action-specific
安全投影：保留工具名、可安全关联的业务 ID、布尔/数量字段和错误分类，去除 token、Authorization、
下载 URL、头像/媒体 URL、本地路径、完整响应 body、文件内容以及 `reason` 等自由文本。失败
日志只记录固定分类和安全阶段，不记录底层异常正文。该投影只影响日志，不改变 Tool 调用方
看到的完整成功结果。

### 6. 用脱敏合成 fixture 覆盖协议边界

为 8 个 Action 建立合成请求/响应 fixture；下载链接、头像和自由文本使用非真实的占位值，
不保存 live 响应、凭证、真实 QQ、媒体路径或完整媒体内容。测试同时覆盖 handler 的网络
前置拒绝、client allowlist、完整 envelope 保留、最小 data 缺失、unknown transport 和
日志安全投影。

## Risks / Trade-offs

- [好友 UID 与 QQ 号同时存在时可能被调用方混用] → Tool schema 强制 `initiator_uid` 为非空
  字符串，并覆盖数字、昵称和空值的拒绝测试。
- [管理 Action 是不可逆或远端执行状态未知的操作] → 只允许显式 Tool handler 触发，一次
  调用最多提交一次；未知结果不重试、不换目标、不伪造成功。
- [raw 查询结果可能包含未来新增的 URL 或敏感字段] → Tool 返回保留协议原样，但审计日志
  使用字段名/值类别安全投影；新增敏感字段进入 fixture 和日志回归后再归类。
- [Milky 实现对可选 nullable 字段的默认处理存在差异] → 缺省字段不自行补入请求，显式
  `null` 按 OpenAPI nullable 语义保留，并用请求 body fixture 锁定边界。
- [现有 Hermes host 的 Tool 注册字段可能有差异] → 复用已通过当前 host 回归的注册形状；
  host 不可用时记录 blocked 证据，不把 fake context 当作真实集成通过。

## Migration Plan

1. 先补 8 个 ToolSpec 的脱敏 schema、请求 body、成功/失败 envelope 和日志安全 fixture。
2. 扩展显式工具白名单和 sender/client 调用链，补齐最小响应验证；更新 manifest 和 QQ tools
   说明。
3. 运行工具单元、协议 fixture、fake Hermes 注册、fake Milky transport 和错误/日志回归，
   再运行完整 uv 质量门禁和 OpenSpec strict 校验。
4. 真实 Milky 只读 Action smoke 仅在用户明确授权且运行时注入凭证时执行；踢人、退群、删
   好友、接受/拒绝好友请求和文件链接访问等可能影响外部状态的 smoke 不在本 change 自动执行。
5. 回滚时移除新增注册项和 allowlist 项即可；不需要远端数据迁移，也不恢复本地副作用状态。

## Open Questions

无。8 个 Action 的 operationId、参数和最小响应结构已由当前 Milky v1.3.0 OpenAPI 确认；
若未来需要审批、分页游标、结果转换或更多 Action，应另立 change。
