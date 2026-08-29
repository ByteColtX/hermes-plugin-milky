<!-- omit in toc -->
# Contributing to hermes-plugin-milky

感谢你为 hermes-plugin-milky 贡献时间！❤️

本仓库是 Hermes 的 Milky QQ 平台适配器，目前仍处于新建骨架阶段。开始贡献前，
请先阅读 [ARCHITECTURE.md](ARCHITECTURE.md)；它是协议、模块边界和行为的唯一事实来源。
当前 OpenSpec change 位于
[`openspec/changes/specify-milky-adapter-contracts/`](openspec/changes/specify-milky-adapter-contracts/)，
其中的 `tasks.md` 是实现进度和任务状态的唯一来源。

我们欢迎 bug 报告、协议 fixture、测试、代码和文档改进。请根据目录阅读相关章节，
这样可以减少来回确认，也能让贡献更容易被复现和审查。🎉

如果暂时没有时间贡献代码，也欢迎通过以下方式支持项目：

- Star 项目；
- 在项目或文章中引用 hermes-plugin-milky；
- 向可能需要 Milky/Hermes 适配器的开发者介绍本项目。

<!-- omit in toc -->
## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [I Have a Question](#i-have-a-question)
- [I Want To Contribute](#i-want-to-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Enhancements](#suggesting-enhancements)
  - [Your First Code Contribution](#your-first-code-contribution)
  - [Improving The Documentation](#improving-the-documentation)
- [Styleguides](#styleguides)
  - [Commit Messages](#commit-messages)
- [Join The Project Team](#join-the-project-team)


## Code of Conduct

请尊重所有参与者，使用建设性的语言进行讨论，并遵守项目维护者提出的协作要求。若遇到
不可接受的行为，请联系 <umk@live.com>。


## I Have a Question

> 提问前，请先阅读 [ARCHITECTURE.md](ARCHITECTURE.md) 和
> [OpenSpec 工作说明](openspec/README.md)。

提问前，请先搜索已有的 [Issues](https://github.com/ByteColtX/hermes-plugin-milky/issues)。
如果已有 issue 与问题相关，优先在原 issue 中补充信息；否则再新建 issue。

提问时请尽量提供：

- 使用的 commit、Python 版本和 `uv` 版本；
- 最小复现步骤、预期结果和实际结果；
- 相关的 Milky/Hermes 配置项名称（不要提供 token 值）。

请不要在 issue、日志或截图中粘贴 `MILKY_ACCESS_TOKEN`、Authorization header、个人 QQ、
真实媒体路径或敏感消息正文。

## I Want To Contribute

> ### Legal Notice <!-- omit in toc -->
> 贡献内容前，请确认你拥有相应权利，并同意该内容可以按照项目许可证发布。

### Reporting Bugs

<!-- omit in toc -->
#### Before Submitting a Bug Report

好的 bug 报告应当让其他人能够独立复现问题。提交前请先收集信息，并尽量缩小复现范围：

- 使用当前代码和最新依赖复现，并注明 commit、Python 版本和 `uv` 版本；
- 阅读 [ARCHITECTURE.md](ARCHITECTURE.md)，并搜索已有的
  [bug issues](https://github.com/ByteColtX/hermes-plugin-milky/issues?q=label%3Abug)；
- 提供操作系统、运行命令、最小复现步骤、预期结果和实际结果；
- 提供必要的 traceback、输入和输出，但移除 token、个人 QQ、媒体路径和敏感正文。

<!-- omit in toc -->
#### How Do I Submit a Good Bug Report?

> 不要在 issue 或其他公开渠道披露包含敏感信息的安全问题、漏洞或 bug。请将安全问题发送至
> <umk@live.com>。

我们使用 GitHub issues 跟踪 bug：

- 新建一个 [Issue](https://github.com/ByteColtX/hermes-plugin-milky/issues/new)；
- 说明预期行为与实际行为；
- 提供他人可以照着执行的复现步骤和最小测试用例；
- 附上前一节收集的环境信息和安全的日志片段。

提交后，维护者会根据复现情况标记和处理 issue。若暂时无法复现，可能会请求补充步骤或将其
标记为 `needs-repro`；确认问题后再安排修复。

### Suggesting Enhancements

本节用于提交 hermes-plugin-milky 的功能建议，包括新能力和现有行为的改进。建议必须符合
`ARCHITECTURE.md` 的边界；如果涉及行为变化，请同时说明需要更新的 OpenSpec capability
或新增的 change。

<!-- omit in toc -->
#### Before Submitting an Enhancement

- 确认问题在当前代码或 active OpenSpec change 中尚未被覆盖；
- 仔细阅读 [ARCHITECTURE.md](ARCHITECTURE.md) 和相关 OpenSpec spec，确认建议没有违反既定边界；
- 搜索已有的 [Issues](https://github.com/ByteColtX/hermes-plugin-milky/issues)，已有建议请在原 issue 中补充；
- 说明建议是否属于 Milky v0.1 范围。高风险 Action、WebHook、`MILKY_HOME_CHANNEL`、
  temp 出站和插件自有媒体缓存等能力需要单独设计，不能直接作为小改动加入。

<!-- omit in toc -->
#### How Do I Submit a Good Enhancement Suggestion?

功能建议请提交为 [GitHub issue](https://github.com/ByteColtX/hermes-plugin-milky/issues/new)，并提供：

- 清晰、描述性强的标题；
- 当前行为、期望行为以及变更动机；
- 可执行的步骤、示例或脱敏 fixture；
- 对大多数 hermes-plugin-milky 用户的价值，以及已考虑过的替代方案。

### Your First Code Contribution

#### 开发环境

- Python 3.13 或更高版本；
- [uv](https://docs.astral.sh/uv/)；
- Git。

本项目只使用 `uv` 管理 Python 环境和依赖，不要使用 `pip`、`pipx` 或直接调用
`python`/`python3`。基本设置如下：

```text
git clone https://github.com/ByteColtX/hermes-plugin-milky.git
cd hermes-plugin-milky
uv sync
```

#### 开发流程

1. 阅读 `ARCHITECTURE.md` 和当前 OpenSpec change 的全部 artifacts，尤其是 `tasks.md`。
2. 选择下一个未完成的 T01–T20 任务；先补充契约或脱敏 fixture，再实现最小行为。
3. 为新增行为补充单元、集成或协议 fixture 测试，并在 `tasks.md` 中记录可复现证据。
4. 运行质量检查后再提交 PR：

```text
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
git diff --check
```

当前适配器尚未完整实现；不要把 `ARCHITECTURE.md` 或 OpenSpec 中的目标行为描述成已经交付的
功能。必要的本地 Milky smoke test 只能从运行时环境读取凭证，不能把凭证或真实敏感数据写入仓库。

代码应遵循 Google Python Style Guide，保持类型明确、模块职责单一，并遵守 `milky/`、`inbound/`、
`gates/`、`will/`、`session/`、`state/` 和 `outbound/` 的依赖边界。协议和生命周期改动应同时
补充 fake transport、fake Hermes 或 Milky fixture 测试。

### Improving The Documentation

文档改动应以 `ARCHITECTURE.md` 和 active OpenSpec change 为依据。请：

- 修正过时、含糊或与实现不符的描述，并明确标注尚未实现的目标行为；
- 协议行为变化同步更新对应的 OpenSpec spec 和必要的 fixture 说明；
- 不在文档、示例或截图中放入 token、Authorization header、个人 QQ、真实媒体路径和敏感正文；
- 检查 Markdown 链接、代码示例和 `git diff --check`。

## Styleguides
### Commit Messages
提交消息遵循 Conventional Commits，subject 和 body 全部使用中文。格式为：

```text
<type>(<scope>): <简短摘要>

<说明修改动机的可选正文>
```

`type` 使用 `feat`、`fix`、`refactor`、`perf`、`docs`、`test`、`chore`、`ci`、`build`、
`style` 或 `revert`；subject 使用祈使语气、无句号且不超过 72 个字符。正文应解释为什么修改，
而不是重复文件改动；适用时在 footer 引用 issue。

示例：

```text
docs(contributing): 补充本地开发和质量检查说明
```

## Join The Project Team

目前没有单独的项目团队申请流程。持续贡献高质量 issue、fixture、测试、代码或文档后，可以在
相关 PR 或 issue 中说明你希望长期参与维护；维护者会根据贡献范围和协作情况联系你。一般贡献
请直接提交 issue 或 pull request，并在描述中说明变更范围、验证命令和未解决风险。

安全问题不要公开提交到 issue，请发送至 <umk@live.com>。

<!-- omit in toc -->
## Attribution
This guide is based on the [contributing.md](https://contributing.md/generator)!
