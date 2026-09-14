# OpenSpec

本目录按 [OpenSpec](https://github.com/Fission-AI/OpenSpec) 管理插件的行为规范和功能变更。

## 模型

- `specs/`：当前系统行为的事实来源。
- `changes/`：一个变更的提案、delta spec、设计和任务。
- `changes/archive/`：已完成变更的历史；归档时 delta spec 合并到 `specs/`。

## 工作流

官方流程是“先达成共识，再实现”：

```text
explore → propose → apply → sync/archive
```

本项目 Codex skill 的调用名如下；`openspec ...` 在终端运行，`$openspec-*` 在 AI
对话中运行：

```text
$openspec-explore
$openspec-propose <change-name>
$openspec-apply-change <change-name>
$openspec-update-change <change-name>
$openspec-sync-specs <change-name>
$openspec-archive-change <change-name>
```

## Change 文件

```text
changes/<change-name>/
├── proposal.md   # 为什么改、改什么
├── specs/        # ADDED/MODIFIED/REMOVED 的 delta
├── design.md     # 如何实现
└── tasks.md      # 实施清单
```

变更可以随时迭代。规范描述可观察行为和具体场景，不描述实现细节。

## 校验

```text
openspec status --change <change-name>
openspec validate --changes --strict
openspec validate --specs --strict
```

参考：[Getting Started](https://github.com/Fission-AI/OpenSpec/blob/main/docs/getting-started.md) ·
[Overview](https://github.com/Fission-AI/OpenSpec/blob/main/docs/overview.md) ·
[CLI](https://github.com/Fission-AI/OpenSpec/blob/main/docs/cli.md)
