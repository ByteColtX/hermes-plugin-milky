# OpenSpec 规范

本仓库使用 OpenSpec 记录 Milky 适配器的可观察行为。OpenSpec 已按 Codex 的
skills-only 集成初始化到 `.agents/skills/openspec-*`，默认工作流为
`$openspec-propose`、`$openspec-apply-change`、`$openspec-sync-specs` 和
`$openspec-archive-change`。

## 当前状态

仓库仍是新建骨架，运行时适配器尚未实现。因此本次按 OpenSpec brownfield/增量
约定建立的 feature spec 全部位于：

`openspec/changes/specify-milky-adapter-contracts/specs/`

该目录下每个 capability 只有一个 `spec.md`。它们是待实现的 delta contracts，
不是已经归档的系统行为。完成对应的 T01-T20 实现、测试和必要的本地 Milky
smoke 后，才可以使用 `$openspec-sync-specs` 或 `$openspec-archive-change` 将
已经实现的能力写入 `openspec/specs/`。

任务状态以该 change 的 `tasks.md` 为唯一来源；依赖、验收、smoke 检查点、风险和
脱敏证据台账也维护在 `tasks.md` 中，不再维护独立的实施计划文件。

## 常用命令

```text
npx --yes @fission-ai/openspec@1.11.0 status --change specify-milky-adapter-contracts
npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict
$openspec-apply-change specify-milky-adapter-contracts
```

使用 `npx --yes` 是为了不要求开发环境预先全局安装 `openspec`；固定版本是为了避免
下次 OpenSpec CLI 升级导致验证行为或参数发生变化。若仓库存在多个 change，可将
`--changes` 改为具体 change 名称，但仍保留固定的 CLI 版本。

不要把 token、个人 QQ、真实媒体 URL/路径或敏感正文写入 spec、fixture、日志
或提交。规范内容必须保持行为导向；实现细节放在 `design.md` 和代码中。
