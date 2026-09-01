## 1. 契约与脱敏 fixture

- [x] 1.1 定义四类附件的合成 Hermes materialization 结果，覆盖 kind、可用 URI、文档文件名、空值、未确认本地路径和 text-only turn；验证 fixture 不包含真实路径、凭证、完整媒体内容或 live 响应
- [x] 1.2 建立 group/dm 的图片、语音、视频 message Action 与文件 upload Action 请求/响应 fixture；验证请求方法、目标、segment/upload 边界、调用次数和稳定结果 ID
- [x] 1.3 建立 fake Hermes host dispatch fixture，模拟同一 Agent turn 按顺序提供图片、语音、视频和文件 materialization；验证附件不会被误判为普通文本或互相转换

## 2. Hermes materialization 交接

- [x] 2.1 在 plugin 边界增加本地路径、`Path`、`file://localhost`、远端 URI 和显式 Base64 的统一校验；验证常规文件、空文件、8 MiB 上限、未知 scheme 和远端 file URI 的分类
- [x] 2.2 在 plugin materializer 中恢复一次本地读取和 `base64://` 编码，删除对 Hermes outbound materialization seam 的运行时依赖；验证 adapter 未连接时不读取资源、不访问网络、不调用 sender
- [x] 2.3 复核 adapter、sender 和 file uploader 只转发生成的 URI 及必要文件名；验证不会把本地路径、完整异常、URI 或资源内容写入结果和日志

## 3. Native media 与文件出站

- [x] 3.1 恢复图片、语音和视频的 native segment 发送；验证 group 使用 `send_group_message`、dm 使用 `send_private_message`，segment 类型、URI、caption 和附件顺序正确
- [x] 3.2 保持文档走独立文件上传；验证 group 使用 `upload_group_file`、dm 使用 `upload_private_file`，请求包含确认的 URI 和文件名且不包含 file message segment
- [x] 3.3 实现多附件有序交接和部分失败结果；验证每个可能产生副作用的 Action 最多调用一次，保留已成功数量和首个失败位置，不执行 plain-text fallback 或盲目重试
- [x] 3.4 保持 text-only turn 的普通文本路径；验证没有附件 materialization 时只调用普通文本 Action，不猜测媒体、不调用 upload

## 4. 回归与宿主集成验证

- [x] 4.1 增加实际 Hermes `BasePlatformAdapter` dispatch 回归（宿主源码可用时）；验证当前 host 传入本地路径后仍解析到 native plugin 方法并完成本地 materialization，宿主不可用时记录 `blocked` 证据而不是标记能力通过
- [x] 4.2 增加 Agent 文件枚举到逐项附件发送的集成 fixture；验证 Agent 产生附件调用时出现对应 native/upload 事件，单纯 `/usr/bin/bash: python: command not found` 或 text-only 响应不会被伪装成媒体发送成功
- [x] 4.3 覆盖 adapter 未连接、目标非法、资源未确认、协议拒绝、非 JSON、超时和 `transport_unknown`；验证错误分类原样保留且不会产生第二次可能有副作用的 Action
- [x] 4.4 增加日志和异常安全断言；验证不输出 token、Authorization、URI 内容、base64 数据、本地路径、敏感正文、完整异常或请求/响应 body

## 5. 文档、迁移与质量门禁

- [x] 5.1 更新 `ARCHITECTURE.md`、`README.md` 和 OpenSpec 证据台账，明确 plugin-owned materialization、native/upload 映射和 `61d99fc` 回归背景；验证文档不依赖未实现的 Hermes host seam
- [x] 5.2 在当前 Hermes runtime 上执行真实 host dispatch、fake Milky 和 local HTTP 回归；验证本地附件不再返回 seam 缺失，并且失败不执行用户可见 fallback
- [x] 5.3 运行媒体、sender、adapter、outbound 和集成测试，并执行 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`；将失败按协议、Hermes API、媒体、并发、权限或测试基础设施分类
- [x] 5.4 执行 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`；验证 change 的 proposal、delta spec、design 和 tasks 一致，并记录真实 Milky 写入 smoke 未授权时未执行
- [x] 5.5 明确 Agent 使用 `send_message` 的 `MEDIA:<local_path>` 发送本地媒体，避免将固定 QQ ToolSpec 列表误判为完整出站能力；增加平台提示、工具说明和入口回归断言

## Evidence ledger

| 阶段 | 命令/证据 | 结果 | 反馈分类与下一步 |
|---|---|---|---|
| 规划 | 已读取 `AGENTS.md`、`ARCHITECTURE.md`、本 change 的 `proposal.md`、delta spec、`design.md`、`tasks.md`，并只读检查 `hermes-dev` 中实际 Hermes host、历史 plugin commit 和部署日志 | 已完成 | 范围重构为 plugin-owned 的受限本地 materialization；不修改 Hermes core，不下载远端 URI，不创建持久化媒体缓存 |
| fixture/实现 | `uv run pytest tests/test_multimedia_outbound.py tests/test_protocol_fixtures.py tests/test_outbound.py -q`；相关 Ruff check | 87 passed, 1 skipped；fixture、Path/file URI/边界校验、native segment、独立 upload、text-only、顺序和部分失败回归通过 | 协议和安全边界通过；本地路径由 plugin 受限读取并生成 `base64://`，无 Hermes outbound seam 依赖 |
| Hermes host 回归 | `HERMES_SOURCE_ROOT=/Users/bytecolt/PythonProjects/hermes-agent uv run --with pyyaml pytest tests/test_multimedia_outbound.py::test_actual_hermes_multiple_image_dispatch_uses_inherited_entries -q -rs`；`orb -m hermes-dev` 只读检查部署 plugin 与 `/home/bytecolt/.hermes/hermes-agent/gateway/platforms/base.py` | 1 passed；实际 BasePlatformAdapter 继承/覆盖解析通过，当前 host 直接传本地路径，部署 plugin 含本地 materializer；未执行写入 Action | 已确认 `61d99fc` 的 seam 边界回归已由 plugin-owned materialization 修正；不修改 Hermes core |
| 集成与安全 | fake Hermes Agent 文件枚举、shell 错误/text-only、非法目标前置校验、本地读取/文件名边界、协议拒绝/非 JSON/超时/transport unknown 和日志脱敏回归 | 通过；每个可能产生副作用的 Action 最多调用一次，无路径、URI、base64、凭证、完整异常或 body 泄露；plugin 不实现 fallback | 分类为媒体/权限/协议安全回归已覆盖；未知远端执行结果不重试、不 fallback |
| 质量门禁 | `uv run pytest -q`；`uv run ruff check .`；`uv run ruff format --check .`；`uv build`；`git diff --check` | `509 passed, 22 skipped`；ruff check 通过；format 通过（191 files）；build 成功；diff check 通过 | 无协议、Hermes API、媒体、并发、权限或测试基础设施失败 |
| OpenSpec | `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict` | `1 passed, 0 failed` | proposal、delta spec、design、tasks 一致 |
| 真实环境 | 已在 `orb -m hermes-dev` 只读检查实际 plugin、host 方法和部署路径；fake Milky 与 local HTTP fixture 已执行 | 证实当前 host 仍传本地路径；部署 plugin 已包含本地读取和 Base64 编码；未执行 Milky 写入/上传 smoke | 分类为已确认的 plugin 媒体回归且已完成代码级修正；真实视频发送仍需用户明确授权后再观察 native Action |
| Agent 能力提示 | `uv run pytest -q tests/test_plugin_entry.py`；静态检查 `PLATFORM_HINT`、`skills/qq-tools/SKILL.md`、README 和架构说明 | 通过：平台提示明确普通最终回复和 `send_message` 两种 `MEDIA:<local_path>` 入口，并明确不以 QQ ToolSpec 清单推断媒体能力 | 修复 Agent 能力发现歧义；未改变 ToolSpec 数量、Milky Action 或安全边界 |
