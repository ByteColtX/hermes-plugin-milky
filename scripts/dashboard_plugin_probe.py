"""在隔离的真实 Hermes 中验证当前 Milky API，图库种子使用合成视觉 fixture。"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def check(home):
    """真实宿主认证与 profile API；不连接 QQ 或真实视觉供应商。"""
    from fastapi.testclient import TestClient
    from hermes_cli.web_server import app
    from PIL import Image

    from stickers.maintenance import StickerMaintenanceService

    image = io.BytesIO()
    Image.new("RGB", (32, 32), (90, 140, 210)).save(image, format="PNG")
    root = home / "profiles" / "alpha" / "plugin-data" / "hermes-plugin-milky"
    inbox = root / "stickers" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "synthetic.png").write_bytes(image.getvalue())

    def vision(*_):
        return json.dumps(
            {
                "success": True,
                "analysis": json.dumps(
                    {
                        "is_sticker": True,
                        "emotion": "joy",
                        "tags": ["测试", "合成"],
                        "description": "合成测试图片",
                    }
                ),
            }
        )

    asyncio.run(StickerMaintenanceService(data_dir=root, vision_analyzer=vision).add())
    headers = {"X-Hermes-Session-Token": "synthetic-test-session"}
    base = "/api/plugins/hermes-plugin-milky"
    results = {}
    with TestClient(app) as client:

        def request(method, path, *, profile="alpha", **kwargs):
            return client.request(
                method, base + path, params={"profile": profile}, headers=headers, **kwargs
            )

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

        config = request("GET", "/config").json()
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
        gallery = request("GET", "/gallery").json()
        assert gallery["total"] == 1
        item = gallery["items"][0]
        preview = request("GET", f"/gallery/{item['sticker_id']}/preview")
        results["authenticated_preview"] = (
            preview.content == image.getvalue()
            and preview.headers["cache-control"] == "private, no-store"
        )
        results["anonymous_preview_refused"] = (
            client.get(base + f"/gallery/{item['sticker_id']}/preview?profile=alpha").status_code
            == 401
        )
        results["cross_profile_preview_refused"] = (
            request("GET", f"/gallery/{item['sticker_id']}/preview", profile="beta").status_code
            == 404
        )
        upload = request(
            "POST",
            "/uploads",
            files={"files": ("../../synthetic.png", image.getvalue(), "image/png")},
        )
        assert upload.status_code == 200
        batch = upload.json()
        results["controlled_stream_upload"] = batch["items"][0]["status"] == "ready"
        duplicate = job("import", {"batch_id": batch["batch_id"], "file_ids": batch["file_ids"]})
        results["duplicate_without_vision"] = (
            duplicate["status"] == "succeeded" and duplicate["items"][0]["status"] == "duplicate"
        )
        target = {"sticker_id": item["sticker_id"], "version": item["version"]}
        edited = job("edit", {"targets": [target], "sets": {"emotion": "love"}})
        results["versioned_edit"] = edited["status"] == "succeeded"
        conflict = job("delete", {"targets": [target]})
        results["old_version_conflict"] = conflict["items"][0]["status"] == "conflict"
        item = request("GET", "/gallery").json()["items"][0]
        deleted = job(
            "delete", {"targets": [{"sticker_id": item["sticker_id"], "version": item["version"]}]}
        )
        results["versioned_delete"] = deleted["status"] == "succeeded"
        plan = request("POST", "/cleanup/preview").json()
        results["cleanup_plan"] = (
            job("cleanup", {"plan_id": plan["plan_id"]})["status"] == "succeeded"
        )
        results["reindex"] = job("reindex", {})["status"] == "succeeded"
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
    results["status"] = "passed" if all(results.values()) else "failed"
    return results


def main():
    """子进程隔离所有宿主环境，最终只返回固定检查结果。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-source", required=True, type=Path)
    parser.add_argument("--child-result", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.child_result:
        home = Path(os.environ["HERMES_HOME"])
        for path in (home, home / "profiles" / "alpha", home / "profiles" / "beta"):
            path.mkdir(parents=True, exist_ok=True)
            (path / "config.yaml").write_text("plugins:\n  enabled: [hermes-plugin-milky]\n")
        install = home / "plugins" / "hermes-plugin-milky"
        install.parent.mkdir()
        install.symlink_to(root, target_is_directory=True)
        sys.path[:0] = [str(root), str(args.hermes_source.resolve())]
        try:
            result = check(home)
        except Exception as error:  # noqa: BLE001 - 不输出宿主原始异常
            import traceback

            result = {
                "status": "failed",
                "error_type": type(error).__name__,
                "line": traceback.extract_tb(error.__traceback__)[-1].lineno,
            }
        args.child_result.write_text(json.dumps(result))
        return
    with tempfile.TemporaryDirectory(prefix="milky-api-probe-") as temporary:
        directory = Path(temporary)
        output = directory / "result.json"
        env = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "HOME", "USER", "TMPDIR", "LANG"}
        }
        env.update(
            HERMES_HOME=str(directory / "home"),
            HERMES_DASHBOARD_SESSION_TOKEN="synthetic-test-session",
        )
        process = subprocess.run(
            [
                "uv",
                "run",
                "--no-project",
                "--python",
                sys.executable,
                str(Path(__file__).resolve()),
                "--hermes-source",
                str(args.hermes_source.resolve()),
                "--child-result",
                str(output),
            ],
            env=env,
            cwd=directory,
            capture_output=True,
            timeout=60,
            check=False,
        )
        result = (
            json.loads(output.read_text())
            if process.returncode == 0 and output.exists()
            else {"status": "blocked"}
        )
        result["evidence_kind"] = "real_host_milky_api_synthetic_seed"
        print(json.dumps(result, indent=2))
        if result["status"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
