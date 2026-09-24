"""真实图片格式、上传竞争与异常输入的边界。"""

import asyncio
import io
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image

from dashboard.host import ManagementError
from dashboard.uploads import UploadStore
from stickers.maintenance import StickerMaintenanceService
from stickers.management import StickerManagementService
from tests.test_dashboard_stream import Stream, body
from tests.test_dashboard_uploads import Upload
from tests.test_sticker_maintenance import _PNG, _vision


@pytest.mark.parametrize(
    "format_name,suffix", [("PNG", "png"), ("JPEG", "jpg"), ("GIF", "gif"), ("WEBP", "webp")]
)
def test_all_allowed_formats_import(tmp_path, monkeypatch, format_name, suffix):
    image = io.BytesIO()
    Image.new("RGB", (16, 16), "yellow").save(image, format=format_name)
    monkeypatch.setattr(
        StickerMaintenanceService, "_call_vision", lambda *_: _async_value(_vision())
    )

    async def run():
        uploads = UploadStore(tmp_path)
        batch = await uploads.receive([Upload(image.getvalue(), "image." + suffix)])
        root, candidates = uploads.candidates(batch["batch_id"], batch["file_ids"])
        result = await StickerManagementService(tmp_path).import_candidates(root, candidates)
        assert result["items"][0]["status"] == "created"
        assert not candidates[0][1].exists()

    asyncio.run(run())


async def _async_value(value):
    return value


def test_visual_failure_retains_input_and_junk_stays_outside_reclamation(tmp_path, monkeypatch):
    async def run():
        uploads = UploadStore(tmp_path, clock=lambda: 0)
        batch = await uploads.receive([Upload(_PNG)])
        root, candidates = uploads.candidates(batch["batch_id"], batch["file_ids"])
        manager = StickerManagementService(tmp_path)
        monkeypatch.setattr(
            StickerMaintenanceService, "_call_vision", lambda *_: _async_value("invalid")
        )
        failed = await manager.import_candidates(root, candidates)
        assert failed["items"][0]["status"] == "visual_unavailable"
        assert candidates[0][1].exists()
        monkeypatch.setattr(
            StickerMaintenanceService,
            "_call_vision",
            lambda *_: _async_value(_vision(is_sticker=False)),
        )
        result = await manager.import_candidates(root, candidates)
        assert result["items"][0]["status"] == "junk"
        junk = list((tmp_path / "stickers/junk").iterdir())
        assert len(junk) == 1
        uploads.clock = lambda: 8 * 86400
        uploads.reclaim()
        assert junk[0].exists()

    asyncio.run(run())


def test_concurrent_uploads_cannot_exceed_quota(tmp_path, monkeypatch):
    import dashboard.uploads as uploads_module

    monkeypatch.setattr(uploads_module, "QUOTA", len(_PNG))
    gate = threading.Barrier(2)

    def upload():
        gate.wait(timeout=3)
        try:
            asyncio.run(UploadStore(tmp_path).receive([Upload(_PNG)]))
            return "accepted"
        except ManagementError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: upload(), range(2)))
    assert sorted(outcomes) == ["accepted", "quota_exceeded"]
    assert sum(p.stat().st_size for p in (tmp_path / "web-uploads").glob("*/*.png")) == len(_PNG)


def test_disconnected_stream_immediately_removes_incomplete_input(tmp_path):
    class BrokenStream(Stream):
        async def stream(self):
            yield body()[:-22]
            raise ConnectionError("private transport details")

    store = UploadStore(tmp_path)
    with pytest.raises(ConnectionError):
        asyncio.run(store.receive_stream(BrokenStream(b"")))
    assert list(store.root.iterdir()) == []


def test_move_failure_keeps_input_and_does_not_claim_success(tmp_path, monkeypatch):
    from stickers import maintenance
    from stickers.errors import StickerStorageError

    async def run():
        uploads = UploadStore(tmp_path)
        batch = await uploads.receive([Upload(_PNG)])
        root, candidates = uploads.candidates(batch["batch_id"], batch["file_ids"])
        monkeypatch.setattr(
            StickerMaintenanceService, "_call_vision", lambda *_: _async_value(_vision())
        )

        def fail_move(*_):
            raise OSError("private storage details")

        monkeypatch.setattr(maintenance.os, "replace", fail_move)
        with pytest.raises(StickerStorageError):
            await StickerManagementService(tmp_path).import_candidates(root, candidates)
        assert candidates[0][1].exists()
        assert StickerManagementService(tmp_path).browse()["total"] == 0

    asyncio.run(run())
