## 1. 契约与测试基础

- [ ] 1.1 根据 NapCat 消息格式文档补充全部 CQ 类型、组合控制码、未知/转换失败原样 fallback、隐式 reply anchor、真实 ID 来源和 bundled skill 的脱敏契约 fixture，并验证 fixture 不包含凭证、真实身份或敏感正文
- [ ] 1.2 为 `platform_hint` 增加稳定中文文案测试，验证文案包含 `[CQ:at,qq=<uid>]`、`[CQ:reply,id=<msg_id>]`、默认不自动 @/引用和 skill 命名空间，同时不包含逐轮 ID 或敏感字段；更多 CQ 类型和 fallback 规则在 skill fixture 中验证
- [ ] 1.3 更新 `ARCHITECTURE.md` 的协议边界，明确 CQ-compatible 语法只存在于 Agent 出站适配层，不改变 Milky wire protocol 或 OneBot 能力声明，并通过文档/差异检查

## 2. CQ-compatible 出站解析

- [ ] 2.1 在出站 formatter 中实现通用 CQ 形态 `[CQ:<name>,<key>=<value>,...]` 的严格边界解析，覆盖 NapCat 文档列出的全部 CQ 类型，保留控制码前后文本和出现顺序；通过完整类型矩阵和组合输入单元测试
- [ ] 2.2 建立按 CQ 类型选择转换器的 registry：确认映射时生成 Milky native segment，`file` 等不能进入 message segment 的类型遵守既有 upload 边界，未知或没有确认映射的类型生成包含原始 CQ 字符串的 text segment；通过转换成功、未映射和转换异常测试
- [ ] 2.3 将 CQ 解析接入普通文本分块和结构化出站路径，确保控制码不会在分块边界被截断；malformed、缺失参数、非十进制 ID、非法范围或转换失败均保留对应原文并继续发送，通过混合内容、空白和无损 fallback 测试
- [ ] 2.4 验证现有 native Milky segment、文件 upload、group/dm 路由和远端 `message_seq` 行为不受 CQ 解析改动影响，运行相关 outbound 回归测试

## 3. 取消隐式引用与宿主边界回归

- [ ] 3.1 调整 Milky adapter 的普通 Agent 回复交接，使 Hermes 提供的隐式当前消息 `reply_to` 不再自动生成 reply segment；通过无控制码、显式 reply 和显式 at 加隐式 anchor 的测试验证
- [ ] 3.2 验证一次出站交接最多调用一次 Milky send，且 CQ malformed/unknown/转换失败只触发原样 text fallback，远端拒绝和 `transport_unknown` 不触发宿主通用 retry、plain-text fallback 或第二次发送；通过 adapter 边界 fake transport 回归测试
- [ ] 3.3 验证 CQ 控制码转换后 group/dm 请求 body 分别包含准确的 Milky mention/reply segment，并验证真实 `uid`/`msg_id` 值原样传递且缺失值不被伪造

## 4. bundled QQ reference skill

- [ ] 4.1 创建 `skills/qq-reference/SKILL.md` 模板，完整列出 NapCat 文档 CQ 类型、每项 native/fallback 状态、Milky segment 映射、原样放行规则、三个现有 QQ ToolSpec 的边界和后续待办，并验证模板不把 text fallback 或未注册工具写成已执行能力
- [ ] 4.2 在根插件注册入口通过 `ctx.register_skill()` 登记 `qq-reference`，保持插件命名空间、只读属性和用户全局 skills 隔离；验证注册阶段无网络、无长期任务和无全局文件写入
- [ ] 4.3 增加 skill 按命名空间加载、同名隔离、缺失 skill 文件和无 `register_skill` 宿主兼容分支的测试，并验证实际 ToolSpec 仍是工具可用性与参数校验的唯一依据

## 5. 集成验证与交付

- [ ] 5.1 增加 fake Hermes/fake Milky 端到端回归，覆盖普通文本、只 @、只引用、同时 @/引用、历史 `channel_context`、当前消息、隐式 anchor 和 Agent 忙碌交接不重复发送
- [ ] 5.2 更新 README 或相关能力矩阵，说明 CQ-compatible 语法、skill 按需加载方式、native conversion 与原样 fallback 的区别；验证文档不宣称 OneBot/Milky 任意 Action 兼容
- [ ] 5.3 运行 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check` 和 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`，记录失败分类、修复后的最小回归和最终结果
