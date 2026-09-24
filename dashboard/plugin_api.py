"""Hermes 挂载的管理路由；认证与来源检查由宿主执行。"""

from __future__ import annotations

import asyncio
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

_PLUGIN_ROOT = str(Path(__file__).resolve().parents[1])
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from dashboard.host import ManagementError, profile_scope, profiles, storage_root
from dashboard.jobs import JobManager
from dashboard.uploads import UploadStore
from stickers.errors import StickerError
from stickers.management import StickerManagementService

_MANAGERS = {}
_MANAGER_LOCK = threading.Lock()


@asynccontextmanager
async def lifetime(_app):
    """仅在宿主生命周期中接收请求并关闭本实例拥有的任务。"""
    try:
        yield
    finally:
        await asyncio.gather(*(manager.close() for manager in _MANAGERS.values()))
        _MANAGERS.clear()


router = APIRouter(lifespan=lifetime)


async def scoped(profile, action):
    """在线程内绑定宿主范围，避免文件和配置读取阻塞事件循环。"""

    def execute():
        with profile_scope(profile) as confirmed:
            return action(confirmed)

    try:
        return await asyncio.to_thread(execute)
    except (ManagementError, StickerError) as error:
        status = error.status if isinstance(error, ManagementError) else error.classification
        code = {"not_found": 404, "disabled": 404, "conflict": 409, "unsupported": 501}.get(
            status, 400
        )
        return JSONResponse(
            {
                "status": status,
                **(
                    {"field": error.field}
                    if isinstance(error, ManagementError) and error.field
                    else {}
                ),
            },
            status_code=code,
        )
    except Exception:  # noqa: BLE001 - 固定错误类别避免泄漏宿主与存储异常
        return JSONResponse({"status": "storage_error"}, status_code=500)


@router.get("/profiles")
async def profile_list():
    """返回宿主确认且已启用本插件的 profile。"""
    try:
        return await asyncio.to_thread(profiles)
    except Exception:  # noqa: BLE001 - 作用域无法确认时关闭入口
        return JSONResponse({"status": "unsupported"}, status_code=501)


@router.get("/gallery")
async def gallery(
    profile: str,
    page: int = 1,
    limit: int = 20,
    emotion: str | None = None,
    tag: str | None = None,
    description: str | None = None,
):
    """只读图库分页，不创建存储或任务。"""
    return await scoped(
        profile,
        lambda confirmed: StickerManagementService(storage_root(confirmed)).browse(
            page=page, limit=limit, emotion=emotion, tag=tag, description=description
        ),
    )


@router.get("/gallery/{sticker_id}/preview")
async def preview(profile: str, sticker_id: str):
    """交付受限认证媒体，并禁止浏览器及共享缓存。"""

    def read(confirmed):
        data, mime = StickerManagementService(storage_root(confirmed)).preview(sticker_id)
        return Response(
            data,
            media_type=mime,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Vary": "Cookie, Authorization, X-Hermes-Session-Token",
            },
        )

    return await scoped(profile, read)


async def bounded_json(request: Request):
    """实际接收字节受限，不将原始字段写入日志。"""
    import json

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 128 * 1024:
            raise ManagementError("invalid_input")
    try:
        value = json.loads(body)
    except (ValueError, UnicodeError):
        raise ManagementError("invalid_input") from None
    if not isinstance(value, dict):
        raise ManagementError("invalid_input")
    return value


@router.get("/config")
async def config_read(profile: str):
    """展示当前范围配置与保存来源。"""
    from dashboard import settings

    return await scoped(profile, lambda _confirmed: settings.read())


@router.patch("/config")
async def config_save(profile: str, request: Request):
    """拒绝未知请求字段，仅提交显式变化键。"""
    from dashboard import settings

    try:
        body = await bounded_json(request)
        if set(body) != {"version", "changes"}:
            raise ManagementError("invalid_input")
    except ManagementError:
        return JSONResponse({"status": "invalid_input"}, status_code=400)
    return await scoped(profile, lambda _confirmed: settings.save(body["version"], body["changes"]))


@router.post("/credential")
async def credential_save(profile: str, request: Request):
    """独立凭证操作不复制到普通设置。"""
    from dashboard import settings

    try:
        body = await bounded_json(request)
        if set(body) - {"action", "value"} or "action" not in body:
            raise ManagementError("invalid_input")
    except ManagementError:
        return JSONResponse({"status": "invalid_input"}, status_code=400)
    return await scoped(
        profile, lambda _confirmed: settings.credential(body["action"], body.get("value", ""))
    )


def manager_for(confirmed):
    """每实例各自拥有任务管理器，按宿主确认根隔离。"""
    key = str(confirmed)
    with _MANAGER_LOCK:
        if key not in _MANAGERS:
            _MANAGERS[key] = JobManager(storage_root(confirmed))
            _MANAGERS[key].recover()
        return _MANAGERS[key]


def enabled(profile):
    """派发和提交边界重新核查目标 profile 的启用状态。"""
    try:
        with profile_scope(profile):
            return True
    except Exception:  # noqa: BLE001 - 作用域无法确认按停用处理
        return False


async def execute_operation(profile, confirmed, operation, payload, guard):
    """所有图库变更共享持久任务与创建时冻结的 profile。"""
    root = storage_root(confirmed)
    gallery = StickerManagementService(root)
    progress = getattr(guard, "progress", lambda items: None)
    with profile_scope(profile):
        guard()
        if operation in {"edit", "delete"}:
            return await asyncio.to_thread(
                gallery.mutate,
                operation,
                payload.get("targets"),
                sets=payload.get("sets"),
                clears=payload.get("clears"),
                guard=guard,
                progress=progress,
            )
        if operation == "reanalyze":
            return await gallery.reanalyze_targets(
                payload.get("targets"), guard=guard, progress=progress
            )
        if operation == "import":
            uploads = UploadStore(root)
            batch_id = payload.get("batch_id")
            input_root, candidates = uploads.candidates(batch_id, payload.get("file_ids"))
            return await gallery.import_candidates(
                input_root, candidates, guard=guard, progress=progress
            )
        if operation == "cleanup":
            return await asyncio.to_thread(
                gallery.cleanup_execute, payload.get("plan_id"), guard=guard
            )
        if operation == "reclaim_uploads":
            return await asyncio.to_thread(UploadStore(root).reclaim)
        if operation == "reindex":
            from stickers.coordination import library_guard
            from stickers.maintenance import StickerMaintenanceService

            def reindex():
                if not root.exists():
                    return {"status": "empty"}
                with library_guard(root):
                    guard()
                    return StickerMaintenanceService(data_dir=root).reindex()

            return await asyncio.to_thread(reindex)
        raise ManagementError("unsupported")


@router.post("/requests")
async def issue_request(profile: str, request: Request):
    """签发绑定本 profile 和操作的期限请求标识。"""
    try:
        body = await bounded_json(request)
        if set(body) != {"operation"}:
            raise ManagementError("invalid_input")
    except ManagementError:
        return JSONResponse({"status": "invalid_input"}, status_code=400)
    return await scoped(profile, lambda confirmed: manager_for(confirmed).issue(body["operation"]))


@router.post("/jobs")
async def submit_job(profile: str, request: Request):
    """持久记录提交后再启动执行层，重复请求不重复执行。"""
    try:
        body = await bounded_json(request)
        if set(body) != {"operation", "request_id", "payload"}:
            raise ManagementError("invalid_input")
        with profile_scope(profile) as confirmed:
            manager = manager_for(confirmed)
            from dashboard.payloads import validate
            from stickers.coordination import library_guard

            validate(body["operation"], body["payload"])
            manager.root.mkdir(parents=True, exist_ok=True)
            with library_guard(manager.root):
                if body["operation"] == "import":
                    UploadStore(manager.root).candidates(
                        body["payload"]["batch_id"], body["payload"]["file_ids"]
                    )
                result = manager.submit(body["request_id"], body["operation"], body["payload"])
            manager.start(
                lambda operation, payload, guard: execute_operation(
                    profile, confirmed, operation, payload, guard
                ),
                lambda: enabled(profile),
            )
            return result
    except ManagementError as error:
        return JSONResponse(
            {"status": error.status},
            status_code=409 if error.status in {"conflict", "busy", "expired"} else 400,
        )


@router.get("/jobs")
async def list_jobs(profile: str):
    """恢复查看不会重提或自动重放任务。"""
    return await scoped(profile, lambda confirmed: manager_for(confirmed).list())


@router.post("/jobs/{task_id}/cancel")
async def cancel_job(profile: str, task_id: str):
    """取消未开始项，保留此前已完成内容。"""
    return await scoped(profile, lambda confirmed: manager_for(confirmed).cancel(task_id))


@router.post("/cleanup/preview")
async def preview_cleanup(profile: str):
    """预览只生成有期限的明确对象计划。"""
    return await scoped(
        profile, lambda confirmed: StickerManagementService(storage_root(confirmed)).cleanup_plan()
    )


@router.get("/uploads")
async def list_uploads(profile: str):
    """恢复查看已有批次，不隐式重新导入。"""
    return await scoped(
        profile, lambda confirmed: UploadStore(storage_root(confirmed)).list_batches()
    )


@router.post("/uploads")
async def upload_batch(profile: str, request: Request):
    """宿主认证后的有界 multipart 图片批次。"""
    try:
        with profile_scope(profile) as confirmed:
            return await UploadStore(storage_root(confirmed)).receive_stream(request)
    except ManagementError as error:
        return JSONResponse({"status": error.status}, status_code=400)
    except Exception:  # noqa: BLE001 - multipart 原始输入不能进入响应
        return JSONResponse({"status": "invalid_input"}, status_code=400)


@router.delete("/uploads/{batch_id}")
async def discard_upload(profile: str, batch_id: str):
    """显式删除无活动任务引用的受控批次。"""
    return await scoped(
        profile, lambda confirmed: UploadStore(storage_root(confirmed)).discard(batch_id)
    )
