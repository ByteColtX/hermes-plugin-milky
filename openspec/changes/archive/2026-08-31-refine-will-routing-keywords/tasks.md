## 1. 契约与 fixture

- [x] 1.1 更新 routing 默认值、公开 schema 和配置示例，使用 `allMessage` 与空的
  `keywords`，并验证旧的 `group`、`image`、`mentionHere` 字段会被拒绝且不会建立网络连接
- [x] 1.2 补充脱敏策略 fixture 和测试输入，覆盖 friend/group、self mention、全体提及、
  quote、关键词命中、空关键词和图片消息不再拥有独立 routing 分支；以断言 OR 合并结果和
  配置错误分类验证完成

## 2. Routing 实现

- [x] 2.1 调整 routing 配置解析与值域校验，支持 `direct`、`mention`、`mentionAll`、
  `quote`、`poke`、`allMessage` 和 `keywords`，并保留非空字符串数组的类型校验；以配置
  单元测试和完整嵌套策略 round-trip 断言完成
- [x] 2.2 将 routing 决策改为无优先级 OR 合并：评估所有适用规则，任一 `trigger` 即
  `trigger`，否则 `wait`；使 `allMessage` 匹配每条普通 `message_receive`，并使任意
  关键词子串命中产生确定性 `trigger`；以 routing 单元测试覆盖多信号和等待/触发组合
- [x] 2.3 保持 poke/nudge 的 observe-only 边界，并确认 routing keywords 不调用随机源、
  willingness、网络、文件系统或资源补全；以副作用探针和系统事件回归测试验证

## 3. 集成与迁移

- [x] 3.1 更新入站流水线相关测试，验证图片 segment 仍被正常解析和延迟处理，但 routing
  只使用 allMessage、其他保留信号和关键词结果；以 fake Milky/fake Hermes pipeline 测试
  验证无额外 Action 调用
- [x] 3.2 更新 README、plugin manifest 和配置错误文档中的 routing 示例与 breaking migration
  说明；以全文搜索确认不再公开旧 routing 字段，且未误删 inbound image 或 willingness
  imageGain 契约

## 4. 质量门禁

- [x] 4.1 运行 `uv run pytest tests/test_config.py tests/test_will_routing.py
  tests/test_hermes_pipeline.py tests/test_normalizer.py`，确认新增 routing 和兼容性回归
  全部通过
- [x] 4.2 运行 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、
  `uv build` 和 `git diff --check`，记录每项命令的可复现结果
- [x] 4.3 运行 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`，
  确认本 change 的 proposal、两份 delta spec 与 tasks 完整且通过严格校验；该策略变更
  不需要 Milky live smoke

## 证据台账

- `uv run pytest tests/test_config.py tests/test_will_routing.py tests/test_hermes_pipeline.py tests/test_normalizer.py`：77 passed。
- `uv run pytest`：478 passed，22 skipped。
- `uv run pytest tests/test_plugin_entry.py`：13 passed，包含旧 routing 字段在网络访问前被拒绝的入口回归。
- `uv run ruff check .`：All checks passed。
- `uv run ruff format --check .`：176 files already formatted。
- `uv build`：成功生成 source distribution 和 wheel。
- `git diff --check`：通过，无空白错误。
- `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`：1 change passed，0 failed。
- 本 change 只调整本地 routing 配置与决策，不需要 Milky live smoke；未使用外部凭证或网络 Action。
