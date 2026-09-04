## Context

详见 `proposal.md`。当前固定 ToolSpec 由 `outbound/tools.py` 声明和注册，经过
`outbound/sender.py` 转交给 `milky/client.py`；client 维护显式 operationId 白名单、统一
`POST`/Bearer/path prefix、Milky envelope 解析和工具参数/结果校验。manifest、README 和
`ARCHITECTURE.md` 还把工具数量固定描述为 23 个。

当前公开 Milky v1.3 文档包含 `set_group_member_special_title`，其请求字段为
`group_id`、`user_id`、`special_title`，成功 data 是空对象；公开文档没有
`get_friend_info`。本 change 仍按用户明确指定的 operationId 暴露后者，但不凭空建立其
内部好友资料 DTO 或字段清单。

## Goals / Non-Goals

**Goals:**

- 让两个 operationId 都通过 manifest、ToolSpec、sender 和 client 的同一条显式 Action 边界
  可发现、可调用和可测试。
- 在第一个网络请求前完成参数集合、类型、QQ ID 范围和额外字段校验，并保持省略字段与
  Agent 原值的语义。
- 对 `get_friend_info` 采用不猜测内部字段的 opaque object 响应边界；对专属头衔采用空
  object 成功边界，并保留 HTTP、协议、malformed、transport unknown 和 unsupported 分类。
- 用脱敏 fixture 锁定 25 个固定工具的注册、请求路径、请求 body、结果保留、安全日志和
  未知结果单次提交行为。

**Non-Goals:**

- 不将 `get_friend_info` 的未确认内部字段加入 `FriendEntity`、parser 或入站消息 DTO；不
  从消息、好友名称或本地状态推断查询参数。
- 不把两个 operationId 改造成通用 Action catalog，不增加调用者/目标授权系统，也不修改
  Hermes core、Gate、Will、入站事件或普通消息上下文。
- 不因设置专属头衔刷新群成员缓存、群列表或 MuteTracker；本 change 不承诺远端状态变更后
  的本地快照一致性。
- 不执行真实 Milky 写入 smoke，除非后续实现阶段得到明确授权和符合目标 allowlist 的运行
  环境。

## Decisions

### 1. 沿用固定 ToolSpec 的四层边界

在 `outbound/tools.py` 增加两个 schema、注册 handler 和固定 tuple 项；在
`outbound/sender.py` 增加同名委托；在 `milky/client.py` 增加 operationId 白名单、参数
规则和最小响应规则；在 `plugin.yaml` 加入公开名称。所有层都使用同名 operationId，保持
调用只能落到对应的 `<base>/api/{operationId}`。

备选方案是让 handler 直接拼接 Action 名称，或开放按字符串查找的 Action catalog。前者会
绕过现有 sender/client 的校验，后者会扩大状态变更和未确认能力的暴露面，因此不采用。

### 2. `get_friend_info` 使用 `user_id` 单字段和 opaque data

工具只声明必填 `user_id`，按现有 QQ ID 规则拒绝 bool、越界值和额外字段。成功结果在工具
边界保留完整 envelope，只要求 `data` 是 JSON object；data 内部字段原样保留，不进入本地
typed DTO。这样可以支持用户指定的目标服务扩展，同时在公开 v1.3 尚无该 operation 时不把
昵称、性别、备注或其他字段错误地当作协议保证。

备选方案是复用入站 `FriendEntity`，或先把好友资料规范化为摘要。前者要求未确认的完整字段
和必填关系，后者丢失未知扩展字段，均与“未确认能力不猜测、不改写”的边界冲突。

目标服务若返回 404、HTTP 其他错误或协议拒绝，沿用现有分类；若返回成功但 data 不是
object，则归类为 `malformed`。这让“服务不提供该 operation”和“服务返回不可解析成功
结果”保持可观察差异。

### 3. 专属头衔保留三个字段的原值

`set_group_member_special_title` 的 handler、sender 和 client 都只接受
`group_id`、`user_id`、`special_title`。`special_title` 按字符串类型校验并原样传递，包含
空字符串；不套用会 trim 或拒绝空值的通用非空文本校验，因为空字符串是协议允许的字符串值，
其是否表示清除头衔由目标服务定义。成功只接受 `data={}`，不把远端状态复制到本地实体。

备选方案是把空字符串改成 `null`、省略字段或在本地先修改群成员对象。这些做法都会改写
协议 body 或制造未经确认的本地状态，因此不采用。

### 4. 状态变更沿用单次提交和未知结果边界

专属头衔是可能产生副作用的 Action。client 的一次 `call_tool` 只调用一次 HTTP Action；
timeout、连接/读写失败和 transport unknown 不自动重试，也不改目标。HTTP 200 的失败
envelope 返回 `rejected`，非空 data 返回 `malformed`。sender 只把安全分类交给 Tool 调用
方，日志沿用安全参数投影，不记录完整头衔、token、Authorization 或响应正文。

备选方案是对查询和管理都做统一重试，或在 unknown 后查询群成员确认。前者可能重复远端副
作用，后者会增加未授权网络调用并不能证明首次写入是否成功；两者都不符合当前未知结果契约。

### 5. 以脱敏 fixture 和清单回归锁定兼容性

扩展现有 `tests/test_qq_tools.py` 及 `tests/fixtures/qq_tools/`：schema fixture 增加两个
operationId；request fixture 覆盖 `user_id`、空头衔和额外字段；response fixture 覆盖好友
object、未知扩展、空 data、协议拒绝、malformed、HTTP 错误和 transport unknown。测试同时
断言 path prefix、POST、精确 body、单次请求、完整 envelope 和注册总数 25。manifest、
README 和 `ARCHITECTURE.md` 的清单同步更新，但不在文档中把 `get_friend_info` 的未确认
内部字段写成标准 v1.3 能力。

## Risks / Trade-offs

- [目标服务不支持公开 v1.3 未声明的 `get_friend_info`] → 保留 operationId 的显式请求边界，
  让远端 HTTP/协议错误如实分类；实现和交付证据记录目标服务契约或 `unsupported`/错误边界，
  不报告假成功。
- [好友资料的真实返回层级与未来 schema 变化] → 只校验 `data` object，保留完整 envelope
  和未知字段，不创建猜测 DTO；若目标服务后来提供正式 schema，再单独提出规范变更。
- [空 `special_title` 被某些实现拒绝] → 请求仍按 Milky 字符串契约原样传递，远端拒绝按
  `rejected` 返回，不在插件侧把它改成另一种清除语义。
- [新增固定工具遗漏某一层导致发现与执行不一致] → 使用注册数量、名称集合、client path、
  sender calls 和 manifest 清单的多层回归断言，并运行完整质量门禁。
- [自由文本或业务资料进入日志/fixture] → fixture 只使用 synthetic 值；日志仅保留安全 ID、
  operationId 和错误分类，不保留完整 `special_title`、好友资料、凭证或响应正文。

## Migration Plan

1. 先以目标服务的 operation 契约确认 `get_friend_info` 至少接受 `user_id` 并成功返回 object
   data；若无法确认，保留 opaque 规则和远端 unsupported/错误证据，不新增字段猜测。
2. 增加脱敏 schemas、request/response fixture 与最小失败案例，再接入 client、sender、handler
   和 manifest；所有实现改动保持在固定工具边界内。
3. 运行 QQ 工具聚焦测试、fake sender/client 集成测试、manifest/文档断言和安全日志断言；随后
   运行 `uv run pytest -q`、Ruff、format、build、`git diff --check` 及严格 OpenSpec 校验。
4. 按受控环境执行真实只读 `get_friend_info` 验证；专属头衔写入和其他副作用 smoke 仅在明确
   授权、目标命中运行时 allowlist 且记录结果未知边界后执行。
5. 回滚时移除两个 ToolSpec、client/sender 白名单项、fixture 和清单文案即可；不需要配置、
   入站状态或远端数据迁移，也不回滚其他固定工具。
