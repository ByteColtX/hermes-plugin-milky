"""同步视觉在超时后仍占名额，禁止额外派发与迟到提交。"""

import asyncio
import contextvars
import threading

import pytest

from stickers.errors import StickerError
from stickers.visual_worker import run_visual


def test_timeout_keeps_cross_process_slot_until_actual_completion(tmp_path):
    async def run():
        entered, finish, ended = threading.Event(), threading.Event(), threading.Event()
        scope = contextvars.ContextVar("scope", default="wrong")
        scope.set("expected")

        def slow():
            try:
                assert scope.get() == "expected"
                entered.set()
                finish.wait(5)
                return "late"
            finally:
                ended.set()

        with pytest.raises(TimeoutError):
            await run_visual(tmp_path, slow, timeout=0.02)
        assert entered.is_set()
        try:
            with pytest.raises(StickerError) as caught:
                await run_visual(tmp_path, lambda: "must not start")
            assert caught.value.classification == "busy"
        finally:
            finish.set()
            assert await asyncio.to_thread(ended.wait, 2)

    asyncio.run(run())
