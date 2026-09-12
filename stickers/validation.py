"""贴纸输入路径、图片格式和 content hash 校验。"""

from __future__ import annotations

import hashlib
import os
import re
import zlib
from dataclasses import dataclass
from pathlib import Path

MAX_IMAGE_BYTES = 10 * 1024 * 1024

_FORMAT_BY_SUFFIX = {
    ".png": ("png", "image/png"),
    ".jpg": ("jpeg", "image/jpeg"),
    ".jpeg": ("jpeg", "image/jpeg"),
    ".gif": ("gif", "image/gif"),
    ".webp": ("webp", "image/webp"),
}
_CANONICAL_SUFFIX = {"png": ".png", "jpeg": ".jpg", "gif": ".gif", "webp": ".webp"}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ImageCandidate:
    """经过确定性校验的 inbox 图片。"""

    path: Path
    file_sha256: str
    image_format: str
    mime_type: str
    size_bytes: int

    @property
    def suffix(self) -> str:
        """返回 content-addressed 文件使用的规范后缀。"""

        return _CANONICAL_SUFFIX[self.image_format]


def _is_within(path: Path, root: Path) -> bool:
    """检查解析后的路径是否仍在受控根目录内。"""

    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except (OSError, ValueError):
        return False
    return True


def ensure_regular_image_path(path: Path, inbox: Path) -> None:
    """拒绝越界、符号链接、目录和特殊文件。"""

    if not _is_within(path, inbox):
        raise ValueError("path is outside inbox")
    try:
        stat = path.lstat()
    except OSError as error:
        raise ValueError("file is unreadable") from error
    if not os.path.isfile(path) or os.path.islink(path) or not _is_regular_mode(stat.st_mode):
        raise ValueError("file is not a regular non-symlink")


def _is_regular_mode(mode: int) -> bool:
    """不跟随路径的前提下判断 POSIX regular file。"""

    return (mode & 0o170000) == 0o100000


def _read_limited(path: Path) -> tuple[bytes, str, int]:
    """流式读取并计算 hash，拒绝空文件和超过上限的文件。"""

    digest = hashlib.sha256()
    prefix = bytearray()
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            if len(prefix) < 512:
                prefix.extend(chunk[: 512 - len(prefix)])
            total += len(chunk)
            if total > MAX_IMAGE_BYTES:
                raise ValueError("image exceeds size limit")
            digest.update(chunk)
    if total == 0:
        raise ValueError("image is empty")
    return bytes(prefix), digest.hexdigest(), total


def _png_valid(data: bytes) -> bool:
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) < 33:
        return False
    offset = 8
    saw_ihdr = False
    saw_idat = False
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        kind = data[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(data):
            return False
        expected_crc = int.from_bytes(data[end - 4 : end], "big")
        actual_crc = zlib.crc32(data[offset + 4 : offset + 8 + length]) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            return False
        if not saw_ihdr:
            if kind != b"IHDR" or length != 13:
                return False
            width = int.from_bytes(data[offset + 8 : offset + 12], "big")
            height = int.from_bytes(data[offset + 12 : offset + 16], "big")
            if width == 0 or height == 0:
                return False
            saw_ihdr = True
        elif kind == b"IDAT":
            saw_idat = True
        if kind == b"IEND":
            return saw_ihdr and saw_idat and length == 0 and end == len(data)
        offset = end
    return False


def _jpeg_valid(data: bytes) -> bool:
    if not data.startswith(b"\xff\xd8") or len(data) < 4:
        return False
    index = 2
    saw_frame = False
    while index < len(data):
        if data[index] != 0xFF:
            return False
        while index < len(data) and data[index] == 0xFF:
            index += 1
        if index >= len(data):
            return False
        marker = data[index]
        index += 1
        if marker == 0xD9:
            return saw_frame
        if marker in (0xD8,):
            continue
        if marker == 0xDA:
            if index + 2 > len(data):
                return False
            length = int.from_bytes(data[index : index + 2], "big")
            if length < 2 or index + length > len(data):
                return False
            index += length
            end = data.find(b"\xff\xd9", index)
            return saw_frame and end >= 0 and end + 2 == len(data)
        if marker == 0x00 or 0xD0 <= marker <= 0xD7:
            return False
        if index + 2 > len(data):
            return False
        length = int.from_bytes(data[index : index + 2], "big")
        if length < 2 or index + length > len(data):
            return False
        if 0xC0 <= marker <= 0xC3 or 0xC5 <= marker <= 0xC7 or 0xC9 <= marker <= 0xCB:
            if length < 7:
                return False
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            if width == 0 or height == 0:
                return False
            saw_frame = True
        index += length
    return False


def _gif_valid(data: bytes) -> bool:
    if len(data) < 13 or data[:6] not in (b"GIF87a", b"GIF89a"):
        return False
    width = int.from_bytes(data[6:8], "little")
    height = int.from_bytes(data[8:10], "little")
    if width == 0 or height == 0:
        return False
    packed = data[10]
    index = 13
    if packed & 0x80:
        index += 3 * (2 ** ((packed & 0x07) + 1))
    if index > len(data):
        return False
    saw_image = False
    while index < len(data):
        marker = data[index]
        index += 1
        if marker == 0x3B:
            return saw_image and index == len(data)
        if marker == 0x21:
            if index >= len(data):
                return False
            index += 1
            while True:
                if index >= len(data):
                    return False
                size = data[index]
                index += 1
                if size == 0:
                    break
                index += size
                if index > len(data):
                    return False
            continue
        if marker != 0x2C or index + 9 > len(data):
            return False
        image_width = int.from_bytes(data[index + 5 : index + 7], "little")
        image_height = int.from_bytes(data[index + 7 : index + 9], "little")
        if image_width == 0 or image_height == 0:
            return False
        image_packed = data[index + 9]
        index += 10
        if image_packed & 0x80:
            index += 3 * (2 ** ((image_packed & 0x07) + 1))
        if index >= len(data):
            return False
        index += 1
        while True:
            if index >= len(data):
                return False
            size = data[index]
            index += 1
            if size == 0:
                break
            index += size
            if index > len(data):
                return False
        saw_image = True
    return False


def _webp_valid(data: bytes) -> bool:
    if len(data) < 16 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return False
    riff_size = int.from_bytes(data[4:8], "little")
    if riff_size + 8 != len(data):
        return False
    index = 12
    saw_image = False
    while index + 8 <= len(data):
        chunk_type = data[index : index + 4]
        size = int.from_bytes(data[index + 4 : index + 8], "little")
        end = index + 8 + size + (size & 1)
        if end > len(data):
            return False
        payload = data[index + 8 : index + 8 + size]
        if (chunk_type == b"VP8 " and len(payload) >= 10 and payload[6:9] == b"\x9d\x01\x2a") or (
            chunk_type == b"VP8L" and len(payload) >= 5 and payload[0] == 0x2F
        ):
            saw_image = True
        elif chunk_type == b"VP8X" and len(payload) >= 10:
            width = 1 + int.from_bytes(payload[4:7], "little")
            height = 1 + int.from_bytes(payload[7:10], "little")
            saw_image = width > 0 and height > 0
        index = end
    return saw_image and index == len(data)


def _detect_format(prefix: bytes, data: bytes) -> str | None:
    if _png_valid(data):
        return "png"
    if _jpeg_valid(data):
        return "jpeg"
    if _gif_valid(data):
        return "gif"
    if _webp_valid(data):
        return "webp"
    del prefix
    return None


def validate_image_file(path: Path, inbox: Path) -> ImageCandidate:
    """验证 inbox 图片并返回流式 hash 结果。"""

    path = Path(path)
    inbox = Path(inbox)
    ensure_regular_image_path(path, inbox)
    prefix, file_sha256, size_bytes = _read_limited(path)
    # 结构检查需要完整 bytes，但上限已经在流式读取阶段固定为 10 MiB。
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ValueError("image is unreadable") from error
    image_format = _detect_format(prefix, data)
    suffix = path.suffix.lower()
    expected = _FORMAT_BY_SUFFIX.get(suffix)
    if image_format is None or expected is None or expected[0] != image_format:
        raise ValueError("image format is unsupported or extension mismatches content")
    return ImageCandidate(path, file_sha256, image_format, expected[1], size_bytes)


def validate_library_name(path: Path, library: Path) -> tuple[str, str] | None:
    """验证库内 content-addressed 文件名并返回 hash 与格式。"""

    path = Path(path)
    library = Path(library)
    if not _is_within(path, library) or path.is_symlink() or not path.is_file():
        return None
    stem = path.stem.lower()
    suffix = path.suffix.lower()
    if not _HEX64.fullmatch(stem):
        return None
    if path.parent.name.lower() != stem[:2]:
        return None
    expected = _FORMAT_BY_SUFFIX.get(suffix)
    if expected is None:
        return None
    return stem, expected[0]


__all__ = [
    "MAX_IMAGE_BYTES",
    "ImageCandidate",
    "ensure_regular_image_path",
    "validate_image_file",
    "validate_library_name",
]
