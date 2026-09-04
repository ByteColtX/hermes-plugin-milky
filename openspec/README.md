# OpenSpec 规范

本仓库使用 OpenSpec 记录 Milky 适配器的可观察行为。OpenSpec 已按 Codex 的
skills-only 集成初始化到 `.agents/skills/openspec-*`，默认工作流为
`$openspec-propose`、`$openspec-apply-change`、`$openspec-sync-specs` 和
`$openspec-archive-change`。

## 当前状态

运行时适配器已经实现；当前代码、测试和文档覆盖 Milky HTTP Action、SSE、入站
pipeline、Will、资源边界、出站媒体/文件、固定 QQ ToolSpec 以及可选的 Milky system prompt
section。主规范位于
`openspec/specs/`，未归档的增量 change 位于 `openspec/changes/`。

当前未归档 change 的 proposal、design、delta spec 和 tasks 是各项变更的规划与
证据记录。proposal 中对“尚未实现”的描述是创建 change 时的范围说明，不能单独
替代当前代码和测试证据；同时，未归档 delta 尚未自动写入 `openspec/specs/`。
在实现和自动化证据完整后，才可以使用 `$openspec-sync-specs` 或
`$openspec-archive-change` 整理主规范和 change 历史。

任务状态以该 change 的 `tasks.md` 为唯一来源；依赖、验收、smoke 检查点、风险和
脱敏证据台账也维护在 `tasks.md` 中，不再维护独立的实施计划文件。

## 常用命令

```text
npx --yes @fission-ai/openspec@1.11.0 status --change <change-name>
npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict
$openspec-apply-change <change-name>
```

使用 `npx --yes` 是为了不要求开发环境预先全局安装 `openspec`；固定版本是为了避免
下次 OpenSpec CLI 升级导致验证行为或参数发生变化。`status` 一次检查一个 change，
`validate --changes` 检查全部 change；仍需保留固定的 CLI 版本。

不要把 token、个人 QQ、真实媒体 URL/路径或敏感正文写入 spec、fixture、日志
或提交。规范内容必须保持行为导向；实现细节放在 `design.md` 和代码中。
