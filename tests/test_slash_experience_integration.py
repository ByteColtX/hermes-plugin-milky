"""使用 fake host 和既有发送器验证命令展示的端到端本地边界。"""

import asyncio
from types import SimpleNamespace

import pytest

from gates import GateRegistry
from milky.client import ActionError
from outbound.sender import MilkyOutboundSender
from slash_commands import SlashCommandService
from stickers import presentation
from stickers.maintenance import StickerMaintenanceService
from tests.test_hot_allowlist import invoke, setup
from tests.test_long_text_forwarding import ForwardClient, _forward_body, _text_content
from tests.test_slash_commands import (
    FIXTURE_ROOT,
    DispatchingHermes,
    RecordingResolver,
    RecordingWill,
    load_fixture,
    make_pipeline,
)
from tests.test_sticker_maintenance import _PNG, _vision
from tests.test_sticker_text import item


@pytest.mark.parametrize("args", ["help", "status", "sticker help", "sticker remove demo_id"])
@pytest.mark.parametrize("allowed", [False, True])
@pytest.mark.parametrize("core_allowed", [False, True])
def test_new_commands_follow_gate_then_core_without_agent(args, allowed, core_allowed):
    """新语法只在 Gate 和 core 均允许时执行，不进入 Will 或资源补全。"""

    async def scenario():
        calls = []

        async def dispatch(raw):
            if core_allowed:
                calls.append(raw)
            return "core accepted" if core_allowed else "core denied"

        host = DispatchingHermes(dispatch)
        resolver, will = RecordingResolver(), RecordingWill()
        pipeline = make_pipeline(host, resolver, will)
        pipeline._gates = GateRegistry({"dm:*"} if allowed else ())
        event = load_fixture(FIXTURE_ROOT / "events/friend_plain_text.json")
        event["data"]["segments"] = [{"type": "text", "data": {"text": "/milky " + args}}]
        result = await pipeline.handle_event(event)
        await pipeline.wait_idle()
        assert result.classification == ("command" if allowed else "denied")
        assert calls == ([args] if allowed and core_allowed else [])
        assert resolver.calls == will.decisions == will.reply_costs == 0
        assert host.agent_inputs == []
        await pipeline.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("core_allowed", [False, True])
def test_allowlist_exception_still_belongs_to_core_and_never_queries_group(core_allowed):
    """管理帮助白名单外可到 core，但 core 拒绝时不执行插件帮助。"""

    async def scenario():
        service = SlashCommandService()
        calls = []

        async def dispatch(raw):
            if not core_allowed:
                return "core denied"
            calls.append(raw)
            return await service.handle(raw)

        host = DispatchingHermes(dispatch)
        resolver, will = RecordingResolver(), RecordingWill()
        pipeline = make_pipeline(host, resolver, will)
        pipeline._gates = GateRegistry(())
        pipeline._mute_tracker = SimpleNamespace(
            gate_snapshot=lambda _: pytest.fail("管理命令不查群状态"),
            prepare_group=lambda _: pytest.fail("管理命令不准备群"),
        )
        event = load_fixture(FIXTURE_ROOT / "events/group_plugin_milky.json")
        event["data"]["segments"] = [{"type": "text", "data": {"text": "/milky allowlist help"}}]
        assert (await pipeline.handle_event(event)).classification == "command"
        await pipeline.wait_idle()
        assert calls == (["allowlist help"] if core_allowed else [])
        assert resolver.calls == will.decisions == 0
        await pipeline.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["help", "stickers", "allowlist"])
@pytest.mark.parametrize("forward", [False, True])
def test_long_real_command_text_preserves_all_content(kind, forward):
    """实际命令文本完整分块或转发，白名单不套贴纸返回上限。"""

    async def scenario():
        if kind == "help":
            text = await SlashCommandService().handle("sticker help")
        elif kind == "stickers":
            text = presentation.render(
                "list", {"status": "ok", "items": [item(f"demo_{i}") for i in range(20)]}
            )
        else:
            manager, *_ = setup({f"dm:{i}" for i in range(100, 170)})
            text = await invoke(manager, "allowlist list")
            assert all(f"dm:{i}" in text for i in range(100, 170))
        client = ForwardClient()
        sender = MilkyOutboundSender(
            client,
            max_text_length=100,
            long_text_forward_threshold=100 if forward else 0,
            identity_loader=client.get_login_info,
        )
        assert (await sender.send("dm:800000001", text)).success
        if forward:
            delivered = _text_content(_forward_body(client)["messages"])
        else:
            assert len(client.calls) > 1
            delivered = "".join(
                segment["data"]["text"]
                for _, body in client.calls
                for segment in body["message"]
                if segment["type"] == "text"
            )
        assert delivered == text

    asyncio.run(scenario())


def test_receipt_failure_does_not_repeat_sticker_delete(tmp_path, monkeypatch):
    """删除已提交后回执未知，仍只执行一次业务和一次发送。"""

    async def scenario():
        inbox = tmp_path / "stickers" / "inbox"
        inbox.mkdir(parents=True)
        (inbox / "synthetic.png").write_bytes(_PNG)
        stickers = StickerMaintenanceService(
            data_dir=tmp_path, vision_analyzer=lambda *a, **k: _vision()
        )
        added = await stickers.add()
        sticker_id = added["items"][0]["sticker_id"]
        original, calls = stickers._delete, []

        def delete(store, target):
            calls.append(target)
            return original(store, target)

        monkeypatch.setattr(stickers, "_delete", delete)
        service = SlashCommandService(stickers)
        text = await service.handle("sticker remove " + sticker_id)
        client = ForwardClient(
            send_error=ActionError("transport_unknown", "send_private_message", "secret")
        )
        sender = MilkyOutboundSender(client)
        result = await sender.send("dm:800000001", text)
        assert not result.success
        assert len(client.calls) == 1 and calls == [sticker_id]
        assert stickers.list()["count"] == 0
        assert "secret" not in text

    asyncio.run(scenario())
