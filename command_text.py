"""提供命令帮助与格式错误的共用纯文本约定。"""


def format_usage(syntax: str, help_command: str) -> str:
    """只使用固定语法生成就近错误提示，不回显用户输入。"""
    return f"指令格式不正确。\n\nUsage:\n  {syntax}\n\nHelp:\n  {help_command}"
