"""验证贴纸命令文本、静态帮助及业务与展示隔离。"""

import asyncio
from types import SimpleNamespace

import pytest

from slash_commands import SlashCommandService
from stickers import presentation
from stickers.maintenance import StickerMaintenanceService, parse_sticker_command
from tests.test_sticker_maintenance import _PNG, _vision


@pytest.mark.parametrize("count", [0, 1, 2])
@pytest.mark.parametrize("raw", ["sticker", "sticker help", "STICKER HELP"])
def test_sticker_help_does_not_open_any_dependency(tmp_path, count, raw):
    """帮助在任意实例数量及缺失图库下都不触及工厂。"""

    def forbidden(*args, **kwargs):
        pytest.fail("静态帮助不应访问外部依赖")

    stickers = StickerMaintenanceService(
        data_dir=tmp_path / "missing",
        data_dir_factory=forbidden,
        store_factory=forbidden,
        db_factory=forbidden,
        vision_analyzer=forbidden,
    )
    service = SlashCommandService(stickers)
    for _ in range(count):
        service.bind_client(SimpleNamespace(get_impl_info=forbidden))
        service.bind_status_provider(SimpleNamespace(status=forbidden))
        service.bind_manager(SimpleNamespace(handle=forbidden))
    assert asyncio.run(service.handle(raw)) == presentation.HELP
    assert not list(tmp_path.iterdir())
    assert presentation.HELP.count("\n  /milky sticker ") == 3


@pytest.mark.parametrize(
    ("raw", "verb"),
    [
        ("sticker unknown-secret", None),
        ("sticker help secret", "help"),
        ("sticker add secret", "add"),
        ("sticker list --limit 101", "list"),
        ("sticker list --limit secret", "list"),
        ("sticker edit demo_id", "edit"),
        ("sticker edit demo_id --emotion=JOY", "edit"),
        ("sticker edit demo_id --tags=开心,安慰 --clear=tags", "edit"),
        ("sticker reanalyze", "reanalyze"),
        ("sticker del /secret/path", "del"),
        ("sticker remove", "del"),
        ("sticker cleanup secret", "cleanup"),
        ("sticker reindex secret", "reindex"),
    ],
)
def test_invalid_sticker_syntax_is_local_and_safe(raw, verb):
    """全部动词错误均在存储和视觉前返回已知语法。"""

    def forbidden():
        pytest.fail("格式错误不应打开业务依赖")

    service = StickerMaintenanceService(store_factory=forbidden)
    result = asyncio.run(service.handle(raw))
    assert result.startswith("指令格式不正确。\n\nUsage:\n  /milky sticker ")
    assert result.endswith("\n\nHelp:\n  /milky sticker help")
    if verb:
        assert f"  /milky sticker {presentation.SYNTAX[verb]}\n" in result
    assert "secret" not in result


@pytest.mark.parametrize("verb", ["del", "remove", "REMOVE"])
def test_alias_uses_one_delete_with_same_result(tmp_path, monkeypatch, verb):
    """不同拼写从同一初始库出发只删除一次且回执一致。"""
    inbox = tmp_path / "stickers" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "synthetic.png").write_bytes(_PNG)
    service = StickerMaintenanceService(
        data_dir=tmp_path, vision_analyzer=lambda *_args, **_kwargs: _vision()
    )
    added = asyncio.run(service.add())
    sticker_id = added["items"][0]["sticker_id"]
    original = service._delete
    calls = []

    def delete(store, target):
        calls.append(target)
        return original(store, target)

    monkeypatch.setattr(service, "_delete", delete)
    result = asyncio.run(service.handle(f"sticker {verb} {sticker_id}"))
    assert result == f"已移除贴纸\nID: {sticker_id}"
    assert calls == [sticker_id]
    assert service.list()["count"] == 0


@pytest.mark.parametrize("suffix", ["", " ../secret", " demo_missing"])
def test_alias_errors_are_identical(tmp_path, suffix):
    """缺参、非法 ID 和不存在条目的结果不因别名改变。"""
    service = StickerMaintenanceService(data_dir=tmp_path)
    assert asyncio.run(service.handle("sticker del" + suffix)) == asyncio.run(
        service.handle("sticker remove" + suffix)
    )


def item(sticker_id="demo_id"):
    """返回包含必要字段及禁止扩展字段的合成业务条目。"""
    return {
        "sticker_id": sticker_id,
        "emotion": "joy",
        "tags": ["开心", "反应"],
        "description": "小图表达情绪",
        "source": "manual",
        "field_sources": {"emotion": "vision", "tags": "manual", "description": "vision"},
        "format": "PNG",
        "size_bytes": 68,
        "created_at": "2026-01-01T00:00:00+00:00",
        "use_count": 3,
        "last_used_at": None,
        "path": "/secret/path",
        "url": "https://secret",
        "raw": "secret-response",
        "error": "secret-exception",
        "file_sha256": "secret-hash",
    }


def test_list_keeps_order_metadata_sources_and_actual_return_count():
    """列表只展示返回条数，保留逐字段来源与现有统计。"""
    second = item("demo_second")
    second["last_used_at"] = "2026-01-02T00:00:00+00:00"
    result = presentation.render("list", {"status": "ok", "count": 99, "items": [item(), second]})
    assert "本次显示 2 条" in result and "99" not in result
    assert result.index("ID: demo_id") < result.index("ID: demo_second")
    for value in (
        "喜悦 (joy)",
        "人工 (manual)",
        "视觉 (vision)",
        "使用次数: 3",
        "尚未使用",
        "2026-01-02T00:00:00+00:00 UTC",
        "大小: 68 字节",
        "格式: PNG",
    ):
        assert value in result
    assert "secret" not in result
    empty = presentation.render("list", {"status": "ok", "items": []})
    assert "尚未添加贴纸。" in empty and "本次显示 0 条" in empty
    assert "/milky sticker help" in empty


@pytest.mark.parametrize("status", list(presentation.FAILURES))
def test_single_failure_text_never_leaks_extensions(status):
    """未知提交不声称未执行，已保留条目的分类独立说明。"""
    result = presentation.render("reanalyze", {"status": status, **item()})
    assert result == presentation.FAILURES[status]
    assert "secret" not in result
    if status == "storage_error":
        assert "先核验" in result and "未执行" not in result


@pytest.mark.parametrize("status", ["ok", "storage_error", "missing_file"])
def test_mixed_add_retains_success_ids_and_all_categories(status):
    """顶层可读结果或部分存储失败都不能吞掉已提交项。"""
    result = presentation.render(
        "add",
        {
            "status": status,
            "created": 3,
            "duplicate": 2,
            "junk": 4,
            "rejected": 1,
            "visual_unavailable": 1,
            "storage_error": 1,
            "batch_deferred": 2,
            "items": [{"status": "created", "sticker_id": "demo_id", "path": "secret"}],
        },
    )
    assert result.startswith("贴纸导入部分完成")
    for value in (
        "已添加: 3",
        "重复图片: 2",
        "非贴纸隔离文件: 4",
        "视觉分析失败: 1",
        "存储失败: 1",
        "延后处理: 2",
        "已添加 ID: demo_id",
        "未完成项",
    ):
        assert value in result
    assert "secret" not in result


def test_add_preview_preserves_candidates_and_never_claims_execution():
    """两类候选保留受限元数据与判定，不显示文件 hash 或虚构 ID。"""
    result = presentation.render(
        "add",
        {
            "status": "ok",
            "created": 0,
            "items": [
                {**item(), "status": "would_add"},
                {**item(), "status": "would_move_to_junk"},
            ],
        },
        dry_run=True,
    )
    assert result.startswith("贴纸导入预览") and result.endswith("未作更改。")
    assert "待添加: 1" in result and "待隔离: 1" in result
    assert "候选 1: 待添加\n贴纸判定: 是" in result
    assert "候选 2: 待隔离\n贴纸判定: 否" in result
    assert result.count("描述: 小图表达情绪") == 2
    assert "ID:" not in result and "secret" not in result and "已添加:" not in result
    empty = presentation.render("add", {"status": "ok", "created": 0, "items": []})
    assert "没有待处理的图片。" in empty and "导入完成" not in empty


@pytest.mark.parametrize("operation", ["cleanup", "reindex"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_file_operations_preserve_units_and_unfinished_results(operation, dry_run):
    """文件计数与缺失条目不合计，预览不冒充已清理。"""
    if operation == "reindex" and dry_run:
        return
    result = presentation.render(
        operation,
        {
            "status": "ok",
            "orphan": 2,
            "temporary": 3,
            "indexed": 5,
            "missing_file": 1,
            "reindex_skipped": 4,
        },
        dry_run=dry_run,
    )
    assert "缺失引用条目: 1" in result and "跳过文件: 4" in result
    assert "本次没有恢复缺失文件" in result
    if dry_run:
        assert result.startswith("贴纸清理预览") and result.endswith("未作更改。")
        assert "待清理未引用文件: 2" in result and "已清理" not in result
    else:
        assert "部分完成" in result


def test_help_values_match_parser():
    """帮助公布的枚举与参数示例都可被解析。"""
    from stickers.maintenance import EMOTIONS

    assert set(presentation.EMOTION_NAMES) == EMOTIONS
    for emotion in EMOTIONS:
        assert parse_sticker_command(f"sticker edit demo_id --emotion={emotion}").sets == {
            "emotion": emotion
        }
    assert parse_sticker_command("sticker add --dry-run").dry_run
    assert parse_sticker_command("sticker edit demo_id --clear=tags").clears == {"tags"}
