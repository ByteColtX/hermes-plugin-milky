## 1. 配置契约和 manifest

- [ ] 1.1 在 `config/` 增加 `MILKY_PROACTIVE_POLICY` 的结构化配置对象、默认值和严格 JSON 校验；覆盖 `enabled`、`idleSeconds`、`maxAttemptsPerDay`、`quietHours`、未知字段、跨午夜时间和非法输入，并用 `uv run pytest -q tests/test_config.py` 验证
- [ ] 1.2 更新 `plugin.yaml`、配置摘要和配置主规范所需的可观察说明；验证 manifest 只增加一个 optional JSON 环境变量且不出现独立 `chats`、`cooldown`、`timezone` 配置

## 2. 主动唤醒状态和候选选择

- [ ] 2.1 新增插件侧 idle-session policy/tracker，保存每个 chat 的人工 activity epoch、已接受注入标记、Hermes 本地日期和每日 accepted injection 计数；用可注入时钟验证默认两小时、同一 epoch 单次、人工消息重新武装和进程内状态边界
- [ ] 2.2 实现从 Hermes `list_sessions()` 读取既有 Milky `group:<id>`/`dm:<id>` route 的候选解析；验证只接受已存在且已有确认 session key 的条目、精确/命名空间白名单命中、空白名单 fail-closed、temp/未知 origin 跳过且不调用 session 创建
- [ ] 2.3 实现 Hermes Core 时区下的 quiet hours 和每日次数判断；验证 `null` 关闭免扰、跨午夜窗口、免扰不消耗次数、拒绝注入不计数和次数耗尽跳过

## 3. watcher 生命周期和安全交接

- [ ] 3.1 在 adapter ready 后通过 `PluginContext.spawn_task()` 启动固定低频 watcher，并在 disconnect、重连和插件卸载时取消、等待和去重；用 fake context/stream 验证未 ready 不启动、最多一个 task、停止后不再扫描
- [ ] 3.2 接入普通入站 pipeline 的人工 activity recorder，确保 Gate deny、system event、主动 synthetic turn 和 Agent 出站结果不重新武装；用 group/dm pipeline 测试验证 activity 边界
- [ ] 3.3 在主动注入前增加 Hermes busy、确认 session key 和 `MuteTracker` 状态检查；验证运行中/状态未知/群禁言时跳过，dm 不读取群状态，busy 能力未知时 fail-closed
- [ ] 3.4 通过已有 `inject_message()` 交接固定 `<event idle_session_wakeup>` 英文文案，并只在宿主返回 `true` 后标记 epoch、增加每日计数；验证拒绝/异常保留未接受状态，接受后 `[SILENT]` 与现有 outbound 流程闭环且不直接调用 Milky Action

## 4. 文档和稳定边界

- [ ] 4.1 更新 `README.md` 的 JSON 配置示例、默认关闭语义、白名单范围、夜间免扰、每日次数、Hermes 时区复用和 `[SILENT]` 文案说明；验证示例与配置测试字段一致
- [ ] 4.2 更新 `ARCHITECTURE.md` 的插件 watcher、session ownership、生命周期清理、busy/mute fail-closed 和 Hermes Core 不修改边界；验证文档不宣称插件创建 session 或拥有 Agent 队列
- [ ] 4.3 将已验证行为同步到对应主 specs，保留本 change delta 与实现状态边界；验证主 specs、README、ARCHITECTURE 和本 change 中的默认值、事件名与固定英文 body 一致

## 5. 回归和质量门禁

- [ ] 5.1 运行配置、tracker、adapter lifecycle、pipeline 和 fake injection 聚焦测试，覆盖 group/dm、白名单、闲置、quiet hours、maxAttemptsPerDay、busy、mute、拒绝和重连清理；验证 `uv run pytest -q tests/test_config.py tests/test_adapter_lifecycle.py tests/test_hermes_pipeline.py`
- [ ] 5.2 运行完整质量门禁并记录结果：`uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check` 和 `openspec validate --changes --strict`
