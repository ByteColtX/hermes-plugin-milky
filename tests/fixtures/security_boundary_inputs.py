"""安全边界测试使用的合成 Tool、资源和协议输入。"""

SYNTHETIC_TOOL_ARGUMENTS = {
    "group_id": 700000001,
    "user_id": 800000002,
    "extension_field": "fixture-business-extension",
}

SYNTHETIC_TOOL_ENVELOPE = {
    "status": "ok",
    "retcode": 0,
    "data": {
        "group_id": 700000001,
        "extension_field": "fixture-business-extension",
    },
    "message": "fixture-result-message",
    "envelope_extension": "fixture-envelope-extension",
}

SYNTHETIC_RESOURCE_REFERENCES = {
    "image_url": "https://media.example.invalid/fixture-image",
    "file_url": "https://media.example.invalid/fixture-file",
    "file_id": "fixture-file-id",
    "file_name": "fixture-report.txt",
}

SYNTHETIC_PROTOCOL_VALUES = {
    "self_id": 900000001,
    "peer_id": 700000001,
    "sender_id": 800000002,
    "message_id": "1005",
    "body": "合成占位正文",
}


__all__ = [
    "SYNTHETIC_PROTOCOL_VALUES",
    "SYNTHETIC_RESOURCE_REFERENCES",
    "SYNTHETIC_TOOL_ARGUMENTS",
    "SYNTHETIC_TOOL_ENVELOPE",
]
