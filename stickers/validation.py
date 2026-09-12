"""贴纸输入路径、图片格式和 content hash 校验。"""

from __future__ import annotations

import hashlib
import io
import os
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

MAX_IMAGE_BYTES = 10 * 1024 * 1024

_FORMAT_BY_SUFFIX = {
    ".png": ("png", "image/png"),
    ".jpg": ("jpeg", "image/jpeg"),
    ".jpeg": ("jpeg", "image/jpeg"),
    ".gif": ("gif", "image/gif"),
    ".webp": ("webp", "image/webp"),
}
_FORMAT_BY_PIL_FORMAT = {
    "PNG": ("png", "image/png"),
    "JPEG": ("jpeg", "image/jpeg"),
    "GIF": ("gif", "image/gif"),
    "WEBP": ("webp", "image/webp"),
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
    payload = bytearray()
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_IMAGE_BYTES:
                raise ValueError("image exceeds size limit")
            digest.update(chunk)
            payload.extend(chunk)
    if total == 0:
        raise ValueError("image is empty")
    return bytes(payload), digest.hexdigest(), total


def _detect_format(data: bytes) -> tuple[str, str] | None:
    """使用 Pillow 验证图片结构并返回内部格式和 MIME。"""

    try:
        with Image.open(io.BytesIO(data)) as image:
            image_format = _FORMAT_BY_PIL_FORMAT.get(image.format or "")
            if image_format is None:
                return None
            image.verify()
            return image_format
    except Exception:  # noqa: BLE001 - 解码器异常统一归类为 rejected
        return None


def validate_image_file(path: Path, inbox: Path) -> ImageCandidate:
    """验证 inbox 图片并返回流式 hash 结果。"""

    candidate, _data = read_validated_image_file(path, inbox)
    return candidate


def read_validated_image_file(path: Path, inbox: Path) -> tuple[ImageCandidate, bytes]:
    """验证图片并返回与 hash 校验使用的同一份文件内容。"""

    path = Path(path)
    inbox = Path(inbox)
    ensure_regular_image_path(path, inbox)
    data, file_sha256, size_bytes = _read_limited(path)
    image_format = _detect_format(data)
    suffix = path.suffix.lower()
    expected = _FORMAT_BY_SUFFIX.get(suffix)
    if image_format is None or expected is None or expected != image_format:
        raise ValueError("image format is unsupported or extension mismatches content")
    return ImageCandidate(path, file_sha256, image_format[0], image_format[1], size_bytes), data


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
    "read_validated_image_file",
    "validate_image_file",
    "validate_library_name",
]
