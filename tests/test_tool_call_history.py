"""工具调用历史的 fake host、边界回收与只读查询测试。"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

from tool_call_history import (
    HISTORY_FILENAME,
    MAX_RECORDS,
    ToolCallHistoryObserver,
    ToolCallHistoryStore,
    history_root,
    register_tool_call_history,
)


class HookContext:
    """只记录 hook 注册，不执行任何网络或后台动作。"""

    def __init__(self) -> None:
        self.hooks = []

    def register_hook(self, name, callback):
        self.hooks.append((name, callback))


def test_register_hook_is_declarative_and_does_not_create_storage(tmp_path: Path) -> None:
    """注册只保存 callback，不提前解析 profile 或创建数据库。"""

    context = HookContext()
    register_tool_call_history(context)
    assert [name for name, _callback in context.hooks] == ["post_tool_call"]
    assert list(tmp_path.rglob("*")) == []


def test_observer_filters_declared_tools_and_redacts_raw_values(tmp_path: Path) -> None:
    """非 Milky 工具不落库，参数只保留白名单摘要。"""

    observer = ToolCallHistoryObserver(profile_home_provider=lambda: tmp_path)
    assert (
        observer.observe(
            tool_name="terminal",
            args={"command": "secret text"},
            result="https://remote.invalid/private",
            error_message="private error detail",
            middleware_trace=[{"secret": "trace"}],
            duration_ms=8,
            status="ok",
        )
        is False
    )
    assert not (history_root(tmp_path) / HISTORY_FILENAME).exists()

    assert (
        observer.observe(
            tool_name="reject_friend_request",
            args={
                "initiator_uid": "synthetic-uid",
                "reason": "do not persist this text",
                "secret": "do not persist this value",
            },
            result='{"private": "result"}',
            error_message="do not persist this error",
            middleware_trace=[{"trace": "do not persist"}],
            duration_ms=12,
            status="error",
            error_type="ToolError",
        )
        is True
    )
    db_path = history_root(tmp_path) / HISTORY_FILENAME
    raw = db_path.read_bytes()
    assert b"do not persist" not in raw
    with sqlite3.connect(db_path) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(tool_calls)")]
        assert columns == [
            "record_id",
            "observed_at_utc",
            "duration_ms",
            "tool_name",
            "status",
            "error_type",
            "args_summary_json",
        ]
        row = connection.execute("SELECT * FROM tool_calls").fetchone()
    assert row[3:6] == ("reject_friend_request", "error", "unknown")
    summary = json.loads(row[6])
    assert summary == {
        "initiator_uid": {"provided": True},
        "reason": {"provided": True},
        "unknown_fields": {"provided": True},
    }


def test_profile_restart_retention_and_filter_statistics(tmp_path: Path) -> None:
    """重启可查、profile 隔离、筛选统计覆盖全部匹配记录。"""

    now = [datetime(2026, 1, 31, 12, tzinfo=UTC)]
    store_a = ToolCallHistoryStore(history_root(tmp_path / "a"), clock=lambda: now[0])
    store_b = ToolCallHistoryStore(history_root(tmp_path / "b"), clock=lambda: now[0])
    assert store_a.record("get_group_info", {"group_id": 900000001}, 10, "ok")
    assert store_a.record("get_group_info", {"group_id": 900000001}, 20, "ok")
    assert store_a.record("get_friend_info", {"user_id": 900000002}, 30, "error")
    assert store_b.record("get_group_info", {"group_id": 900000003}, 99, "ok")

    restarted = ToolCallHistoryStore(history_root(tmp_path / "a"), clock=lambda: now[0])
    result = restarted.query(tool_name="get_group_info", page=1, limit=1, profile_name="a")
    assert result["profile"] == "a"
    assert result["total"] == 2
    assert len(result["items"]) == 1
    assert result["summary"]["count"] == 2
    assert result["summary"]["total_duration_ms"] == 30
    assert result["summary"]["by_tool"] == {"get_group_info": 2}
    assert result["summary"]["by_status"] == {"ok": 2}
    assert restarted.query(profile_name="a")["total"] == 3
    assert ToolCallHistoryStore(history_root(tmp_path / "b")).query()["total"] == 1

    old = now[0] - timedelta(days=31)
    assert restarted.record("get_group_info", {"group_id": 900000004}, 1, "ok", observed_at=old)
    assert restarted.query()["total"] == 3


def test_write_failure_is_fail_open_for_tool_result(tmp_path: Path) -> None:
    """无法写入历史时只丢失观察记录，不改变原 Tool 回执。"""

    blocked_root = tmp_path / "blocked"
    blocked_root.write_text("synthetic", encoding="utf-8")
    store = ToolCallHistoryStore(blocked_root)
    result = '{"ok":true,"message_id":"synthetic"}'
    assert store.record("get_group_info", {"group_id": 900000001}, 1, "ok") is False
    assert result == '{"ok":true,"message_id":"synthetic"}'


def test_record_limit_removes_oldest(tmp_path: Path) -> None:
    """数量上限只回收当前 profile 的最早记录。"""

    now = [datetime(2026, 2, 1, tzinfo=UTC)]
    store = ToolCallHistoryStore(history_root(tmp_path), clock=lambda: now[0])
    for index in range(MAX_RECORDS + 1):
        assert store.record(
            "get_group_info",
            {"group_id": 900000000 + (index % 1000)},
            index,
            "ok",
            observed_at=now[0] + timedelta(milliseconds=index),
        )
    assert store.query(limit=1)["total"] == MAX_RECORDS


def test_missing_database_query_is_read_only(tmp_path: Path) -> None:
    """空 profile 查询不创建目录或数据库。"""

    root = tmp_path / "missing" / "plugin-data" / "hermes-plugin-milky"
    assert ToolCallHistoryStore(root).query()["items"] == []
    assert not root.exists()


def _install_dashboard_host(monkeypatch, homes: dict[str, Path]):
    """安装最小 profile 认证 fake，供 API 只读边界测试。"""

    active = {"name": "active"}

    class HTTPException(Exception):
        """模拟宿主 profile resolver 的拒绝。"""

    fastapi = ModuleType("fastapi")
    fastapi.HTTPException = HTTPException  # type: ignore[attr-defined]
    hermes_cli = ModuleType("hermes_cli")
    hermes_cli.__path__ = []  # type: ignore[attr-defined]
    plugins_cmd = ModuleType("hermes_cli.plugins_cmd")
    plugins_cmd._get_enabled_set = lambda: {"hermes-plugin-milky"}  # type: ignore[attr-defined]
    plugins_cmd._get_disabled_set = lambda: (  # type: ignore[attr-defined]
        {"hermes-plugin-milky"} if active["name"] == "disabled" else set()
    )
    profiles = ModuleType("hermes_cli.web_server_profiles")

    def resolve(name):
        if name not in homes:
            raise HTTPException("unknown profile")
        return homes[name]

    profiles._resolve_profile_dir = resolve  # type: ignore[attr-defined]

    @contextmanager
    def scope(name):
        previous = active["name"]
        active["name"] = name
        try:
            yield
        finally:
            active["name"] = previous

    profiles._config_profile_scope = scope  # type: ignore[attr-defined]
    constants = ModuleType("hermes_constants")
    constants.get_hermes_home = lambda: homes[active["name"]]  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fastapi", fastapi)
    monkeypatch.setitem(sys.modules, "hermes_cli", hermes_cli)
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins_cmd", plugins_cmd)
    monkeypatch.setitem(sys.modules, "hermes_cli.web_server_profiles", profiles)
    monkeypatch.setitem(sys.modules, "hermes_constants", constants)


def test_dashboard_history_is_authenticated_read_only_and_profile_local(
    tmp_path: Path, monkeypatch
) -> None:
    """历史 API 只读打开既有库，并拒绝未授权或伪造 profile。"""

    pytest.importorskip("fastapi")
    from dashboard.plugin_api import tool_call_history

    homes = {name: tmp_path / name for name in ("active", "other", "disabled")}
    _install_dashboard_host(monkeypatch, homes)
    store = ToolCallHistoryStore(history_root(homes["active"]))
    assert store.record("get_group_info", {"group_id": 900000001}, 11, "ok")

    result = asyncio.run(tool_call_history(profile="active", from_=None, to_=None))
    assert result["profile"] == "active"
    assert result["total"] == 1
    assert not (history_root(homes["other"]) / HISTORY_FILENAME).exists()

    empty = asyncio.run(tool_call_history(profile="other", from_=None, to_=None))
    assert empty["total"] == 0
    assert not history_root(homes["other"]).exists()

    disabled = asyncio.run(tool_call_history(profile="disabled", from_=None, to_=None))
    assert disabled.status_code == 404
    assert disabled.body == b'{"status":"disabled"}'
    unknown = asyncio.run(tool_call_history(profile="forged", from_=None, to_=None))
    assert unknown.status_code == 404
    assert unknown.body == b'{"status":"invalid_profile"}'


@pytest.mark.parametrize("page,limit", [(0, 20), (1, 0), (1, 101)])
def test_dashboard_history_rejects_unbounded_page_arguments(
    tmp_path: Path, page: int, limit: int
) -> None:
    """分页边界在读取前拒绝，不创建数据库。"""

    store = ToolCallHistoryStore(tmp_path / "missing")
    with pytest.raises(ValueError):
        store.query(page=page, limit=limit)
    assert not (tmp_path / "missing").exists()
