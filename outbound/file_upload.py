"""为 Hermes 文档附件选择 Milky 独立文件上传 Action。"""

from __future__ import annotations

from typing import Protocol
from urllib.parse import unquote, urlsplit

from milky.client import ActionError, validate_media_uri
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


class FileUploader:
    """只上传 Hermes 已 materialize 的显式 URI，不读取主机文件。"""

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

        if scene == "group":
            uri = validate_media_uri(file_path, action="upload_group_file")
            name = _file_name(file_name, uri)
            return await self._upload_group(peer_id, uri, name, parent_folder_id=parent_folder_id)
        if scene == "dm":
            if parent_folder_id is not _MISSING:
                raise ActionError(
                    "invalid_input", "upload_private_file", "parent_folder_id is unsupported"
                )
            uri = validate_media_uri(file_path, action="upload_private_file")
            return await self._upload_private(peer_id, uri, _file_name(file_name, uri))
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

        if parent_folder_id is _MISSING:
            return await self._client.upload_group_file(group_id, value, name)
        return await self._client.upload_group_file(
            group_id, value, name, parent_folder_id=parent_folder_id
        )

    async def _upload_private(self, user_id: int, value: object, name: str) -> MilkyEnvelope:
        """执行私聊文件上传。"""

        return await self._client.upload_private_file(user_id, value, name)


def _file_name(value: object, file_path: object) -> str:
    """从显式文件名或远端 URI 确定上传名称。"""

    if value is None:
        if not isinstance(file_path, str):
            name = ""
        else:
            parsed = urlsplit(file_path)
            if parsed.scheme == "base64":
                raise ActionError("invalid_input", "file_upload", "file name is required")
            name = unquote(parsed.path.rsplit("/", 1)[-1])
    elif isinstance(value, str):
        if "/" in value or "\\" in value:
            raise ActionError("invalid_input", "file_upload", "file name is invalid")
        name = value
    else:
        name = ""
    if not name or name in {".", ".."}:
        raise ActionError("invalid_input", "file_upload", "file name is invalid")
    return name


__all__ = ["FileUploadClient", "FileUploader"]
