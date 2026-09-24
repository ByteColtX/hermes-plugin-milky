"""在隔离用户插件安装中验证真实 Hermes Dashboard 的后端接入能力。

运行示例：uv run --no-project --python <宿主解释器> \
    scripts/dashboard_host_probe.py --hermes-source <Hermes 源码目录>

本检查使用真实宿主 ASGI 应用与合成插件，不代表 Milky 页面浏览器验收。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_PLUGIN_NAME = "milky-dashboard-probe"
_TOKEN = "synthetic-dashboard-probe-token"
_PROBE_API = '''"""供真实宿主能力验证使用的合成管理路由。"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import APIRouter, Response
from hermes_constants import get_hermes_home
from hermes_cli.web_server_profiles import _config_profile_scope

@asynccontextmanager
async def lifetime(app):
    marker = get_hermes_home() / "probe-lifespan"
    marker.write_text("started")
    yield
    marker.write_text("stopped")

router = APIRouter(lifespan=lifetime)

@router.get("/image")
async def image():
    return Response(bytes([137, 80, 78, 71]), media_type="image/png",
                    headers={"Cache-Control": "no-store"})

@router.get("/scope")
async def scope(profile: str):
    from hermes_cli.config import load_config
    from agent.secret_scope import get_secret
    with _config_profile_scope(profile):
        await asyncio.sleep(0.02)
        cfg = load_config()
        name = cfg["plugins"]["entries"]["milky-dashboard-probe"]["settings"]["marker"]
        secret = get_secret("MILKY_ACCESS_TOKEN")
        return {"marker": name, "secret_matches": secret == "synthetic-" + name + "-secret"}
'''


def _install_probe(home: Path) -> None:
    """只向临时用户插件目录安装合成资源与两个测试 profile。"""
    plugin = home / "plugins" / _PLUGIN_NAME / "dashboard"
    (plugin / "dist").mkdir(parents=True)
    manifest = {
        "name": _PLUGIN_NAME,
        "label": "Milky capability probe",
        "version": "0.0.0",
        "entry": "dist/index.js",
        "api": "plugin_api.py",
        "tab": {"path": "/milky-dashboard-probe"},
    }
    (plugin / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin / "dist" / "index.js").write_text(
        "window.__MILKY_SYNTHETIC_PROBE__ = true;", encoding="utf-8"
    )
    (plugin / "plugin_api.py").write_text(_PROBE_API, encoding="utf-8")
    config = (
        "plugins:\n  enabled: [milky-dashboard-probe]\n  entries:\n"
        "    milky-dashboard-probe:\n      settings:\n        marker: launch\n"
    )
    for name, scoped in (
        ("launch", home),
        *((n, home / "profiles" / n) for n in ("alpha", "beta")),
    ):
        scoped.mkdir(parents=True, exist_ok=True)
        (scoped / "config.yaml").write_text(config.replace("launch", name), encoding="utf-8")
        (scoped / ".env").write_text(
            f"MILKY_ACCESS_TOKEN=synthetic-{name}-secret\n", encoding="utf-8"
        )


def _run_checks(home: Path) -> dict[str, object]:
    """直接使用真实应用的发现、认证、范围与路由生命周期。"""
    import fastapi
    import httpx
    import starlette
    from fastapi.testclient import TestClient
    from hermes_cli import web_server
    from hermes_cli.config import load_config, save_config

    headers = {"X-Hermes-Session-Token": _TOKEN}
    result: dict[str, object] = {
        "versions": {"fastapi": fastapi.__version__, "starlette": starlette.__version__},
        "user_plugin_discovery": any(
            row["name"] == _PLUGIN_NAME and row["source"] == "user"
            for row in web_server._get_dashboard_plugins()
        ),
    }
    base = f"/api/plugins/{_PLUGIN_NAME}"

    async def check_scopes() -> bool:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=web_server.app),
            base_url="http://testserver",
            headers=headers,
        ) as client:
            names = ("alpha", "beta", "alpha")
            responses = await asyncio.gather(
                *(client.get(f"{base}/scope", params={"profile": name}) for name in names)
            )
            return all(
                response.status_code == 200
                and response.json() == {"marker": name, "secret_matches": True}
                for name, response in zip(names, responses, strict=True)
            )

    with TestClient(web_server.app) as client:
        result["router_startup"] = (home / "probe-lifespan").read_text() == "started"
        result["unauthenticated_binary_denied"] = client.get(f"{base}/image").status_code == 401
        response = client.get(f"{base}/image", headers=headers)
        result["authenticated_binary"] = (
            response.status_code == 200
            and response.content == bytes([137, 80, 78, 71])
            and response.headers.get("cache-control") == "no-store"
        )
        result["installed_static_asset"] = (
            client.get(
                f"/dashboard-plugins/{_PLUGIN_NAME}/dist/index.js", headers=headers
            ).status_code
            == 200
        )
        result["concurrent_profile_config_and_secret_isolation"] = asyncio.run(check_scopes())
        result["forged_profile_denied"] = (
            client.get(f"{base}/scope", params={"profile": "../other"}, headers=headers).status_code
            == 400
        )
        cfg = load_config()
        cfg["plugins"]["disabled"] = [_PLUGIN_NAME]
        save_config(cfg)
        result["runtime_disabled_denied"] = (
            client.get(f"{base}/image", headers=headers).status_code == 404
        )
    result["router_shutdown"] = (home / "probe-lifespan").read_text() == "stopped"
    return result


def _child(source: Path, result_file: Path, home: Path) -> None:
    """在子进程内完成临时安装并只写固定检查项。"""
    sys.path.insert(0, str(source))
    _install_probe(home)
    try:
        result = _run_checks(home)
    except Exception as error:  # noqa: BLE001 - 宿主边界仅记录异常类型，避免泄露原文
        result = {"status": "blocked", "error_type": type(error).__name__}
        if isinstance(error, ModuleNotFoundError):
            result["missing_module"] = error.name
    result_file.write_text(json.dumps(result), encoding="utf-8")


def main() -> int:
    """隔离环境并输出不包含运行日志、凭证或路径的能力摘要。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-source", required=True, type=Path)
    parser.add_argument("--child-result", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    source = args.hermes_source.resolve()
    if args.child_result:
        _child(source, args.child_result, Path(os.environ["HERMES_HOME"]))
        return 0
    revision = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="milky-dashboard-probe-") as root:
        temp = Path(root)
        home = temp / "hermes"
        output = temp / "result.json"
        env = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "HOME", "USER", "TMPDIR", "LANG", "LC_ALL"}
        }
        env["HERMES_HOME"] = str(home)
        env["HERMES_DASHBOARD_SESSION_TOKEN"] = _TOKEN
        command = [
            "uv",
            "run",
            "--no-project",
            "--python",
            sys.executable,
            str(Path(__file__).resolve()),
            "--hermes-source",
            str(source),
            "--child-result",
            str(output),
        ]
        try:
            completed = subprocess.run(
                command, cwd=temp, env=env, capture_output=True, text=True, timeout=60, check=False
            )
        except subprocess.TimeoutExpired:
            result = {"status": "blocked", "error_type": "TimeoutExpired"}
        else:
            result = (
                json.loads(output.read_text(encoding="utf-8"))
                if completed.returncode == 0 and output.is_file()
                else {"status": "blocked", "error_type": "HostProcessFailed"}
            )
        result.update(
            {
                "evidence_kind": "real_host_asgi_synthetic_plugin",
                "core_revision": revision,
                "python_version": ".".join(map(str, sys.version_info[:3])),
                "browser_sdk_verification": "unknown",
                "milky_plugin_verification": "unknown",
            }
        )
        if "status" not in result:
            result["status"] = (
                "passed" if all(v is not False for v in result.values()) else "failed"
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
