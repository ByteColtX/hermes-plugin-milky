"""为 Hermes 文档附件选择 Milky 独立文件上传 Action。"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlsplit

from milky.client import ActionError
from milky.models import MilkyEnvelope

_MISSING = object()


class FileUploadClient(Protocol):
    """定义文件上传所需的 Milky client 能力。"""

    async def upload_group_file(
        self,
        group_id: object,
        file_uri: object,
        file_name: object,
        *,
        parent_folder_id: object = None,
    ) -> MilkyEnvelope:
        """使用显式 Milky file URI 上传群文件。"""

    async def upload_private_file(
        self, user_id: object, file_uri: object, file_name: object
    ) -> MilkyEnvelope:
        """使用显式 Milky file URI 上传私聊文件。"""

    async def upload_group_file_from_path(
        self,
        group_id: object,
        file_path: object,
        file_name: object,
        *,
        parent_folder_id: object = None,
    ) -> MilkyEnvelope:
        """把本地文件交给已确认的 client path seam。"""

    async def upload_private_file_from_path(
        self, user_id: object, file_path: object, file_name: object
    ) -> MilkyEnvelope:
        """把本地文件交给已确认的 client path seam。"""


class FileUploader:
    """选择安全的显式 URI 或 client 本地文件入口，不把路径直接发给 Milky。"""

    def __init__(self, client: FileUploadClient) -> None:
        self._client = client

    async def upload(
        self,
        scene: str,
        peer_id: int,
        file_path: object,
        file_name: object = None,
        *,
        parent_folder_id: object = _MISSING,
    ) -> MilkyEnvelope:
        """按 friend/group scene 上传文件，并返回已校验的 envelope。"""

        name = _file_name(file_name, file_path)
        if scene == "group":
            return await self._upload_group(
                peer_id, file_path, name, parent_folder_id=parent_folder_id
            )
        if scene == "dm":
            if parent_folder_id is not _MISSING:
                raise ActionError(
                    "invalid_input", "upload_private_file", "parent_folder_id is unsupported"
                )
            return await self._upload_private(peer_id, file_path, name)
        raise ActionError("unsupported", "file_upload", "target scene is unsupported")

    async def _upload_group(
        self,
        group_id: int,
        value: object,
        name: str,
        *,
        parent_folder_id: object,
    ) -> MilkyEnvelope:
        """执行群文件上传。"""

        uri = _explicit_uri(value)
        if uri is not None and not uri.startswith("file://"):
            if parent_folder_id is _MISSING:
                return await self._client.upload_group_file(group_id, uri, name)
            return await self._client.upload_group_file(
                group_id, uri, name, parent_folder_id=parent_folder_id
            )
        path = _local_path(value, "upload_group_file")
        if parent_folder_id is _MISSING:
            return await self._client.upload_group_file_from_path(group_id, path, name)
        return await self._client.upload_group_file_from_path(
            group_id, path, name, parent_folder_id=parent_folder_id
        )

    async def _upload_private(self, user_id: int, value: object, name: str) -> MilkyEnvelope:
        """执行私聊文件上传。"""

        uri = _explicit_uri(value)
        if uri is not None and not uri.startswith("file://"):
            return await self._client.upload_private_file(user_id, uri, name)
        path = _local_path(value, "upload_private_file")
        return await self._client.upload_private_file_from_path(user_id, path, name)


def _explicit_uri(value: object) -> str | None:
    """返回协议明确支持的非本地 URI。"""

    if not isinstance(value, str):
        return None
    normalized = value.strip()
    parsed = urlsplit(normalized)
    if parsed.scheme in {"http", "https"}:
        if not parsed.netloc:
            raise ActionError("invalid_input", "file_upload", "file URI is invalid")
        return normalized
    if parsed.scheme == "base64":
        if not parsed.netloc and not parsed.path:
            raise ActionError("invalid_input", "file_upload", "file URI is invalid")
        return normalized
    return None


def _local_path(value: object, action: str) -> Path:
    """将本地路径转换为 client path seam 的输入且不回显路径。"""

    if not isinstance(value, (str, Path)):
        raise ActionError("invalid_input", action, "file path is invalid")
    raw = str(value)
    if raw.startswith("file://"):
        parsed = urlsplit(raw)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            raise ActionError("invalid_input", action, "file path is invalid")
        raw = unquote(parsed.path)
    if not raw.strip():
        raise ActionError("invalid_input", action, "file path is invalid")
    path = Path(raw)
    try:
        if not path.is_file():
            raise ActionError("invalid_input", action, "file path is unavailable")
    except OSError:
        raise ActionError("invalid_input", action, "file path is unavailable") from None
    return path


def _file_name(value: object, file_path: object) -> str:
    """确定用户可见文件名，拒绝空值和目录穿越片段。"""

    if value is None:
        if isinstance(file_path, Path):
            name = file_path.name
        elif isinstance(file_path, str):
            parsed = urlsplit(file_path)
            name = Path(unquote(parsed.path or file_path)).name
        else:
            name = ""
    elif isinstance(value, str):
        if "/" in value or "\\" in value:
            raise ActionError("invalid_input", "file_upload", "file name is invalid")
        name = Path(value).name
    else:
        name = ""
    if not name or name in {".", ".."}:
        raise ActionError("invalid_input", "file_upload", "file name is invalid")
    return name


__all__ = ["FileUploadClient", "FileUploader"]
