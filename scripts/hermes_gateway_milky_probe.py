"""在目标 Hermes Gateway 中验证 Milky 的 profile、去重和注入边界。"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import logging
import os
import sys
import tempfile
import types
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_CURRENT_STAGE = "initialize"
_PLUGIN_DEPENDENCY_SITE_PACKAGES: Path | None = None


def _set_stage(stage: str) -> None:
    """更新脱敏诊断阶段。"""

    global _CURRENT_STAGE
    _CURRENT_STAGE = stage


@contextmanager
def _milky_profile_scope(profile_home: Path):
    """只绑定 adapter 所需的 profile home 与凭证。"""

    from agent.secret_scope import build_profile_secret_scope, reset_secret_scope, set_secret_scope
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    home_token = set_hermes_home_override(str(profile_home))
    secret_token = None
    try:
        secrets = build_profile_secret_scope(profile_home)
        secret_token = set_secret_scope(secrets, profile_home=str(profile_home))
        yield
    finally:
        if secret_token is not None:
            reset_secret_scope(secret_token)
        reset_hermes_home_override(home_token)


@asynccontextmanager
async def _async_milky_profile_scope(profile_home: Path):
    """在异步注入中绑定 profile home 与凭证，不初始化终端运行时。"""

    with _milky_profile_scope(profile_home):
        yield


def _write_profile(home: Path, profile: str, port: int) -> None:
    """写入隔离 profile 的合成配置和凭证。"""

    home.mkdir(parents=True, exist_ok=True)
    config = (
        "plugins:\n"
        "  enabled: [hermes-plugin-milky]\n"
        "  isolation: in_process\n"
        "  entries:\n"
        "    hermes-plugin-milky:\n"
        "      allow_gateway_injection: true\n"
    )
    (home / "config.yaml").write_text(config, encoding="utf-8")
    (home / ".env").write_text(
        f"MILKY_BASE_URL=http://127.0.0.1:{port}/milky\n"
        f"MILKY_ACCESS_TOKEN=synthetic-{profile}-token\n",
        encoding="utf-8",
    )


def _find_plugin_dependency_site_packages(home: Path) -> Path | None:
    """选择 Hermes 已准备且包含 Milky 直接依赖的最新 profile 插件环境。"""

    required_modules = ("httpx", "multipart", "PIL", "jieba")
    candidates = [
        path
        for path in home.glob("installs/*/environments/*/venv/lib/python*/site-packages")
        if all((path / module).is_dir() for module in required_modules)
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def _load_plugin_entry(profile: str):
    """通过真实 PluginContext 注册当前 profile 的 Milky platform。"""

    _set_stage("import_gateway_config")
    from gateway.config import PlatformConfig

    _set_stage("import_platform_registry")
    from gateway.platform_registry import platform_registry

    _set_stage("import_gateway_runner")

    _set_stage("import_plugin_manager")
    from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest

    _set_stage("import_hermes_home")
    from hermes_constants import get_hermes_home

    namespace = sys.modules.get("hermes_plugins")
    if namespace is None:
        namespace = types.ModuleType("hermes_plugins")
        namespace.__path__ = []
        sys.modules["hermes_plugins"] = namespace
    module_name = f"hermes_plugins.milky_gateway_probe_{profile}"
    spec = importlib.util.spec_from_file_location(
        module_name,
        PLUGIN_ROOT / "__init__.py",
        submodule_search_locations=[str(PLUGIN_ROOT)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("plugin entry is unavailable")
    _set_stage("import_plugin_entry")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    _set_stage("construct_plugin_context")
    manager = PluginManager(scope_key=str(get_hermes_home()))
    manifest = PluginManifest(
        name="hermes-plugin-milky",
        key="hermes-plugin-milky",
        source="user",
    )
    context = PluginContext(manifest, manager)
    _set_stage("register_plugin_entry")
    with _milky_profile_scope(get_hermes_home()):
        if _PLUGIN_DEPENDENCY_SITE_PACKAGES is not None:
            sys.path.insert(0, str(_PLUGIN_DEPENDENCY_SITE_PACKAGES))
        _set_stage("import_plugin_dependencies")
        for dependency in ("httpx", "multipart", "PIL", "jieba"):
            importlib.import_module(dependency)
        _set_stage("register_plugin_entry")
        module.register(context)
        _set_stage("construct_milky_adapter")
        entry = platform_registry.get("milky")
        if entry is None:
            raise RuntimeError("platform registry entry is unavailable")
        adapter = entry.adapter_factory(PlatformConfig(enabled=True))
    return manager, context, entry, adapter


def _gateway_runner(default_adapter, beta_adapter):
    """組裝目標 Gateway 的 profile adapter map，避免啟動模型或網絡服務。"""

    from gateway.config import GatewayConfig, Platform
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(multiplex_profiles=True)
    milky_platform = Platform("milky")
    runner.adapters = {milky_platform: default_adapter}
    runner._profile_adapters = {"beta": {milky_platform: beta_adapter}}
    runner._primary_profile_name = "default"
    runner._running = True
    runner._draining = False
    runner._background_tasks = set()
    runner._gateway_loop = asyncio.get_running_loop()
    return runner


async def _settle_gateway(runner, adapters) -> None:
    """等待 Gateway 调度任务和合成 adapter handler 完成。"""

    for _ in range(4):
        tasks = set(runner._background_tasks)
        for adapter in adapters:
            tasks.update(adapter._background_tasks)
        if not tasks:
            await asyncio.sleep(0)
            continue
        await asyncio.gather(*tasks, return_exceptions=True)


async def _check_gateway(
    default_adapter,
    beta_adapter,
    default_context,
    beta_context,
    default_entry,
    default_home: Path,
) -> dict:
    """运行目标 Gateway profile routing、receipt 和异步拒绝检查。"""

    import gateway.run as gateway_run
    from gateway.config import Platform
    from gateway.platforms.helpers import carry_inbound_dedup

    from inbound.pipeline import _gateway_receipt_classification

    with _milky_profile_scope(default_home):
        replacement = default_entry.adapter_factory(default_adapter.config)
    key = "milky:900000001:group:700000001:fixture-seq"
    previous_seeded = default_adapter._deduplicator.is_duplicate(key) is False
    carry_inbound_dedup(default_adapter, replacement)
    replacement_inherited = replacement._deduplicator.is_duplicate(key) is True
    replacement_new_sequence = (
        replacement._deduplicator.is_duplicate("milky:900000001:group:700000001:new-seq") is False
    )

    missing_receipt = types.SimpleNamespace()
    receipt_missing_is_unknown = _gateway_receipt_classification(missing_receipt) == "unknown"

    runner = _gateway_runner(default_adapter, beta_adapter)
    authorization = {"allowed": True}
    runner._is_user_authorized_for_source = lambda *_args, **_kwargs: authorization["allowed"]
    beta_adapter.set_owner_profile("beta")
    for adapter in (default_adapter, beta_adapter):
        adapter.gateway_runner = runner
        adapter._connected = True
        adapter._initial_sync_complete = True
        adapter._pipeline = object()
        adapter.set_message_handler(lambda _event: None)

    captured: dict[str, list[tuple[object, str]]] = {"default": [], "beta": []}
    for profile, adapter in (("default", default_adapter), ("beta", beta_adapter)):

        async def record(event, session_key, *, target=profile):
            captured[target].append((event, session_key))

        adapter._process_message_background = record

    default_manager = default_context._manager
    beta_manager = beta_context._manager
    default_manager.set_gateway_message_injector(runner, runner._schedule_plugin_message_injection)
    beta_manager.set_gateway_message_injector(runner, runner._schedule_plugin_message_injection)

    gateway_run._multiplex_profile_homes = lambda _config: [
        ("default", default_home),
        ("beta", default_home / "profiles" / "beta"),
    ]
    original_profile_scope = gateway_run._async_profile_runtime_scope

    @asynccontextmanager
    async def profile_runtime_scope(profile_home):
        async with _async_milky_profile_scope(Path(profile_home)):
            yield

    gateway_run._async_profile_runtime_scope = profile_runtime_scope

    default_origin = {
        "platform": "milky",
        "chat_id": "group:700000001",
        "chat_type": "group",
        "user_id": "800000001",
    }
    beta_origin = {
        "platform": "milky",
        "chat_id": "group:700000002",
        "chat_type": "group",
        "user_id": "800000002",
    }
    default_scheduled = default_adapter.inject_message(
        "synthetic default-profile event", origin=default_origin
    )
    beta_scheduled = beta_adapter.inject_message("synthetic beta-profile event", origin=beta_origin)
    await _settle_gateway(runner, (default_adapter, beta_adapter))

    profile_routing = (
        default_scheduled
        and beta_scheduled
        and len(captured["default"]) == 1
        and len(captured["beta"]) == 1
        and captured["default"][0][0].source.profile in {None, "default"}
        and captured["beta"][0][0].source.profile == "beta"
        and captured["default"][0][0]._gateway_accepted is True
        and captured["beta"][0][0]._gateway_accepted is True
    )
    receipt_missing_is_unknown = bool(
        receipt_missing_is_unknown
        and captured["beta"]
        and _gateway_receipt_classification(captured["beta"][0][0]) == "accepted"
    )

    before_rejection = len(captured["beta"])
    authorization["allowed"] = True
    async_rejection_was_scheduled = beta_adapter.inject_message(
        "synthetic async rejection", origin=beta_origin
    )
    authorization["allowed"] = False
    await _settle_gateway(runner, (default_adapter, beta_adapter))
    async_rejection_not_visible_to_plugin = (
        async_rejection_was_scheduled and len(captured["beta"]) == before_rejection
    )

    wrong_profile_refused = not default_adapter.inject_message(
        "synthetic cross-profile request",
        origin={**default_origin, "profile": "beta"},
    )
    gateway_run._async_profile_runtime_scope = original_profile_scope
    return {
        "gateway_profile_routing": profile_routing,
        "adapter_replacement_dedup": (
            previous_seeded and replacement_inherited and replacement_new_sequence
        ),
        "receipt_missing_unknown": receipt_missing_is_unknown,
        "async_injection_rejection_not_visible": async_rejection_not_visible_to_plugin,
        "cross_profile_injection_refused": wrong_profile_refused,
        "replacement_adapter_unused": replacement is not default_adapter,
        "platform_registry_profile_scoped": (
            default_adapter.platform == Platform("milky")
            and beta_adapter.platform == Platform("milky")
        ),
    }


def main() -> int:
    """建立一次性 Hermes homes 並輸出固定、無敏感資訊的結果。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-source", required=True, type=Path)
    parser.add_argument("--plugin-dependency-home", type=Path)
    args = parser.parse_args()
    hermes_source = args.hermes_source.resolve()
    if not (hermes_source / "gateway" / "run.py").is_file():
        raise SystemExit("target Hermes source tree is unavailable")

    sys.path[:0] = [str(hermes_source), str(PLUGIN_ROOT)]
    dependency_site_packages = (
        hermes_source
        / ".venv"
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    if dependency_site_packages.is_dir():
        sys.path.insert(0, str(dependency_site_packages))
    plugin_dependency_site_packages = (
        _find_plugin_dependency_site_packages(args.plugin_dependency_home)
        if args.plugin_dependency_home
        else None
    )
    if plugin_dependency_site_packages is not None:
        sys.path.insert(0, str(plugin_dependency_site_packages))
    global _PLUGIN_DEPENDENCY_SITE_PACKAGES
    _PLUGIN_DEPENDENCY_SITE_PACKAGES = plugin_dependency_site_packages
    logging.disable(logging.CRITICAL)
    saved_home = os.environ.get("HERMES_HOME")
    os.environ["HERMES_HOME"] = ""
    for name in tuple(os.environ):
        if name.startswith("MILKY_"):
            os.environ.pop(name, None)

    result: dict[str, object] = {"evidence_kind": "target_hermes_gateway_synthetic"}
    result["source_venv_on_import_path"] = str(dependency_site_packages) in sys.path
    result["hermes_tool_interpreter"] = ".hermes/tools/python" in sys.executable
    result["plugin_dependencies_overlay_used"] = plugin_dependency_site_packages is not None
    _set_stage("preload_gateway_apis")
    try:
        try:
            result["ruamel_yaml_available"] = importlib.util.find_spec("ruamel.yaml") is not None
        except ModuleNotFoundError:
            result["ruamel_yaml_available"] = False
        for module_name in (
            "gateway.config",
            "gateway.platform_registry",
            "gateway.run",
            "hermes_cli.plugins",
        ):
            importlib.import_module(module_name)

        _set_stage("prepare_profiles")
        with tempfile.TemporaryDirectory(prefix="milky-gateway-probe-") as directory:
            home = Path(directory) / "hermes"
            beta_home = home / "profiles" / "beta"
            os.environ["HERMES_HOME"] = str(home)
            _write_profile(home, "default", 59991)
            _write_profile(beta_home, "beta", 59992)
            from hermes_constants import reset_hermes_home_override, set_hermes_home_override

            _set_stage("register_default_platform")
            default_token = set_hermes_home_override(home)
            try:
                default_manager, default_context, default_entry, default_adapter = (
                    _load_plugin_entry("default")
                )
            finally:
                reset_hermes_home_override(default_token)

            _set_stage("register_beta_platform")
            beta_token = set_hermes_home_override(beta_home)
            try:
                beta_manager, beta_context, _entry, beta_adapter = _load_plugin_entry("beta")
            finally:
                reset_hermes_home_override(beta_token)

            result["profile_config_isolated"] = (
                default_adapter._config.base_url != beta_adapter._config.base_url
                and default_manager.home_path == home
                and beta_manager.home_path == beta_home
            )
            _set_stage("run_gateway_checks")
            result.update(
                asyncio.run(
                    _check_gateway(
                        default_adapter,
                        beta_adapter,
                        default_context,
                        beta_context,
                        default_entry,
                        home,
                    )
                )
            )
        result["status"] = (
            "passed"
            if all(value is True for key, value in result.items() if key != "evidence_kind")
            else "failed"
        )
    except Exception as error:  # noqa: BLE001 - 報告類別，避免輸出宿主錯誤正文
        result.update(
            {
                "status": "blocked",
                "stage": _CURRENT_STAGE,
                "error_type": type(error).__name__,
                "error_module": type(error).__module__,
            }
        )
        if isinstance(error, ModuleNotFoundError) and error.name:
            result["missing_module"] = error.name
        frames = []
        traceback = error.__traceback__
        while traceback is not None:
            frame = traceback.tb_frame
            frames.append(
                f"{frame.f_globals.get('__name__', 'unknown')}:{frame.f_code.co_name}:{traceback.tb_lineno}"
            )
            traceback = traceback.tb_next
        if frames:
            result["error_frames"] = frames[-12:]
    finally:
        if saved_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = saved_home
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
