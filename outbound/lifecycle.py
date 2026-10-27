"""提供出站资源的安全关闭辅助。"""

from __future__ import annotations

import inspect


async def close_quietly(resource: object | None) -> None:
    """尽力关闭资源且不让清理异常覆盖原始结果。"""

    close = getattr(resource, "close", None)
    if not callable(close):
        return
    try:
        result = close()
        if inspect.isawaitable(result):
            await result
    except Exception:  # noqa: BLE001 - 清理错误只能留在本地生命周期边界
        return


__all__ = ["close_quietly"]
