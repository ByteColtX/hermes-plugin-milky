"""真实 multipart parser 的字节流、断线和受控暂存边界。"""

import asyncio

import pytest

from dashboard.host import ManagementError
from dashboard.uploads import UploadStore
from tests.test_sticker_maintenance import _PNG


class Stream:
    def __init__(self, body):
        self.headers = {"content-type": "multipart/form-data; boundary=synthetic"}
        self.body = body

    async def stream(self):
        for start in range(0, len(self.body), 7):
            yield self.body[start : start + 7]


def body(data=_PNG):
    return (
        b'--synthetic\r\nContent-Disposition: form-data; name="files"; filename="../../image.png"\r\nContent-Type: image/png\r\n\r\n'
        + data
        + b"\r\n--synthetic--\r\n"
    )


def test_complete_stream_stays_in_batch(tmp_path):
    store = UploadStore(tmp_path)
    result = asyncio.run(store.receive_stream(Stream(body())))
    root, candidates = store.candidates(result["batch_id"], result["file_ids"])
    assert candidates[0][1].parent == root
    assert candidates[0][1].read_bytes() == _PNG
    assert not (tmp_path / "image.png").exists()


def test_incomplete_stream_cannot_become_candidate(tmp_path):
    store = UploadStore(tmp_path)
    with pytest.raises(ManagementError):
        asyncio.run(store.receive_stream(Stream(body()[:-22])))
    assert list(store.root.iterdir()) == []


def test_stream_actual_bytes_respect_quota(tmp_path, monkeypatch):
    from dashboard import uploads

    monkeypatch.setattr(uploads, "QUOTA", 10)
    store = UploadStore(tmp_path)
    with pytest.raises(ManagementError) as caught:
        asyncio.run(store.receive_stream(Stream(body())))
    assert caught.value.status == "quota_exceeded"
    assert list(store.root.iterdir()) == []


def test_single_and_batch_actual_byte_limits(tmp_path, monkeypatch):
    from dashboard import uploads

    monkeypatch.setattr(uploads, "MAX_IMAGE_BYTES", len(_PNG) - 1)
    store = UploadStore(tmp_path)
    with pytest.raises(ManagementError) as caught:
        asyncio.run(store.receive_stream(Stream(body())))
    assert caught.value.status == "too_large"
    assert list(store.root.iterdir()) == []
    monkeypatch.setattr(uploads, "MAX_IMAGE_BYTES", len(_PNG) + 1)
    monkeypatch.setattr(uploads, "BATCH_BYTES", len(_PNG) - 1)
    with pytest.raises(ManagementError) as caught:
        asyncio.run(store.receive_stream(Stream(body())))
    assert caught.value.status == "too_large"
    assert list(store.root.iterdir()) == []


class LargeStream:
    """以固定小块构造真实尺寸请求，避免在内存中拼接完整批次。"""

    def __init__(self, sizes):
        self.headers = {"content-type": "multipart/form-data; boundary=synthetic"}
        self.sizes = sizes

    async def stream(self):
        for size in self.sizes:
            yield b'--synthetic\r\nContent-Disposition: form-data; name="files"; filename="image.png"\r\n\r\n'
            remaining = size
            first = _PNG[:size]
            yield first
            remaining -= len(first)
            chunk = b"\0" * (64 * 1024)
            while remaining:
                current = min(len(chunk), remaining)
                yield chunk[:current]
                remaining -= current
            yield b"\r\n"
        yield b"--synthetic--\r\n"


def test_production_file_count_boundary(tmp_path):
    store = UploadStore(tmp_path)
    result = asyncio.run(store.receive_stream(LargeStream([len(_PNG)] * 50)))
    assert len(result["items"]) == 50
    store.discard(result["batch_id"])
    with pytest.raises(ManagementError) as caught:
        asyncio.run(store.receive_stream(LargeStream([len(_PNG)] * 51)))
    assert caught.value.status == "too_large"
    assert list(store.root.iterdir()) == []


def test_production_10mib_file_and_100mib_batch_boundary(tmp_path):
    from dashboard.uploads import BATCH_BYTES
    from stickers.validation import MAX_IMAGE_BYTES

    store = UploadStore(tmp_path)
    assert BATCH_BYTES == 10 * MAX_IMAGE_BYTES
    result = asyncio.run(store.receive_stream(LargeStream([MAX_IMAGE_BYTES] * 10)))
    root = store._batch(result["batch_id"])
    assert sum(p.stat().st_size for p in root.glob("*.png")) == BATCH_BYTES
    store.discard(result["batch_id"])
    for sizes in ([MAX_IMAGE_BYTES + 1], [MAX_IMAGE_BYTES] * 10 + [1]):
        with pytest.raises(ManagementError) as caught:
            asyncio.run(store.receive_stream(LargeStream(sizes)))
        assert caught.value.status == "too_large"
        assert list(store.root.iterdir()) == []
