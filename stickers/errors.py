"""贴纸维护的内部错误分类。"""

from __future__ import annotations


class StickerError(Exception):
    """带有安全分类的内部异常。"""

    def __init__(self, classification: str, message: str = "") -> None:
        super().__init__(message)
        self.classification = classification


class StickerStorageError(StickerError):
    """贴纸数据库或文件存储不可用。"""

    def __init__(self, message: str = "") -> None:
        super().__init__("storage_error", message)


class StickerUnsupportedError(StickerError):
    """贴纸存储 schema 或宿主能力不受支持。"""

    def __init__(self, message: str = "") -> None:
        super().__init__("unsupported", message)
