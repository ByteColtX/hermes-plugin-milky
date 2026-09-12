"""兼容性导出：贴纸持久化实现位于 :mod:`stickers.storage`。"""

from .storage import PLUGIN_NAME, SCHEMA_VERSION, STICKER_DB_FILENAME, StickerPaths, StickerStore

__all__ = ["PLUGIN_NAME", "SCHEMA_VERSION", "STICKER_DB_FILENAME", "StickerPaths", "StickerStore"]
