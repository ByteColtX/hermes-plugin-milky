# Design

## Context

动机见 proposal.md。工具 handler、出站和协议 module 分别持有字段规则，生产路径取得不透明响应，旧测试路径还存在 typed 转接。主规范已经覆盖固定目录、校验和结果交付，本 change 不扩展行为。

当前实现存在需要记录的差异：三个群查询工具收到显式 no_cache=false 时，请求体仍省略该字段；名片点赞的 schema 声明 count 为 1–50 且不可空，注册入口与协议校验实际接受更宽整数范围及 null。这些是源码证据，不代表新增协议保证；纯重构保持实际请求与结果，不能在集中规则时自动按 schema 收紧或补字段。

## Goals / Non-Goals

**Goals:** 全部 26 个固定 Action 通过同一执行 module 的窄 interface 获得 depth；参数与结果知识取得 locality，注册入口与直接调用入口复用规则，生产与测试走相同响应契约。

**Non-Goals:** 任意操作入口、通用 schema 引擎、修正既有 schema 或请求投影差异、改变工具参数或返回、合并非 Tool 响应处理、重构媒体发送、Tool 运行归属或命令实例绑定。

## Decisions

1. 固定执行 module 拥有共同字段契约和单次执行；注册层只选择已登记 operation。直接传任意字符串的公开入口会扩大操作范围，纯转接也不能消除重复知识，因此目录保持私有且显式。工具名称与 manifest 的一致性由注册 interface 的契约测试确认。
2. 网络是 true external 依赖，现有 HTTP 与 fake transport 两个 adapter 已支撑真实 seam。执行 module 复用当前 client 所拥有的认证、路径、连接和关闭状态，不另建连接、不绕过关闭检查；现有生命周期拥有者仍负责释放。Tool 与非 Tool 响应处理保持不同契约，后者继续承担同步、资源和发送的 typed 校验。测试兼容转接逐组迁移到同一 raw 响应 seam，不把 typed 测试结果包装成生产契约，也不允许请求开始后切换 adapter 重发。真实 host 的后置 Tool 处理仍由宿主拥有。
3. 验证覆盖缺省、显式 null、false、合法空字符串、错误类型、未知字段以及未绑定、已关闭、取消与无响应；完整响应只交给调用方，日志仅保存既有安全分类。组合非法输入与未绑定状态时，错误先后顺序以现有注册工具结果为准，不因合并校验改变。
4. implementation 内可共享计算规则，但每个调用入口仍承担网络前校验。删除重复实现不等于删除防护，参数不可被前层校验后再悄然改写。
5. 先为注册入口建立逐 operation 的请求与结果基线，再集中共同规则；单独列出 schema、主规范和运行行为的差异，防止差异被同一份派生 fixture 隐藏。将原有行为搬进更多调用方会增加 interface 知识；删除 shallow 转交并把规则收拢到执行 implementation，才能产生 leverage。未来行为修正需要独立确认并调整相应规范，本 change 保持 skip_specs。

## Risks / Trade-offs

- [Risk] 省略字段被补默认值或 null 被删除。→ 对请求体做差异断言，逐 operation 核验既有契约。
- [Risk] unknown 后走备用路径造成第二次副作用。→ 传输故障测试断言一次请求且无 fallback 重发。
- [Risk] 为减少方法而损失既有直接调用方兼容性。→ 只迁移固定 Tool 路径，保留仍被实际调用的 typed interface。
- [Risk] 将 schema 当成当前执行的唯一事实来源，悄然收紧校验或改变 false 投影。→ 保留独立的实际请求基线和差异记录，不在本 change 修正行为。
- [Risk] 执行 module 新建或借用未受管理的连接。→ 复用既有 client 生命周期；以未绑定、关闭和取消场景确认不创建连接、不重发。

## Migration Plan

先建立注册 interface 的本地行为基线和差异记录，再收拢共同规则并逐组迁移调用；同组提交测试和架构说明。迁移 typed fake 后，确认剩余直接调用方及非 Tool 路径仍可用，再移除已被完整覆盖的内部转接测试，保留传输专项。现有 Tool 绑定与两个贴纸语义工具保持原有所有权，不依赖相邻的命令绑定、Dashboard 或未交付能力。无持久数据迁移；回滚恢复旧执行路径，固定工具目录保持一致。

## Open Questions

真实 Hermes 的 Tool 后处理和真实 Milky 行为需实施后独立确认；本地 fake 结果不替代它们。不影响本方案选择。
