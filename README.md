# hermes-plugin-milky

Hermes 的 Milky QQ platform directory plugin。Hermes 通过 GitHub 仓库目录发现插件，
不依赖 Python package entry point。

## 安装

```bash
hermes plugins install ByteColtX/hermes-plugin-milky
```

安装器读取仓库根目录的 `plugin.yaml`，并加载根目录
`__init__.py::register(ctx)`。`tools.py::register_tools(ctx)` 是显式 Agent 工具的发现
边界；当前工具业务和 Milky 适配器仍在 OpenSpec change 中逐步实现。

## 入口布局

```text
plugin.yaml       # Hermes directory plugin manifest
__init__.py       # 唯一公开注册入口
tools.py          # 显式工具发现入口
adapter.py        # 后续实现的 platform adapter
```

本项目不使用 `hermes_plugin_milky/__init__.py`，也不声明 Hermes Python entry point；
`pyproject.toml` 仅用于 uv 开发环境和质量检查。

当前 manifest 不声明 Agent 工具：`tools.py` 仅保留安全的发现边界，三个 ToolSpec
将在对应的出站能力实现并完成测试后再加入 manifest。
