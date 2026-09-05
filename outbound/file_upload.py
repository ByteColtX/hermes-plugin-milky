"""为 Hermes 文档附件选择 Milky 独立文件上传 Action。"""

from __future__ import annotations

from typing import Protocol

from config import DEFAULT_MAX_LOCAL_MEDIA_BYTES, validate_max_local_media_bytes
from milky.client import ActionError
from milky.models import MilkyEnvelope

from .materialization import prepare_materialization

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
    """将文档附件 materialize 后交给 Milky 独立文件上传 Action。"""

    def __init__(
        self,
        client: FileUploadClient,
        *,
        max_local_media_bytes: int = DEFAULT_MAX_LOCAL_MEDIA_BYTES,
    ) -> None:
        self._client = client
        self._max_local_media_bytes = validate_max_local_media_bytes(max_local_media_bytes)

    async def upload(
        self,
        scene: str,
        peer_id: int,
        file_path: object,
        file_name: object = None,
        *,
        parent_folder_id: object = _MISSING,
    ) -> MilkyEnvelope:
        """按 friend/group scene 读取并上传一次文件。"""

        if scene not in {"group", "dm"}:
            raise ActionError("unsupported", "file_upload", "target scene is unsupported")
        if scene == "dm" and parent_folder_id is not _MISSING:
            raise ActionError(
                "invalid_input", "upload_private_file", "parent_folder_id is unsupported"
            )
        attachment = await prepare_materialization(
            file_path,
            expected_kind="document",
            action="upload_group_file" if scene == "group" else "upload_private_file",
            file_name=file_name,
            max_local_media_bytes=self._max_local_media_bytes,
        )
        uri = attachment.uri
        name = attachment.file_name
        if name is None:  # pragma: no cover - document materialization always resolves a name
            raise ActionError("invalid_input", "file_upload", "file name is invalid")
        if scene == "group":
            return await self._upload_group(peer_id, uri, name, parent_folder_id=parent_folder_id)
        return await self._upload_private(peer_id, uri, name)

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


__all__ = ["FileUploadClient", "FileUploader"]
