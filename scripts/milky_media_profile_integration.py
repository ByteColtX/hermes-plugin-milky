"""在目标 Hermes 双 profile 路由中验证入站媒体归属。

运行示例：uv run --no-project --python <Hermes 宿主解释器> \
    scripts/milky_media_profile_integration.py --hermes-source <Hermes 源码目录

只创建合成媒体文件；Hermes 下载 helper 被替换为本地 fixture writer，不访问网络。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HERMES_ROOT = Path("/Users/bytecolt/PythonProjects/hermes-agent")


class _ResourceClient:
    """提供不访问网络的 Milky 资源 fixture。"""

    async def get_resource_temp_url(self, _resource_id: object) -> object:
        """返回占位 CDN URL，实际 materialization 交给 Hermes helper。"""

        return {"status": "ok", "retcode": 0, "data": {"url": "https://cdn.example.invalid/image"}}

    async def get_group_file_download_url(self, *_args: object) -> object:
        """本场景不使用群文件。"""

        raise AssertionError("unexpected group file lookup")

    async def get_private_file_download_url(self, *_args: object, **_kwargs: object) -> object:
        """本场景不使用私聊文件。"""

        raise AssertionError("unexpected private file lookup")

    async def get_forwarded_messages(self, *_args: object) -> object:
        """本场景不展开转发消息。"""

        raise AssertionError("unexpected forwarded message lookup")

    async def get_message(self, *_args: object) -> object:
        """本场景不补全引用消息。"""

        raise AssertionError("unexpected reply lookup")


def _write_profile_config(home: Path, backend: str) -> None:
    """创建最小、合成的 Hermes profile 配置。"""

    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(f"terminal:\n  backend: {backend}\n", encoding="utf-8")


def _run_checks(hermes_root: Path, temp_root: Path) -> None:
    """运行真实插件 resolver 和 Gateway media re-home 边界。"""

    sys.path[:0] = [str(hermes_root), str(PLUGIN_ROOT)]

    import gateway.platforms.base as platform_base
    from agent import secret_scope
    from gateway.platforms.event import MessageEvent, MessageType
    from gateway.run import _profile_runtime_scope
    from gateway.run_inbound_media import rehome_inbound_media
    from hermes_constants import get_hermes_home

    from adapter import _HermesMediaHelperBridge
    from inbound.hermes_mapper import map_message_event
    from milky.resources import ResourceResolver

    launch_home = temp_root / "launch"
    routed_home = launch_home / "profiles" / "beta"
    _write_profile_config(launch_home, "local")
    _write_profile_config(routed_home, "docker")
    os.environ["HERMES_HOME"] = str(launch_home)
    secret_scope.set_multiplex_active(True)

    helper_calls: list[str] = []

    async def cache_image_from_url(url: str, ext: str = ".jpg", retries: int = 2) -> str:
        """模拟 Hermes helper 的 launch-cache 结果，不下载 URL。"""

        del retries
        assert url == "https://cdn.example.invalid/image"
        helper_calls.append(url)
        path = get_hermes_home() / "cache" / "images" / f"milky-profile-fixture{ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic-image")
        return str(path)

    original_helper = platform_base.cache_image_from_url
    platform_base.cache_image_from_url = cache_image_from_url
    try:
        message = SimpleNamespace(
            body="[img:file_name=photo.jpg]",
            scene="group",
            media_resource_references=(
                SimpleNamespace(
                    kind="image",
                    temp_url="https://cdn.example.invalid/image",
                    resource_id="synthetic-resource",
                    mime_type="image/jpeg",
                    name="photo.jpg",
                ),
            ),
            file_attachment_references=(),
            forward_references=(),
            reply_references=(),
            peer_id=700000001,
            self_id=800000001,
            sender_name="fixture sender",
            sender_id=800000002,
            chat_key="group:700000001",
            message_seq="fixture-seq",
            quote_message_seq=None,
            timestamp=1,
            raw=None,
            quote_target_is_self=False,
            mention_status=None,
        )
        resolved = asyncio.run(
            ResourceResolver(_ResourceClient(), _HermesMediaHelperBridge()).resolve(message)
        )
        assert helper_calls == ["https://cdn.example.invalid/image"]
        launch_path = Path(resolved.hermes_attachment_materializations[0].path)
        assert launch_path == launch_home / "cache" / "images" / "milky-profile-fixture.jpg"
        assert launch_path.read_bytes() == b"synthetic-image"
        assert not (routed_home / "cache" / "images" / launch_path.name).exists()

        event = map_message_event(
            message,
            resolved,
            source=None,
            message_event_cls=MessageEvent,
            message_type_cls=MessageType,
        )
        assert event.media_urls == [str(launch_path)]
        assert launch_path.is_file()
        assert not (routed_home / "cache" / "images" / launch_path.name).exists()

        with _profile_runtime_scope(routed_home):
            rehome_inbound_media(event)

        routed_path = routed_home / "cache" / "images" / launch_path.name
        assert event.media_urls == [str(routed_path)]
        assert routed_path.read_bytes() == b"synthetic-image"
        assert not launch_path.exists()
        assert not (launch_home / "cache" / "images" / launch_path.name).exists()
    finally:
        platform_base.cache_image_from_url = original_helper
        secret_scope.set_multiplex_active(False)


def main() -> None:
    """验证插件调用 Hermes materialization，Gateway 独自完成 profile re-home。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-source", type=Path, default=DEFAULT_HERMES_ROOT)
    args = parser.parse_args()
    hermes_root = args.hermes_source.resolve()
    if not (hermes_root / "gateway" / "run_inbound_media.py").is_file():
        raise SystemExit("target Hermes source tree is unavailable")
    with tempfile.TemporaryDirectory(prefix="milky-media-profile-") as temp_dir:
        _run_checks(hermes_root, Path(temp_dir))
    print(
        "target Hermes media helper and two-profile Gateway re-home: passed; synthetic data, no network"
    )


if __name__ == "__main__":
    main()
