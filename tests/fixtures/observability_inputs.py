"""可观察性测试使用的脱敏合成输入。"""

SYNTHETIC_IDENTIFIERS = {
    "self_id": 900000001,
    "sender_id": 800000002,
    "peer_id": 700000003,
    "message_id": "1005",
    "file_id": "fixture-file-id",
}

SENSITIVE_INPUTS = {
    "url": "https://fixture.invalid/media/item",
    "body": "合成敏感正文，不应进入日志",
    "path": "/private/fixture/media.bin",
    "exception_detail": "remote payload synthetic-credential-input",
}

CORRELATION_FIXTURE = {
    "chat_key": "group:700000003",
    "ingress_sequence": 17,
    "history_count": 2,
    "materialized_count": 1,
    "degraded_count": 1,
    "chunk_count": 2,
    "attachment_count": 1,
}
