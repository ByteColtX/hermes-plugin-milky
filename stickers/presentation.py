"""把已验证维护结果转换为命令文本，不读取或修改业务状态。"""

from command_text import format_usage

SYNTAX = {
    "add": "add [--dry-run]",
    "list": "list [--limit <n>]",
    "edit": "edit <sticker_id> [--emotion=<enum>] [--tags=<tag1>,<tag2>,...] "
    "[--description=<text>] [--clear=<field>[,<field>...]]",
    "reanalyze": "reanalyze <sticker_id>",
    "del": "del <sticker_id>",
    "cleanup": "cleanup [--dry-run]",
    "reindex": "reindex",
    "help": "help",
}
EMOTION_NAMES = {
    "joy": "喜悦",
    "sadness": "悲伤",
    "anger": "愤怒",
    "surprise": "惊讶",
    "fear": "害怕",
    "disgust": "厌恶",
    "love": "喜爱",
    "approval": "赞同",
    "confusion": "困惑",
    "neutral": "中性",
    "mixed": "混合",
    "unknown": "未知",
}
HELP = """Milky · 贴纸维护

Usage:
  /milky sticker [command] [args...]

Commands:
  add [--dry-run]  导入图片
  list [--limit <n>]  查看贴纸
  edit <sticker_id> [--emotion=<enum>] [--tags=<tag1>,<tag2>,...] [--description=<text>] [--clear=<field>[,<field>...]]  编辑字段
  reanalyze <sticker_id>  重新分析
  del <sticker_id>  移除贴纸（别名 remove）
  cleanup [--dry-run]  清理库文件
  reindex  重建技术索引
  help  显示帮助

Options:
  --dry-run  仅适用于 add/cleanup；只预览，未作更改。
  --limit <n>  默认 20，十进制整数 1 至 100；也接受 --limit=<n>。
  --emotion=<enum>  joy、sadness、anger、surprise、fear、disgust、love、approval、confusion、neutral、mixed、unknown
  --tags=<tag1>,<tag2>,...  2 至 5 个不重复标签，每个不超过 16 字符且含中文。
  --description=<text>  非空、不超过 20 字符且含中文，不跨空白 token；不支持 shell 引号语法。
  --clear=<field>[,<field>...]  恢复 emotion、tags、description 对应视觉基线。
  edit 至少指定一个 set/clear；同一字段不能同时设置和清除，不接受重复选项或清除字段。

Examples:
  /milky sticker add --dry-run
  /milky sticker edit demo_id --clear=tags

不带子命令时显示帮助。"""

FAILURES = {
    "sticker_not_found": "贴纸不存在\n\n请查看贴纸列表并确认条目 ID。",
    "missing_file": "贴纸文件缺失\n\n本次没有恢复文件；重建索引不能恢复图片。",
    "not_sticker": "本次未更新贴纸\n\n本次分析判定为非贴纸，已保留原条目。",
    "visual_unavailable": "贴纸分析暂不可用\n\n本次分析未能完成，已保留原条目。",
    "conflict": "更改未保存\n\n条目已发生变化，请确认最新状态后再操作。",
    "storage_error": "贴纸维护未完成\n\n无法确认全部结果，请先核验当前状态后再操作。",
    "unsupported": "贴纸维护暂不可用\n\n请检查插件存储支持。",
}


def usage_for(raw_args: str) -> str:
    """从固定动词选择安全语法，不回显 ID 或非法值。"""
    parts = raw_args.split() if isinstance(raw_args, str) else []
    verb = parts[1].lower() if len(parts) > 1 else ""
    verb = "del" if verb == "remove" else verb
    syntax = SYNTAX.get(verb, "<add|list|edit|reanalyze|del|cleanup|reindex|help>")
    return format_usage(f"/milky sticker {syntax}", "/milky sticker help")


def _metadata(item: dict) -> list[str]:
    """仅展示业务层已经限制的视觉字段。"""
    emotion = item.get("emotion", "unknown")
    if emotion not in EMOTION_NAMES:
        emotion = "unknown"
    tags = item.get("tags", [])
    return [
        f"情绪: {EMOTION_NAMES[emotion]} ({emotion})",
        "标签: " + "、".join(tags),
        f"描述: {item.get('description', '')}",
    ]


def _source(value) -> str:
    """保留可复制来源值和中文含义。"""
    return {"manual": "人工 (manual)", "vision": "视觉 (vision)"}.get(value, "未知")


def _list(result: dict) -> str:
    """保留稳定返回顺序、元数据与统计，不查询全库数量。"""
    items = result.get("items", [])
    lines = ["Milky · 贴纸维护", "", f"本次显示 {len(items)} 条"]
    if not items:
        return "\n".join([*lines, "", "尚未添加贴纸。", "", "Help:", "  /milky sticker help"])
    for item in items:
        fields = item.get("field_sources", {})
        lines.extend(["", f"ID: {item['sticker_id']}", *_metadata(item)])
        lines.extend(
            [
                f"来源: {_source(item.get('source'))}",
                "字段来源: "
                + "、".join(
                    f"{label}={_source(fields.get(field))}"
                    for field, label in (
                        ("emotion", "情绪"),
                        ("tags", "标签"),
                        ("description", "描述"),
                    )
                ),
                f"格式: {item.get('format', '未知')}",
                f"大小: {item.get('size_bytes', '未知')} 字节",
                f"创建时间: {item.get('created_at', '未知')} UTC",
                f"使用次数: {item.get('use_count', 0)}",
                "最近使用: "
                + (f"{item['last_used_at']} UTC" if item.get("last_used_at") else "尚未使用"),
            ]
        )
    return "\n".join(lines)


def _add(result: dict, dry_run: bool) -> str:
    """按独立分类展示批次，顶层失败仍保留已完成部分。"""
    status = result.get("status")
    items = result.get("items", [])
    incomplete = status != "ok" or any(
        result.get(key, 0)
        for key in ("rejected", "visual_unavailable", "storage_error", "batch_deferred")
    )
    title = "贴纸导入预览" if dry_run else ("贴纸导入部分完成" if incomplete else "贴纸导入完成")
    empty = (
        not items
        and not any(
            result.get(key, 0)
            for key in (
                "created",
                "duplicate",
                "junk",
                "rejected",
                "visual_unavailable",
                "storage_error",
                "batch_deferred",
            )
        )
        and status == "ok"
    )
    if empty and not dry_run:
        title = "贴纸导入结果"
    lines = [title, ""]
    if dry_run:
        lines.extend(
            [
                f"待添加: {sum(item.get('status') == 'would_add' for item in items)}",
                f"待隔离: {sum(item.get('status') == 'would_move_to_junk' for item in items)}",
            ]
        )
    else:
        lines.extend(
            [f"已添加: {result.get('created', 0)}", f"非贴纸隔离文件: {result.get('junk', 0)}"]
        )
    lines.extend(
        f"{label}: {result.get(key, 0)}"
        for key, label in (
            ("duplicate", "重复图片"),
            ("rejected", "拒绝图片"),
            ("visual_unavailable", "视觉分析失败"),
            ("storage_error", "存储失败"),
            ("batch_deferred", "延后处理"),
        )
    )
    if empty:
        lines.extend(["", "没有待处理的图片。"])
    for index, item in enumerate(items, 1):
        if item.get("status") == "created":
            lines.extend(["", f"已添加 ID: {item['sticker_id']}"])
        elif dry_run and item.get("status") in {"would_add", "would_move_to_junk"}:
            sticker = item["status"] == "would_add"
            lines.extend(
                [
                    "",
                    f"候选 {index}: {'待添加' if sticker else '待隔离'}",
                    f"贴纸判定: {'是' if sticker else '否'}",
                    *_metadata(item),
                ]
            )
    if status == "missing_file":
        lines.extend(["", "存在缺失的库文件，本次没有恢复文件。"])
    if status == "storage_error" or result.get("storage_error", 0):
        lines.extend(["", "无法确认全部存储结果，请先核验当前状态后再操作。"])
    if incomplete:
        lines.extend(["", "存在未完成项；请核验拒绝或存储失败的候选。"])
    if result.get("visual_unavailable", 0) or result.get("batch_deferred", 0):
        lines.append("视觉失败和延后的候选仍待处理。")
    if dry_run:
        lines.extend(["", "未作更改。"])
    return "\n".join(lines)


def _files(operation: str, result: dict, dry_run: bool) -> str:
    """清理和重建索引保持文件与条目计数单位，不合计。"""
    incomplete = any(result.get(key, 0) for key in ("missing_file", "reindex_skipped"))
    if operation == "cleanup":
        title = (
            "贴纸清理预览" if dry_run else ("贴纸清理部分完成" if incomplete else "贴纸清理完成")
        )
        action = "待清理" if dry_run else "已清理"
        fields = (("orphan", f"{action}未引用文件"), ("temporary", f"{action}临时文件"))
    else:
        title = "贴纸索引重建部分完成" if incomplete else "贴纸索引重建完成"
        fields = (("indexed", "已索引文件"), ("orphan", "未引用文件"))
    lines = [title, ""]
    lines.extend(f"{label}: {result.get(key, 0)}" for key, label in fields)
    lines.extend(
        [
            f"缺失引用条目: {result.get('missing_file', 0)}",
            f"跳过文件: {result.get('reindex_skipped', 0)}",
        ]
    )
    if incomplete:
        lines.extend(["", "存在缺失或跳过项，本次没有恢复缺失文件。"])
    if not any(result.get(key, 0) for key, _label in fields):
        lines.extend(["", "没有可处理的文件。"])
    if dry_run:
        lines.extend(["", "未作更改。"])
    return "\n".join(lines)


def render(operation: str, result: dict, *, dry_run: bool = False) -> str:
    """仅格式化一次已获得的业务结果，不重试或补查。"""
    status = result.get("status")
    if operation == "add" and "created" in result:
        return _add(result, dry_run)
    if status == "ok":
        if operation == "list":
            return _list(result)
        if operation in {"cleanup", "reindex"}:
            return _files(operation, result, dry_run)
    titles = {"updated": "已更新贴纸", "reanalyzed": "已重新分析贴纸", "deleted": "已移除贴纸"}
    if status in titles:
        return f"{titles[status]}\nID: {result['sticker_id']}"
    return FAILURES.get(status, FAILURES["storage_error"])
