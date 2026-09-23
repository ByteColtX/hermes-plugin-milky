# 验证证据

## 已验证行为

- 本地合成输入已复现修复前的提及名称误触发与兴趣倍率问题。
- 规范化区分展示正文和可匹配连续文本；三类关键词共用同一片段边界。
- fake host 流水线覆盖仅名称含关键词时等待、不补资源、不交接、不扣费；正文命中时正常触发且历史和当前的提及展示保留。
- self mention 合成配置验证：名称命中时得分 30，普通文本命中时得分 60；独立 mention force 仍绕过随机抽样。
- 兴趣关键词未命中时保留原有基础增益；流水线合成配置验证得分为 10，而非关键词倍率后的 20。

## 检查记录

- 相关既有测试：118 passed。
- 新增关键词边界用例：17 passed，覆盖名称、QQ 号、全体提及、手输文本、Markdown、相邻文本、非文本隔断、引用内容、self mention 与空区间。
- 最终全量 uv run pytest -q -rs：970 passed，3 skipped。
- uv run ruff check .、uv run ruff format --check .、git diff --check 通过；新增文件曾有一处格式问题，自动格式化后复查通过。
- OpenSpec 未归档 changes 严格校验：5 passed。

## 验证范围

仅本地合成事件、fixture 与 fake host；未连接真实 QQ 或执行发送。3 项 skip 分别因为 Hermes host 不可用、真实集成未显式启用、媒体测试缺少 Hermes host。真实 Hermes/Milky 集成仍未验证。
