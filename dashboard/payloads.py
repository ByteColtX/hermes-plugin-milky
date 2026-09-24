"""任务持久化前验证明确对象与有限元数据，不接收任意字段。"""

from .host import ManagementError


def opaque(value, length=48):
    """检查服务端生成的十六进制标识。"""
    return (
        isinstance(value, str)
        and len(value) == length
        and all(c in "0123456789abcdef" for c in value)
    )


def validate(operation, payload):
    """完整拒绝非法候选，任何输入校验均先于任务持久化。"""
    from stickers.maintenance import _parse_edit_options, _parse_id

    keys = {
        "import": {"batch_id", "file_ids"},
        "edit": {"targets", "sets", "clears"},
        "delete": {"targets"},
        "reanalyze": {"targets"},
        "cleanup": {"plan_id"},
        "reindex": set(),
        "reclaim_uploads": set(),
    }
    if not isinstance(operation, str) or operation not in keys or not isinstance(payload, dict):
        raise ManagementError("invalid_input")
    required = keys[operation] - ({"sets", "clears"} if operation == "edit" else set())
    if set(payload) - keys[operation] or required - set(payload):
        raise ManagementError("invalid_input")
    if operation == "import":
        ids = payload["file_ids"]
        if (
            not opaque(payload["batch_id"])
            or not isinstance(ids, list)
            or not 1 <= len(ids) <= 50
            or not all(opaque(x) for x in ids)
            or len(set(ids)) != len(ids)
        ):
            raise ManagementError("invalid_input")
    if operation == "cleanup" and not opaque(payload["plan_id"]):
        raise ManagementError("invalid_input")
    if "targets" in payload:
        targets = payload["targets"]
        if not isinstance(targets, list) or not 1 <= len(targets) <= 50:
            raise ManagementError("invalid_input")
        seen = set()
        for target in targets:
            if (
                not isinstance(target, dict)
                or set(target) != {"sticker_id", "version"}
                or not opaque(target["version"], 64)
            ):
                raise ManagementError("invalid_input")
            try:
                _parse_id(target["sticker_id"])
            except (ValueError, TypeError):
                raise ManagementError("invalid_input") from None
            if target["sticker_id"] in seen:
                raise ManagementError("invalid_input")
            seen.add(target["sticker_id"])
    if operation == "edit":
        sets, clears = payload.get("sets", {}), payload.get("clears", [])
        if (
            not isinstance(sets, dict)
            or not isinstance(clears, list)
            or not all(isinstance(x, str) for x in clears)
        ):
            raise ManagementError("invalid_input")
        options = []
        for key, value in sets.items():
            if key == "tags" and isinstance(value, list) and all(isinstance(x, str) for x in value):
                value = ",".join(value)
            if not isinstance(value, str) or len(value) > 1000:
                raise ManagementError("invalid_input")
            options.append(f"--{key}={value}")
        if clears:
            options.append("--clear=" + ",".join(clears))
        try:
            _parse_edit_options(options)
        except ValueError:
            raise ManagementError("invalid_input") from None
