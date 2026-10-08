"""验证 profile 间的贴纸与 Dashboard 文件隔离。"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from types import ModuleType

import pytest

from dashboard.host import ManagementError, storage_root
from dashboard.jobs import JobManager
from dashboard.uploads import UploadStore
from stickers.maintenance import StickerMaintenanceService
from stickers.management import StickerManagementService
from stickers.sending import StickerSendService
from stickers.storage import PLUGIN_NAME
from tests.test_dashboard_stream import Stream, body
from tests.test_dashboard_uploads import Upload
from tests.test_sticker_maintenance import _PNG


@contextmanager
def _profile_scope(active_home: ContextVar[Path], home: Path):
    """模拟 Hermes 的 task-local HERMES_HOME profile scope。"""
    token = active_home.set(home)
    try:
        yield
    finally:
        active_home.reset(token)


def _install_profile_storage_helpers(monkeypatch, active_home: ContextVar[Path]) -> None:
    """提供会按当前 profile 解析路径的 Hermes storage fake。"""
    hermes_constants = ModuleType("hermes_constants")
    hermes_constants.get_hermes_home = active_home.get  # type: ignore[attr-defined]
    plugins = ModuleType("plugins")
    plugins.__path__ = []  # type: ignore[attr-defined]
    plugin_storage = ModuleType("plugins.plugin_storage")

    def plugin_data_dir(name: str) -> Path:
        root = active_home.get() / "plugin-data" / name
        root.mkdir(parents=True, exist_ok=True)
        return root

    def plugin_db(name: str, *, filename: str) -> sqlite3.Connection:
        return sqlite3.connect(plugin_data_dir(name) / filename, check_same_thread=False)

    plugin_storage.plugin_data_dir = plugin_data_dir  # type: ignore[attr-defined]
    plugin_storage.plugin_db = plugin_db  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hermes_constants", hermes_constants)
    monkeypatch.setitem(sys.modules, "plugins", plugins)
    monkeypatch.setitem(sys.modules, "plugins.plugin_storage", plugin_storage)


def _visual_response() -> str:
    """返回一份只含合成贴纸元数据的视觉结果。"""
    return json.dumps(
        {
            "success": True,
            "analysis": json.dumps(
                {
                    "emotion": "joy",
                    "tags": ["开心", "反应"],
                    "description": "合成图片表达开心",
                    "is_sticker": True,
                },
                ensure_ascii=False,
            ),
        },
        ensure_ascii=False,
    )


def test_sticker_library_and_maintenance_follow_active_profile(tmp_path: Path, monkeypatch) -> None:
    """共享维护 service 每次打开的图库均取自当前 profile。"""
    active_home = ContextVar("active_profile_home", default=tmp_path / "unscoped")
    _install_profile_storage_helpers(monkeypatch, active_home)
    home_a = tmp_path / "profiles" / "a"
    home_b = tmp_path / "profiles" / "b"

    async def analyze(*, image_url: str, user_prompt: str) -> str:
        assert image_url.endswith("reaction.png")
        assert user_prompt
        return _visual_response()

    service = StickerMaintenanceService(
        plugin_context=object(),
        vision_analyzer=analyze,
    )

    root_a = home_a / "plugin-data" / PLUGIN_NAME
    inbox_a = root_a / "stickers" / "inbox"

    with _profile_scope(active_home, home_a):
        inbox_a.mkdir(parents=True)
        (inbox_a / "reaction.png").write_bytes(_PNG)
        added_a = asyncio.run(service.add())
        assert added_a["created"] == 1
        sticker_id_a = service.list()["items"][0]["sticker_id"]
        assert StickerSendService(plugin_context=object()).is_available() is True

    root_b = home_b / "plugin-data" / PLUGIN_NAME
    inbox_b = root_b / "stickers" / "inbox"
    with _profile_scope(active_home, home_b):
        assert service.list()["count"] == 0
        assert StickerSendService(plugin_context=object()).is_available() is False
        inbox_b.mkdir(parents=True, exist_ok=True)
        (inbox_b / "reaction.png").write_bytes(_PNG)
        added_b = asyncio.run(service.add())
        sticker_id_b = service.list()["items"][0]["sticker_id"]
        assert added_b["created"] == 1
        assert sticker_id_b != sticker_id_a

    with _profile_scope(active_home, home_a):
        assert service.list()["count"] == 1
        assert service.list()["items"][0]["sticker_id"] == sticker_id_a
        assert StickerSendService(plugin_context=object()).is_available() is True

    assert (root_a / "stickers.db").is_file()
    assert (root_b / "stickers.db").is_file()
    assert list((root_a / "stickers" / "library").rglob("*.png"))
    assert list((root_b / "stickers" / "library").rglob("*.png"))


def test_maintenance_resolves_hermes_vision_helper_in_active_profile(
    tmp_path: Path, monkeypatch
) -> None:
    """默认视觉入口按每次维护调用的 profile 解析，不捕获创建时作用域。"""

    active_home = ContextVar("visual_profile_home", default=tmp_path / "unscoped")
    _install_profile_storage_helpers(monkeypatch, active_home)
    tools = ModuleType("tools")
    tools.__path__ = []  # type: ignore[attr-defined]
    vision_tools = ModuleType("tools.vision_tools")
    calls: list[tuple[Path, Path, str]] = []

    async def analyze(*, image_url: str, user_prompt: str) -> str:
        calls.append((active_home.get(), Path(image_url), user_prompt))
        return _visual_response()

    vision_tools.vision_analyze_tool = analyze  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tools", tools)
    monkeypatch.setitem(sys.modules, "tools.vision_tools", vision_tools)
    service = StickerMaintenanceService(plugin_context=object())
    homes = [tmp_path / "profiles" / name for name in ("a", "b")]

    for home in homes:
        inbox = home / "plugin-data" / PLUGIN_NAME / "stickers" / "inbox"
        inbox.mkdir(parents=True)
        (inbox / "reaction.png").write_bytes(_PNG)
        with _profile_scope(active_home, home):
            assert asyncio.run(service.add())["created"] == 1

    assert [(home, path.parent) for home, path, _prompt in calls] == [
        (home, home / "plugin-data" / PLUGIN_NAME / "stickers" / "inbox") for home in homes
    ]
    assert all(prompt for _home, _path, prompt in calls)


def test_dashboard_jobs_and_upload_batches_use_confirmed_profile_roots(
    tmp_path: Path,
) -> None:
    """每个 Dashboard profile 只读取自己的任务库和上传批次。"""
    home_a = tmp_path / "profiles" / "a"
    home_b = tmp_path / "profiles" / "b"
    root_a = storage_root(home_a)
    root_b = storage_root(home_b)
    manager_a = JobManager(root_a)
    request_a = manager_a.issue("reindex")["request_id"]
    task_a = manager_a.submit(request_a, "reindex", {})["task_id"]

    manager_b = JobManager(root_b)
    assert manager_b.list() == {"items": []}
    request_b = manager_b.issue("reindex")["request_id"]
    task_b = manager_b.submit(request_b, "reindex", {})["task_id"]

    assert manager_a.root == root_a
    assert manager_b.root == root_b
    assert manager_a.root != manager_b.root
    assert [item["task_id"] for item in manager_a.list()["items"]] == [task_a]
    assert [item["task_id"] for item in manager_b.list()["items"]] == [task_b]

    result_a = asyncio.run(UploadStore(manager_a.root).receive([Upload(_PNG)]))
    result_b = asyncio.run(UploadStore(manager_b.root).receive([Upload(_PNG)]))
    batches_a = UploadStore(manager_a.root).list_batches()["items"]
    batches_b = UploadStore(manager_b.root).list_batches()["items"]
    assert [item["batch_id"] for item in batches_a] == [result_a["batch_id"]]
    assert [item["batch_id"] for item in batches_b] == [result_b["batch_id"]]
    assert result_a["batch_id"] != result_b["batch_id"]


def test_dashboard_stream_upload_limits_and_batches_are_profile_local(
    tmp_path: Path, monkeypatch
) -> None:
    """每个 profile 独立计算暂存配额，超限请求只清理自己的未完成批次。"""
    import dashboard.uploads as uploads_module

    root_a = storage_root(tmp_path / "profiles" / "a")
    root_b = storage_root(tmp_path / "profiles" / "b")
    monkeypatch.setattr(uploads_module, "QUOTA", len(_PNG))

    result_a = asyncio.run(UploadStore(root_a).receive_stream(Stream(body())))
    result_b = asyncio.run(UploadStore(root_b).receive_stream(Stream(body())))
    path_a, candidate_a = UploadStore(root_a).candidates(result_a["batch_id"], result_a["file_ids"])
    path_b, candidate_b = UploadStore(root_b).candidates(result_b["batch_id"], result_b["file_ids"])
    assert candidate_a[0][1].read_bytes() == _PNG
    assert candidate_b[0][1].read_bytes() == _PNG
    assert path_a != path_b

    monkeypatch.setattr(uploads_module, "MAX_IMAGE_BYTES", len(_PNG) - 1)
    monkeypatch.setattr(uploads_module, "QUOTA", 2 * len(_PNG))
    with pytest.raises(ManagementError) as caught:
        asyncio.run(UploadStore(root_b).receive_stream(Stream(body())))
    assert caught.value.status == "too_large"

    assert UploadStore(root_a).list_batches()["items"][0]["batch_id"] == result_a["batch_id"]
    assert UploadStore(root_b).list_batches()["items"][0]["batch_id"] == result_b["batch_id"]
    assert StickerManagementService(root_b).browse()["total"] == 0
