## 1. 契约与脱敏 fixture

- [ ] 1.1 建立合成的 `group:<id>`、`dm:<id>`、非法/临时目标、无 home 配置、系统通知和 cron 投递 fixture；验证 fixture 不含真实 QQ、token、Authorization、正文、媒体 URL、文件名或本地路径
- [ ] 1.2 建立 fake Hermes platform registry、live adapter、standalone cron 和 fake Milky transport；验证 `deliver=milky` 的 home 解析、显式目标优先级及两条投递路径使用同一安全结果形状
- [ ] 1.3 为启动通知、cron 成功/失败、Milky SSE 系统事件和未知事件建立隔离断言；验证 home channel 消息不会进入 canonical、Gate、Will、wait buffer 或 Hermes Agent turn

## 2. 配置与 manifest

- [ ] 2.1 扩展 `config/` 的启动配置，解析并校验可选 `MILKY_HOME_CHANNEL`；验证合法 `group:`/`dm:`、空值、额外分隔符、负数和非数字输入
- [ ] 2.2 将 home channel 纳入 `MilkyConfig` 和脱敏摘要，确保摘要只暴露是否配置而不输出目标 ID；验证配置只在启动解析一次且错误不回显 token 或原始环境值
- [ ] 2.3 更新 `plugin.yaml` 的 optional env 提示并保持三个显式 ToolSpec 不变；验证 manifest 只声明 `MILKY_HOME_CHANNEL` 而不声明额外 Action 或任意 catalog

## 3. Hermes registry 接入

- [ ] 3.1 在唯一根入口的 platform registration 中接入无网络的 home-channel env enablement、`cron_deliver_env_var="MILKY_HOME_CHANNEL"` 和 standalone sender hook；验证 import/register 阶段不建立 HTTP/SSE 连接或长期任务
- [ ] 3.2 将有效 home target 映射为 Hermes 可识别的 platform home metadata，并让宿主的 `deliver=milky` 发现该平台；用 fake `PluginContext`/registry 验证名称、目标、显示名和 cron hook 一致
- [ ] 3.3 验证 home metadata 与普通 adapter readiness 解耦：初始化同步未完成时普通 `message_receive` 仍被阻断，运行中修改环境变量不改变已解析目标

## 4. live home 与普通出站边界

- [ ] 4.1 让网关已解析的 home target 复用现有 `MilkyOutboundSender`，覆盖系统文本、长文本分块、结构化内容和独立 file upload；验证 `group:`/`dm:` 分别调用正确 Action、成功 ID 来自 `message_seq`
- [ ] 4.2 验证网关启动/重启、系统告警和 cron live 投递只经过出站 sender，不调用 inbound pipeline、Gate、Will、Hermes Agent 或插件侧 fallback；验证显式 cron target 优先于 home channel
- [ ] 4.3 验证 adapter 不读取空目标或 `home` 标记作为隐式 fallback；非法、temp、空目标和无 home target 均在网络访问前返回本地失败或 `unsupported`

## 5. standalone cron 投递

- [ ] 5.1 实现 registry `standalone_sender_fn` 的单次 Milky 文本投递，复用配置、目标解析、formatter、chunking、Action envelope 和稳定 SendResult；验证没有 live adapter 时仍可发送到 `group:`/`dm:` home target
- [ ] 5.2 接入 standalone 的媒体/文件参数边界，复用已有安全 materialization/upload 规则；没有 Hermes 安全输入 seam 时返回 `unsupported`，不直传本地路径、不自行下载 URL、不把 file 放入消息 segment
- [ ] 5.3 为 standalone 的成功、协议拒绝、非 JSON、HTTP 错误、超时、取消和资源关闭建立 fake transport 回归；验证每次调用关闭临时 HTTP 资源、未知执行结果不盲目重试且不泄露凭证

## 6. 系统事件安全与回归

- [ ] 6.1 更新系统事件处理边界，确认 home channel 仅接收 Hermes core/cron 的受信出站消息；验证 Milky recall、request、notice、lifecycle 和未知事件仍 observe-only，不自动转发或授予 Action 权限
- [ ] 6.2 覆盖 home 投递的 `rejected`、`transport_unknown`、`malformed`、`unsupported` 和无目标错误；验证不会伪造成功、改投其他目标、改变 MuteTracker 或触发普通 Agent turn
- [ ] 6.3 扫描日志、异常、SendResult、fixture 和快照的敏感字段；验证不包含 token、Authorization、未脱敏 ID、完整正文、媒体 URL、文件名或本地路径

## 7. 文档与架构状态

- [ ] 7.1 更新 `ARCHITECTURE.md` 的配置、系统拓扑/所有权和扩展边界，明确 `MILKY_HOME_CHANNEL`、live/standalone cron 投递及其不进入入站 pipeline 的边界
- [ ] 7.2 更新 `README.md` 的环境变量、Hermes home-channel/cron 使用方式和能力矩阵；明确未配置时不回退、写入 smoke 仍需运行时凭证与明确授权
- [ ] 7.3 对照本 change 的 proposal、所有 delta spec 和实现结果复核，不把计划中的 standalone 或系统投递描述成尚未完成的能力

## 8. 质量门禁与证据台账

- [ ] 8.1 运行配置、manifest、registry、outbound、standalone 和安全定向测试，并记录每项失败的协议字段/路径、Hermes API、并发/顺序、权限/安全、媒体资源、真实环境或测试基础设施分类
- [ ] 8.2 运行 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`；确认结果写入本文件证据台账且不把未执行命令宣称为通过
- [ ] 8.3 运行 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`，验证 home-channel 新 capability 与 configuration、outbound-messaging、plugin-lifecycle、system-events-and-safety delta 的 requirement/scenario/tasks 一致
- [ ] 8.4 如需本地 Milky smoke，仅使用运行时注入的 `MILKY_BASE_URL`/`MILKY_ACCESS_TOKEN` 和脱敏输出；未经明确授权不执行发送、上传、撤回或其他改变测试环境的 Action，并记录未执行项

## 9. 执行证据台账

| 阶段 | 命令/证据 | 结果 | 反馈分类与下一步 |
|---|---|---|---|
| 规划 | 已读取 `AGENTS.md`、`ARCHITECTURE.md`、现有 active OpenSpec change 全部 artifacts、相关主 spec，以及 Hermes host 的 home-channel/cron plugin interface | 待实施阶段补充 | 范围限定为 Milky home channel 系统/cron 出站，不修改 Hermes core，不把 Milky 入站系统事件转发到 home |
| fixture/实现 | 待实现后填写配置、registry、live/standalone、系统事件隔离和安全 fixture/test 证据 | 待实施 | 每个任务按“fixture/契约 → 实现 → 测试 → 质量门禁 → 必要 smoke → 反馈分类 → 回归修复”闭环 |
| 质量门禁 | 待运行定向/全量 pytest、Ruff、format、build、diff check 和 OpenSpec strict validation | 待实施 | 未运行的命令保持未确认，不以 HTTP 200 或 fake 成功替代协议结果 |
| 真实环境 | 当前未执行 Milky 写入 Action | 待实施 | 仅在明确授权后使用运行时凭证；不保存真实身份、token、正文、媒体路径、URL、message ID 或原始响应 |
