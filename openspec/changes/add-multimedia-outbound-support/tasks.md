## 1. 契约与脱敏 fixture

- [x] 1.1 建立合成的图片、语音、视频和普通文件输入 fixture，覆盖 `http(s)://`、`base64://`、`file://`、本地路径、空值、目录和不可读路径；验证 fixture 不包含真实路径、凭证、完整媒体内容或 live 响应
- [x] 1.2 建立 group/dm 的媒体 Action 请求与成功/拒绝/malformed/transport_unknown 响应 fixture；验证请求方法、目标、segment/upload 边界和稳定结果 ID 断言可复现
- [x] 1.3 建立 Hermes `MEDIA:<path>` 到 adapter 媒体入口的 fake dispatch fixture，覆盖图片、语音、视频和文档；验证资源进入 native 出站而不是基类文本 fallback

## 2. 本地资源 base64 materialization

- [x] 2.1 抽取可复用的本地普通文件读取与 `base64://` 编码边界，复用异步线程读取、普通文件校验和安全错误分类；验证字节内容、空文件、目录和不可读路径测试通过
- [x] 2.2 为本地资源设置固定且可测试的安全大小上限，并在超限前拒绝读取/网络访问；验证边界值、超限值、错误分类和日志脱敏测试通过
- [x] 2.3 统一 URI 处理规则：显式 `http(s)://` 与 `base64://` 保留，`file://` 与无 scheme 本地路径转换为 `base64://`，未知 scheme 本地失败；验证各类输入不会被静默下载或改投其他 Action
- [x] 2.4 让现有 group/private 文件上传路径复用 materialization 边界；验证 upload JSON 只包含 `file_uri`/`file_name` 等确认字段，并且本地文件请求使用 `base64://`

## 3. Outbound sender 多媒体实现

- [x] 3.1 将图片 URL、本地图片和动画接入 image segment 发送，保留 caption 与 segment 顺序；验证 group/dm 请求分别调用正确 message Action
- [x] 3.2 将语音和视频接入 record/video segment 发送，并将本地资源转换为 `base64://`；验证正常、空路径、超限和协议拒绝场景不发送文本 fallback
- [x] 3.3 保持文档附件走独立 `upload_group_file` / `upload_private_file`，不构造 file message segment；验证成功返回远端 `file_id`，失败保留原始分类且不二次发送
- [x] 3.4 复核多媒体、文件和分块发送的 cancellation、transport_unknown、部分成功和群失败刷新行为；验证每个可能产生副作用的 Action 最多调用一次

## 4. Hermes adapter 接线

- [x] 4.1 在 Milky adapter 覆盖 Hermes 的图片 URL、图片文件、动画、语音、视频和文档媒体入口，并委托给统一 outbound sender；验证运行时方法解析不再落入 Hermes 基类文本 fallback
- [x] 4.2 为 adapter 媒体入口复用连接/停止门禁；验证断开或停止后不读取文件、不访问网络、不调用 sender，并返回 `unsupported` 或等价安全错误
- [x] 4.3 验证 Hermes 基类批量图片和非图片媒体 dispatch 能调用 Milky adapter 的 native 方法；验证每个附件的 caption、目标和结果均保持独立

## 5. 端到端与安全回归

- [x] 5.1 组装 fake Hermes、Milky adapter、sender、client 和临时普通文件，覆盖 Agent 请求发送图片、语音、视频和文件；验证最终请求使用 base64/native segment 或独立 upload，用户不收到路径文本
- [x] 5.2 覆盖 group/dm、远端 URI、本地 URI、目标非法、资源不可读、大小超限、协议拒绝、非 JSON、超时和 transport_unknown；验证网络访问前失败、错误分类准确且不盲目重试
- [x] 5.3 增加日志和异常安全断言；验证不输出 token、Authorization、base64 内容、路径、文件名、完整异常、请求 body 或响应 body
- [x] 5.4 在不执行真实写入 Action 的前提下运行本地 HTTP/fake transport 集成回归；验证未使用真实 QQ、凭证、敏感正文或 live 文件

## 6. 文档与实现状态

- [x] 6.1 更新 `ARCHITECTURE.md` 出站边界和所有权说明，明确本地图片/语音/视频/文件暂使用 `base64://`、文件独立 upload、远端 URI 不由插件下载；验证文档不把规划能力写成已实现能力
- [x] 6.2 更新 `README.md` 能力矩阵和 Agent 使用说明，说明 Hermes `MEDIA:<path>` 交接、支持的资源类型、base64 内存/大小限制和失败分类；验证不泄露真实路径或凭证
- [x] 6.3 复核本 change 与既有 outbound-messaging、model-controlled replies 和 unknown-send-outcomes change 的重叠边界；验证 delta spec、design、tasks 与实际实现计划一致

## 7. 质量门禁与交付证据

- [x] 7.1 运行多媒体、client、outbound、adapter 生命周期和相关集成测试；记录每项失败的协议字段/路径、Hermes API、媒体资源、并发/顺序、权限/安全或测试基础设施分类
- [x] 7.2 运行 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`；将真实结果写入本 change 证据台账，不把未执行命令标记为通过
- [x] 7.3 运行 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`；验证本 change 的 requirement、scenario、design 和 tasks 一致，并记录未解决风险
- [x] 7.4 仅在取得独立明确授权后执行真实 Milky 写入 smoke；否则记录未执行发送/上传项，并确认 fake fixture 已覆盖本地 base64 出站路径

## 证据台账

- 本 change 未执行真实 Milky 写入 smoke：当前请求没有独立的写入授权；本地 base64 出站由 fake client 和本地 HTTP fixture 覆盖。
- 重叠复核结论：`add-milky-home-channel` 继续拥有目标解析，`add-model-controlled-milky-replies` 继续拥有结构化/CQ 文本语义，`harden-unknown-send-outcomes` 继续拥有未知结果和禁止 fallback；本 change 只接通 native 媒体、文件 upload 与本地 base64 materialization。
- `uv run pytest`：通过，348 passed、21 skipped；跳过原因归类为测试基础设施（当前 uv 环境未安装 HTTPX），未发现协议字段/路径、Hermes API、媒体资源、并发顺序或权限安全失败。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过。
- `uv build`：通过，生成 sdist 和 wheel。
- `git diff --check`：通过。
- `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`：通过，6 changes passed、0 failed；未解决风险为 base64 完整读入内存及服务端/代理大小限制，已固定 8 MiB 上限并在 README 与架构文档说明。
