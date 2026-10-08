"""在隔离的真实 Hermes 中验证当前 Milky API，只使用合成图片和 profile 数据。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import importlib.util
import io
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path


class SyncASGIClient:
    """在稳定事件循环上发起 ASGI 请求，不启动无关的 Hermes Dashboard 生命周期。"""

    def __init__(self, app, headers):
        import httpx

        self._loop = asyncio.new_event_loop()
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers=headers,
            timeout=30,
        )

    def __enter__(self):
        self._loop.run_until_complete(self._client.__aenter__())
        return self

    def __exit__(self, *_):
        self._loop.run_until_complete(self._client.aclose())
        self._loop.close()

    def request(self, method, url, **kwargs):
        return self._loop.run_until_complete(self._client.request(method, url, **kwargs))

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


def _plugin_dependency_overlays(home):
    """建立只指向本次临时 PM 插件环境的导入别名。"""
    site_packages = sorted(
        path
        for path in home.glob("installs/*/environments/*/venv/lib/python*/site-packages")
        if (path / "jieba").is_dir()
    )
    overlays = []
    for index, site_path in enumerate(site_packages):
        overlay = home / "probe-host-plugin-deps" / f"env-{index}"
        overlay.parent.mkdir(parents=True, exist_ok=True)
        if overlay.exists() or overlay.is_symlink():
            if not overlay.is_symlink() or overlay.resolve() != site_path.resolve():
                raise RuntimeError("unexpected probe dependency overlay")
        else:
            overlay.symlink_to(site_path, target_is_directory=True)
        overlays.append(overlay)
    return overlays


def check(home, set_stage):
    """真实宿主认证与 profile API；不连接 QQ 或真实视觉供应商。"""
    set_stage("import_dashboard_dependencies")
    from hermes_cli.plugins import get_plugin_manager
    from hermes_cli.web_server import _get_dashboard_plugins, app
    from hermes_cli.web_server_profiles import _config_profile_scope
    from PIL import Image

    probe_package_name = "_milky_dashboard_probe_stickers"
    probe_package = types.ModuleType(probe_package_name)
    probe_package.__path__ = [str(Path(__file__).resolve().parents[1] / "stickers")]
    sys.modules[probe_package_name] = probe_package
    sticker_store_class = importlib.import_module(f"{probe_package_name}.storage").StickerStore
    max_image_bytes = importlib.import_module(f"{probe_package_name}.validation").MAX_IMAGE_BYTES

    set_stage("prepare_profile_plugin_hosts")
    plugin_hosts = []
    for profile in ("alpha", "beta"):
        with _config_profile_scope(profile):
            plugin_host = get_plugin_manager()._plugin_host()
            plugin_hosts.append(plugin_host)
            set_stage(f"start_{profile}_plugin_host", plugin_hosts=plugin_hosts)
            original_shutdown = plugin_host.shutdown

            def snapshot_before_shutdown(
                host=plugin_host,
                profile_name=profile,
                stop=original_shutdown,
                stage=set_stage,
            ):
                process = host._proc
                channel = host._channel
                reason = channel.closed_reason if channel is not None else None
                stage(
                    f"start_{profile_name}_plugin_host",
                    host_child_running=process is not None and process.poll() is None,
                    host_child_exit_code=process.poll() if process is not None else None,
                    host_channel_closed=reason is not None,
                    host_channel_close_kind=(
                        "read_failed"
                        if reason and "channel read failed" in reason
                        else "write_failed"
                        if reason and "channel write failed" in reason
                        else "closed"
                        if reason
                        else "open"
                    ),
                )
                stop()
                stage(
                    f"start_{profile_name}_plugin_host",
                    host_child_exit_code_after_shutdown=(
                        process.poll() if process is not None else None
                    ),
                )

            plugin_host.shutdown = snapshot_before_shutdown
            plugin_host.ensure_started()
    set_stage("profile_plugin_hosts_ready", plugin_hosts=plugin_hosts)

    set_stage("seed_synthetic_gallery")
    image = io.BytesIO()
    Image.new("RGB", (32, 32), (90, 140, 210)).save(image, format="PNG")
    image_payload = image.getvalue()
    data_root = home / "profiles" / "alpha" / "plugin-data" / "hermes-plugin-milky"
    with sticker_store_class(data_dir=data_root) as store:
        file_sha256 = hashlib.sha256(image_payload).hexdigest()
        image_path = store.paths.library_path(file_sha256, ".png")
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(image_payload)
        now = "2026-10-08T00:00:00+00:00"
        store.connection.execute(
            "DELETE FROM sticker_send_usage WHERE sticker_id = ?", ("synthetic-sticker",)
        )
        store.connection.execute(
            "DELETE FROM sticker_items WHERE sticker_id = ?", ("synthetic-sticker",)
        )
        store.connection.execute("DELETE FROM sticker_files WHERE sha256 = ?", (file_sha256,))
        store.connection.execute(
            "INSERT INTO sticker_files(sha256, relative_path, mime_type, size_bytes, verified_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                file_sha256,
                image_path.relative_to(data_root).as_posix(),
                "image/png",
                len(image_payload),
                now,
            ),
        )
        store.connection.execute(
            "INSERT INTO sticker_items(sticker_id, file_sha256, format, mime_type, size_bytes, "
            "detected_emotion, detected_tags_json, detected_description, emotion, tags_json, "
            "description, emotion_source, tags_source, description_source, created_at, updated_at, "
            "detected_at, use_count, last_used_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "synthetic-sticker",
                file_sha256,
                "png",
                "image/png",
                len(image_payload),
                "joy",
                json.dumps(["测试", "合成"], ensure_ascii=False),
                "合成贴纸",
                "joy",
                json.dumps(["测试", "合成"], ensure_ascii=False),
                "合成贴纸",
                "vision",
                "vision",
                "vision",
                now,
                now,
                now,
                0,
                None,
            ),
        )
        store.connection.commit()
    headers = {"X-Hermes-Session-Token": "synthetic-test-session"}
    base = "/api/plugins/hermes-plugin-milky"
    results = {
        "milky_dashboard_manifest_discovered": any(
            row.get("name") == "hermes-plugin-milky" for row in _get_dashboard_plugins()
        ),
        "dashboard_api_alias_used": bool(getattr(check, "dashboard_api_alias_used", False)),
        "host_plugin_dependency_overlay_used": bool(
            getattr(check, "host_plugin_dependency_overlay_used", False)
        ),
    }
    set_stage("create_hermes_asgi_client")
    with SyncASGIClient(app, headers) as client:

        def request(method, path, *, profile="alpha", **kwargs):
            stage = f"{method.lower()}_{path.split('?')[0].strip('/').replace('/', '_')}"
            set_stage(stage)
            response = client.request(
                method,
                base + path,
                params={"profile": profile},
                headers=headers,
                timeout=30,
                **kwargs,
            )
            set_stage(stage, http_status=response.status_code)
            return response

        def job(operation, payload):
            issued = request("POST", "/requests", json={"operation": operation}).json()
            body = {"operation": operation, "request_id": issued["request_id"], "payload": payload}
            accepted = request("POST", "/jobs", json=body)
            assert accepted.status_code == 200
            task_id = accepted.json()["task_id"]
            assert request("POST", "/jobs", json=body).json()["task_id"] == task_id
            for _ in range(100):
                rows = request("GET", "/jobs").json()["items"]
                row = next(x for x in rows if x["task_id"] == task_id)
                if row["status"] not in {"queued", "running"}:
                    return row
                time.sleep(0.01)
            raise AssertionError("task did not finish")

        config_response = request("GET", "/config")
        results["proxy_config_status"] = config_response.status_code
        if config_response.status_code != 200:
            results["status"] = "blocked"
            results["blocker"] = (
                "dashboard_plugin_api_not_mounted"
                if config_response.status_code == 404
                else "dashboard_proxy_request_rejected"
            )
            return results
        results["proxy_route_available"] = True
        config = config_response.json()
        results["incomplete_setup_readable"] = config["has_access_token"] is False
        response = request(
            "PATCH",
            "/config",
            json={
                "version": config["version"],
                "changes": {"base_url": "http://127.0.0.1:4000", "session_buffer_size": 0},
            },
        )
        results["settings_saved"] = response.json()["status"] == "saved"
        results["stale_version_refused"] = (
            request(
                "PATCH",
                "/config",
                json={"version": config["version"], "changes": {"session_buffer_size": 2}},
            ).status_code
            == 409
        )
        results["secret_replaced"] = (
            request(
                "POST", "/credential", json={"action": "replace", "value": "synthetic-api-secret"}
            ).json()["status"]
            == "saved"
        )
        results["secret_not_exposed"] = "synthetic-api-secret" not in request("GET", "/config").text
        results["secret_blank_kept"] = (
            request("POST", "/credential", json={"action": "replace", "value": ""}).json()["status"]
            == "unchanged"
        )
        results["secret_cleared"] = (
            request("POST", "/credential", json={"action": "clear"}).json()["status"] == "saved"
        )
        results["profile_isolated"] = (
            request("GET", "/config", profile="beta").json()["effective"]["base_url"] == ""
        )
        results["forged_profile_refused"] = (
            request("GET", "/gallery", profile="../alpha").status_code == 400
        )
        gallery = request("GET", "/gallery")
        results["profile_gallery_request"] = (
            gallery.status_code == 200 and gallery.json()["total"] == 1
        )
        results["other_profile_gallery_isolated"] = (
            request("GET", "/gallery", profile="beta").status_code == 200
            and request("GET", "/gallery", profile="beta").json()["total"] == 0
        )
        sticker = gallery.json()["items"][0]
        preview = request("GET", f"/gallery/{sticker['sticker_id']}/preview")
        results["profile_gallery_preview"] = (
            preview.content == image_payload
            and preview.headers["cache-control"] == "private, no-store"
        )
        results["cross_profile_preview_refused"] = (
            request(
                "GET",
                f"/gallery/{sticker['sticker_id']}/preview",
                profile="beta",
            ).status_code
            == 404
        )
        results["anonymous_gallery_refused"] = (
            client.get(
                base + "/gallery?profile=alpha",
                headers={"X-Hermes-Session-Token": ""},
            ).status_code
            == 401
        )
        upload = request(
            "POST",
            "/uploads",
            files={"files": ("../../synthetic.png", image_payload, "image/png")},
        )
        assert upload.status_code == 200
        batch = upload.json()
        results["controlled_stream_upload"] = batch["items"][0]["status"] == "ready"
        results["profile_upload_isolated"] = (
            request("GET", "/uploads", profile="beta").json()["items"] == []
        )
        oversized = request(
            "POST",
            "/uploads",
            files={"files": ("oversized.png", bytes(max_image_bytes + 1), "image/png")},
        )
        results["oversized_upload_refused"] = (
            oversized.status_code == 400 and oversized.json().get("status") == "too_large"
        )
        too_many_files = request(
            "POST",
            "/uploads",
            files=[
                ("files", (f"fixture-{index}.png", b"synthetic", "image/png"))
                for index in range(51)
            ],
        )
        results["oversized_batch_refused"] = (
            too_many_files.status_code == 400 and too_many_files.json().get("status") == "too_large"
        )
        staged_batches = request("GET", "/uploads").json()["items"]
        results["rejected_uploads_cleaned"] = [row["batch_id"] for row in staged_batches] == [
            batch["batch_id"]
        ]
        reindex = job("reindex", {})
        results["profile_task_completed"] = reindex["status"] == "succeeded"
        results["other_profile_jobs_isolated"] = (
            request("GET", "/jobs", profile="beta").json()["items"] == []
        )
        results["discard_batch"] = (
            request("DELETE", "/uploads/" + batch["batch_id"]).json()["status"] == "discarded"
        )
        results["other_profile_remains_empty"] = (
            request("GET", "/gallery", profile="beta").json()["total"] == 0
        )
        from hermes_cli.config import save_config
        from hermes_cli.web_server_profiles import _config_profile_scope

        with _config_profile_scope("beta"):
            save_config({"plugins": {"enabled": [], "disabled": ["hermes-plugin-milky"]}})
        results["disabled_profile_refused"] = (
            request("GET", "/gallery", profile="beta").status_code == 404
            and request(
                "POST", "/requests", profile="beta", json={"operation": "reindex"}
            ).status_code
            == 404
        )
    checks = [
        value
        for key, value in results.items()
        if key not in {"dashboard_api_alias_used", "host_plugin_dependency_overlay_used"}
    ]
    results["status"] = "passed" if all(checks) else "failed"
    return results


def main():
    """子进程隔离所有宿主环境，最终只返回固定检查结果。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-source", required=True, type=Path)
    parser.add_argument("--child-result", type=Path)
    parser.add_argument("--child-progress", type=Path)
    parser.add_argument("--hermes-home", type=Path)
    parser.add_argument(
        "--dashboard-api-alias",
        action="store_true",
        help="仅用于单独诊断 proxy；在常规插件目录之外创建临时 Dashboard 扫描别名。",
    )
    parser.add_argument(
        "--host-plugin-dependency-overlay",
        action="store_true",
        help="仅用于诊断：将临时 profile 的 PM 插件依赖目录加入 PluginHost 启动路径。",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.child_result:
        progress = {"stage": "child_entry"}

        def set_stage(stage, **metadata):
            progress["stage"] = stage
            progress.update(metadata)
            if args.child_progress:
                args.child_progress.write_text(stage)

        set_stage("prepare_profile_homes")
        home = Path(os.environ["HERMES_HOME"])
        dependency_overlays = (
            _plugin_dependency_overlays(home) if args.host_plugin_dependency_overlay else []
        )
        launcher_pythonpath = os.pathsep.join(
            [str(args.hermes_source.resolve()), *(str(path) for path in dependency_overlays)]
        )
        for path in (home, home / "profiles" / "alpha", home / "profiles" / "beta"):
            path.mkdir(parents=True, exist_ok=True)
            config = "plugins:\n  isolation: host\n  enabled: [hermes-plugin-milky]\n"
            if dependency_overlays:
                config += (
                    "  host:\n    launcher:\n      - env\n      - "
                    + json.dumps(f"PYTHONPATH={launcher_pythonpath}")
                    + "\n"
                )
            (path / "config.yaml").write_text(config)
            install = path / "plugins" / "platforms" / "hermes-plugin-milky"
            install.parent.mkdir(parents=True, exist_ok=True)
            if not install.exists() and not install.is_symlink():
                install.symlink_to(root, target_is_directory=True)
            if args.dashboard_api_alias:
                dashboard_alias = path / "plugins" / "hermes-plugin-milky" / "dashboard"
                dashboard_alias.parent.mkdir(parents=True, exist_ok=True)
                if not dashboard_alias.exists() and not dashboard_alias.is_symlink():
                    dashboard_alias.symlink_to(install / "dashboard", target_is_directory=True)
        set_stage("prepare_child_import_path")
        # Hermes 源码路径要排在插件根目录前，避免插件的根级 tools.py 遮蔽 Hermes tools 包。
        sys.path[:0] = [str(args.hermes_source.resolve()), str(root)]
        logging.basicConfig(level=logging.INFO)

        check.dashboard_api_alias_used = args.dashboard_api_alias
        check.host_plugin_dependency_overlay_used = args.host_plugin_dependency_overlay
        set_stage("prepare_hosted_proxy")

        try:
            result = check(home, set_stage)
        except Exception as error:  # noqa: BLE001 - 不输出宿主原始异常
            failure_text = str(error)
            cause_chain = []
            cause_text = []
            nested_exception_types = []
            missing_modules = []
            cause = error
            pending_causes = [cause]
            seen_causes = set()
            while pending_causes and len(nested_exception_types) < 20:
                current = pending_causes.pop()
                if id(current) in seen_causes:
                    continue
                seen_causes.add(id(current))
                nested_exception_types.append(type(current).__name__)
                cause_text.append(str(current).lower())
                if isinstance(current, ModuleNotFoundError) and current.name:
                    missing_modules.append(current.name)
                if isinstance(current, BaseExceptionGroup):
                    pending_causes.extend(current.exceptions)
                if current.__cause__ is not None:
                    pending_causes.append(current.__cause__)
                if current.__context__ is not None:
                    pending_causes.append(current.__context__)
            cause_chain = nested_exception_types[:5]
            missing_modules.extend(
                re.findall(
                    r"No module named ['\"]([A-Za-z_][A-Za-z0-9_.]*)['\"]",
                    " ".join(cause_text),
                )
            )
            missing_modules = sorted(set(missing_modules))
            joined_causes = " ".join(cause_text)
            failure_kind = next(
                (
                    kind
                    for marker, kind in (
                        ("failed to start", "start_failed"),
                        ("channel write failed", "channel_write_failed"),
                        ("channel read failed", "channel_read_failed"),
                        ("not running", "not_running"),
                        ("exited (code", "process_exited"),
                    )
                    if marker in failure_text
                ),
                "other",
            )
            result = {
                "status": "failed",
                "error_type": type(error).__name__,
                "error_cause_type": type(error.__cause__).__name__ if error.__cause__ else None,
                "failure_kind": failure_kind,
                "missing_module": getattr(error, "name", None),
                "stage": progress["stage"],
                "cause_chain": cause_chain,
                "nested_exception_types": nested_exception_types,
                "missing_modules": missing_modules,
                "host_start_cause_kind": next(
                    (
                        kind
                        for marker, kind in (
                            ("channel read failed", "channel_read_failed"),
                            ("channel write failed", "channel_write_failed"),
                            ("channel closed", "channel_closed"),
                            ("timed out", "timed_out"),
                            ("no module named", "missing_dependency"),
                            ("unknown plugin host request", "unknown_method"),
                        )
                        if marker in joined_causes
                    ),
                    "unclassified",
                ),
                "fastapi_spec_found": importlib.util.find_spec("fastapi") is not None,
                "active_venv": sys.prefix != sys.base_prefix,
                "http_status": progress.get("http_status"),
            }
            for key in (
                "host_child_running",
                "host_child_exit_code",
                "host_child_exit_code_after_shutdown",
                "host_channel_closed",
                "host_channel_close_kind",
            ):
                if key in progress:
                    result[key] = progress[key]
            result["plugin_hosts"] = [
                {
                    "alive": host.alive,
                    "process_running": host._proc is not None and host._proc.poll() is None,
                    "channel_closed": bool(
                        host._channel is not None and host._channel.closed_reason
                    ),
                    "channel_close_kind": (
                        "read_failed"
                        if host._channel is not None
                        and "channel read failed" in (host._channel.closed_reason or "")
                        else "write_failed"
                        if host._channel is not None
                        and "channel write failed" in (host._channel.closed_reason or "")
                        else "closed"
                        if host._channel is not None and host._channel.closed_reason
                        else "open"
                    ),
                    "exit_code": host._proc.poll() if host._proc is not None else None,
                    "has_pid": host._proc is not None and host._proc.pid is not None,
                }
                for host in progress.get("plugin_hosts", [])
            ]
            try:
                from hermes_cli import plugins as hermes_plugins

                home_keys = {
                    "launch": home.resolve(),
                    "alpha": (home / "profiles" / "alpha").resolve(),
                    "beta": (home / "profiles" / "beta").resolve(),
                }
                result["manager_hosts"] = []
                for manager_home, manager in hermes_plugins._plugin_managers_by_home.items():
                    plugin_host = getattr(manager, "_plugin_host_instance", None)
                    if plugin_host is None:
                        continue
                    resolved_home = Path(manager_home).resolve()
                    label = next(
                        (name for name, path in home_keys.items() if path == resolved_home),
                        "other",
                    )
                    result["manager_hosts"].append(
                        {
                            "profile": label,
                            "alive": plugin_host.alive,
                            "process_running": (
                                plugin_host._proc is not None and plugin_host._proc.poll() is None
                            ),
                            "channel_closed": bool(
                                plugin_host._channel is not None
                                and plugin_host._channel.closed_reason
                            ),
                        }
                    )
            except Exception:  # noqa: BLE001 - 诊断字段不影响主结果
                result["manager_hosts"] = []
        finally:
            cleanup_hosts = {
                id(plugin_host): plugin_host for plugin_host in progress.get("plugin_hosts", [])
            }
            try:
                from hermes_cli import plugins as hermes_plugins

                for manager in hermes_plugins._plugin_managers_by_home.values():
                    plugin_host = getattr(manager, "_plugin_host_instance", None)
                    if plugin_host is not None:
                        cleanup_hosts[id(plugin_host)] = plugin_host
            except Exception as error:  # noqa: BLE001 - 保留已知引用并记录固定错误类型
                result["cleanup_error_type"] = type(error).__name__
            for plugin_host in cleanup_hosts.values():
                try:
                    plugin_host.shutdown()
                except Exception as error:  # noqa: BLE001 - 清理失败只影响验证状态
                    result["status"] = "failed"
                    result["cleanup_error_type"] = type(error).__name__
        args.child_result.write_text(json.dumps(result))
        return
    with tempfile.TemporaryDirectory(prefix="milky-api-probe-") as temporary:
        directory = Path(temporary)
        output = directory / "result.json"
        progress = directory / "progress.txt"
        home = (
            args.hermes_home or Path(os.environ.get("HERMES_HOME", directory / "home"))
        ).resolve()
        env = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "HOME", "USER", "TMPDIR", "LANG"}
        }
        env.update(
            HERMES_HOME=str(home),
            HERMES_DASHBOARD_SESSION_TOKEN="synthetic-test-session",
        )
        source = args.hermes_source.resolve()
        sys.path.insert(0, str(source))
        previous_home = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = str(home)
        try:
            from hermes_cli._launchers import resolve_store_python
            from pm.environments import committed_venv, site_packages

            runtime_venv = committed_venv(source)
            if runtime_venv is None:
                raise RuntimeError(
                    "Hermes PM dependency environment is not committed for this home"
                )
            child_python = resolve_store_python(source)
            if child_python is None or not child_python.is_file():
                raise RuntimeError("Hermes managed interpreter is unavailable")
            runtime_packages = site_packages(runtime_venv)
            if not runtime_packages.is_dir():
                raise RuntimeError("Hermes PM dependency site-packages are unavailable")
        except Exception as error:  # noqa: BLE001 - 诊断只保留类型，不暴露路径
            if previous_home is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = previous_home
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "stage": "select_profile_dependency_runtime",
                        "error_type": type(error).__name__,
                        "evidence_kind": "real_host_milky_api_synthetic_seed",
                    },
                    indent=2,
                )
            )
            raise SystemExit(1) from None
        finally:
            if previous_home is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = previous_home
        env["PYTHONPATH"] = os.pathsep.join([str(source), str(runtime_packages)])
        env["PATH"] = os.pathsep.join(
            [str(child_python.parent), str(runtime_venv / "bin"), env.get("PATH", "")]
        )
        bootstrap_runner = (
            "import runpy, sys; "
            "source = sys.argv.pop(1); script = sys.argv.pop(1); "
            "sys.path.insert(0, source); "
            "sys.argv = [script, *sys.argv[1:]]; "
            "runpy.run_path(script, run_name='__main__')"
        )
        try:
            process = subprocess.run(
                [
                    str(child_python),
                    "-c",
                    bootstrap_runner,
                    str(source),
                    str(Path(__file__).resolve()),
                    "--hermes-source",
                    str(args.hermes_source.resolve()),
                    "--child-result",
                    str(output),
                    "--child-progress",
                    str(progress),
                    *(["--dashboard-api-alias"] if args.dashboard_api_alias else []),
                    *(
                        ["--host-plugin-dependency-overlay"]
                        if args.host_plugin_dependency_overlay
                        else []
                    ),
                ],
                env=env,
                cwd=directory,
                capture_output=True,
                timeout=180,
                check=False,
            )
        except subprocess.TimeoutExpired:
            result = {
                "status": "blocked",
                "error_type": "TimeoutExpired",
                "stage": progress.read_text() if progress.exists() else "child_startup",
            }
        else:
            result = (
                json.loads(output.read_text())
                if output.exists()
                else {
                    "status": "blocked",
                    "stage": progress.read_text() if progress.exists() else "child_bootstrap",
                }
            )
            stderr = process.stderr.decode("utf-8", errors="replace")
            missing = re.search(r"No module named ['\"]([A-Za-z_][A-Za-z0-9_.]*)['\"]", stderr)
            if missing:
                result["host_missing_module"] = missing.group(1)
            missing_symbol = re.search(
                r"cannot import name ['\"]([A-Za-z_][A-Za-z0-9_]*)['\"] from ['\"]([A-Za-z_][A-Za-z0-9_.]*)['\"]",
                stderr,
            )
            if missing_symbol:
                result["host_missing_import"] = {
                    "symbol": missing_symbol.group(1),
                    "module": missing_symbol.group(2),
                }
            elif symbol := re.search(r"cannot import name ['\"]?([A-Za-z_][A-Za-z0-9_]*)", stderr):
                result["host_import_failure"] = f"cannot_import_symbol:{symbol.group(1)}"
            elif "attempted relative import" in stderr.lower():
                result["host_import_failure"] = "relative_import_context"
            elif "partially initialized module" in stderr.lower():
                result["host_import_failure"] = "circular_import"
            elif "importerror" in stderr.lower() or "modulenotfounderror" in stderr.lower():
                result["host_import_failure"] = "other_import_error"
            if result.get("host_import_failure"):
                result["host_import_trace_frames"] = re.findall(
                    r'^\s*File "[^"]+", line \d+, in ([A-Za-z_][A-Za-z0-9_]*)\s*$',
                    stderr,
                    re.MULTILINE,
                )[-8:]
            result["host_stderr_exception_types"] = sorted(
                set(re.findall(r"\b([A-Za-z_][A-Za-z0-9]*(?:Error|Exception))(?::|\b)", stderr))
            )
            result["host_stderr_plugin_log_lines"] = sum(
                "plugin host [" in line.lower() for line in stderr.splitlines()
            )
            stderr_lower = stderr.lower()
            result["host_stderr_boot_events"] = [
                event
                for marker, event in (
                    ("home maintenance", "home_maintenance"),
                    ("preparing dependencies", "dependency_prepare"),
                    ("installing python dependencies", "dependency_install"),
                    ("plugin host started", "host_started"),
                    ("plugin host failed", "host_failed"),
                    ("traceback", "traceback"),
                )
                if marker in stderr_lower
            ]
            result["child_exit_code"] = process.returncode
            if process.returncode != 0:
                result.setdefault("status", "blocked")
        result["evidence_kind"] = "real_host_milky_api_synthetic_seed"
        print(json.dumps(result, indent=2))
        failed = result["status"] != "passed"
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
