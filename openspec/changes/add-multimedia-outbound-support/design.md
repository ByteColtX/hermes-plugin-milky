## Context

See `proposal.md` for the motivation. 当前 `MilkyOutboundSender` 已经能构造图片、语音、视频
segment，并能通过独立 upload Action 处理文件；但 `MilkyAdapter` 只覆盖普通 `send()`，
Hermes 的媒体入口仍会命中基类文本 fallback。Milky client 已有本地文件读取并编码为
`base64://` 的 upload seam，这个 seam 是当前本地资源出站的确认方案。

本设计必须同时满足 Hermes 的媒体投递签名、Milky v1.3 的 HTTP POST Action、group/dm 路由、
不重试未知副作用结果和项目的媒体所有权约束。插件只处理明确交给它的出站资源，不接管 Hermes
的入站下载、缓存、SSRF 或权限判断。

## Goals / Non-Goals

**Goals:**

- 让 Hermes 的图片 URL、本地图片、动画、语音、视频和文档附件真正经过 Milky adapter 的
  native 出站路径。
- 统一本地资源处理：读取已授权的普通文件，编码为 `base64://`，不把 `file://` 或本地路径
  交给远端 Milky。
- 保留显式 `http(s)://` 和 `base64://` 的远端 URI 入口，不在插件内额外下载 URL。
- 保持文件独立 upload、caption/媒体 segment 顺序、稳定结果 ID、错误分类和断开时 fail-closed。
- 用 fake Hermes、fake Milky transport 和本地 HTTP fixture 验证从 Agent 资源指令到用户可见
  多媒体出站的完整链路。

**Non-Goals:**

- 不修改 Hermes core 的 `MEDIA:` 解析、路径安全过滤、媒体权限或媒体缓存实现。
- 不新增任意 Agent-callable Milky Action、OneBot/CQ 出站协议或插件自己的媒体缓存目录。
- 不把文件包装成 message segment；不把失败伪装成普通文本成功。
- 不承诺无限大小的 base64 请求；超出内存、协议、代理或服务端限制时必须安全失败。

## Decisions

### 1. 在 adapter 覆盖 Hermes 的媒体出站入口

在 Milky adapter 增加与 Hermes 基类契约一致的图片 URL、图片文件、动画、语音、视频和文档
入口，并将它们委托给已经拥有 Milky 路由和结果转换逻辑的 outbound sender。普通批量图片
逻辑继续复用 Hermes 基类：它会通过动态 dispatch 调用 adapter 的图片方法，因此不复制
批量编排。

每个入口先执行与普通 `send()` 一致的连接/停止检查；未连接时直接返回 `unsupported`，
不得调用 sender、读取文件或走 Hermes 基类 fallback。adapter 只做生命周期门禁和委托，
不会在这里拼装 Milky Action body。

替代方案是让 Hermes 基类继续把媒体转换为文本，或在 adapter 中复制整套媒体分发逻辑；前者
无法产生 native 多媒体，后者会产生两套路由、错误和重试边界，因此不采用。

### 2. 为本地媒体建立无缓存的 base64 materialization seam

增加一个可复用的本地普通文件读取 helper，复用现有 upload 的安全校验和 `asyncio.to_thread`
边界：校验路径确实是普通文件后读取 bytes，生成 `base64://` + ASCII base64 内容，完成后
只保留当前 Action 所需的字符串，不写入临时文件或持久化缓存。现有 file upload path
入口和图片/语音/视频 path 入口共享该语义，避免一类资源继续发送不可达的 `file://`。

URI 规则固定为：

- `http://` / `https://`：视为显式远端引用，做基本 URL 校验后原样交给已确认的 Milky
  segment 或 upload Action，不由插件下载；
- `base64://`：视为显式内联引用，做非空校验后原样使用；
- `file://` 和无 scheme 的本地路径：只允许当前主机可读的普通文件，并转换为 `base64://`；
- 其他 scheme、目录、空路径和不可读路径：在网络访问前返回 `invalid_input` 或
  `unsupported`，不回显输入值。

这比直接发送 `file://` 更适合 Milky 与 Hermes 不在同一可见文件系统的部署，也与当前已确认
的本地文件 upload seam 一致。代价是 base64 会完整占用内存并放大 JSON 请求体；实现必须
复用现有错误分类、日志脱敏和未知结果不重试规则，不能以自动重试缓解大请求失败。

### 3. 图片、语音、视频与文件保持不同的 Milky wire boundary

图片、语音和视频将 materialized URI 放入 `image`、`record`、`video` message segment，
可选 caption 作为前置 text segment；随后按 group/dm 调用对应 send message Action。文件不
进入 message segment，继续由 `upload_group_file` 或 `upload_private_file` 处理，并以远端
`file_id` 作为成功结果。

sender 已经承担 segment 校验、目标解析、分块和结果转换；adapter 委托不得绕过这些边界，
也不得把 document caption 拼进 file URI。文件上传失败只返回原始安全分类，不额外发送用户可见
的路径诊断。

替代方案是将文件先发送为文本 URL，或把所有资源都伪装成 image segment；前者依赖远端可达性
且不是真正附件，后者不符合 Milky file upload 契约，均不采用。

### 4. 用 Hermes 既有 `MEDIA:` 交接证明用户路径

集成测试使用 Hermes 已有的媒体交接语义：合成 Agent 输出显式 `MEDIA:<path>`，由宿主完成
路径过滤和资源分类，再调用 adapter 的对应媒体入口。测试只使用临时普通文件、合成内容和
fake transport，断言最终 Milky 请求包含 base64 URI 或独立 upload Action；不把真实工作区
路径、凭证、完整资源正文或 live 响应写入 fixture。

该测试只证明插件 adapter 边界和已确认的 Hermes 调用契约，不把 fake core 当成 Hermes core
修改的证据。若当前宿主版本没有某个媒体入口的可验证调用 seam，保留该场景为
`unsupported` 并记录原因，而不是自行添加宿主 fallback。

## Risks / Trade-offs

- [base64 读取整个文件导致内存和 JSON 请求体膨胀] → 对资源大小设置明确的实现边界并在
  文档中说明；超限、编码失败和传输超时返回分类错误，不自动重试未知结果。
- [Milky 服务端不支持某种媒体 segment 或 URI 形态] → 只使用已确认的 image/record/video
  schema；协议拒绝保持 `rejected`，不改投文本或其他 Action。
- [Hermes 媒体入口签名随宿主版本变化] → 保持 adapter 方法与当前宿主签名一致，使用真实
  基类 dispatch 的集成测试，失败时记录宿主 API 分类。
- [多个媒体附件部分成功] → 每个附件独立记录结果；已成功的 Action 不重发，后续失败只返回
  原始分类，不用 fallback 重新发送相同内容。
- [日志或异常意外携带本地路径或 base64 内容] → 只记录资源种类、数量、路由和安全错误
  分类；禁止记录 URI、路径、文件名、正文和原始异常。

## Migration Plan

1. 先补充合成资源 fixture、base64 编码契约和 adapter 媒体委托测试，确认现有普通文本、
   structured segment、文件 upload 和未知结果行为不变。
2. 实现共享本地 materialization，并将本地图片、语音、视频和文件切换到 `base64://`；保留
   显式远端 `http(s)://` 和 `base64://` 输入。
3. 接入 Hermes adapter 的媒体入口，运行 fake end-to-end 与全部质量门禁；未通过宿主 seam
   验证的入口保持明确 `unsupported`，不报告假成功。
4. 更新 `ARCHITECTURE.md`、`README.md` 和能力矩阵，说明本地资源的临时 base64 方案及其
   大文件限制。回滚时可移除 adapter 委托，但不得恢复向用户发送本地路径或对未知结果重发。

## Open Questions

无。资源大小边界应在实现任务中采用固定、可测试的安全上限，并在代码和文档中保持一致；这
不会改变 URI、Action、错误或 adapter 交接契约。
