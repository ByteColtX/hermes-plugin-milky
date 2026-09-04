"""`[SPLIT]` 出站契约使用的脱敏文本和交接事件。"""

SPLIT_TEXT_CASES = {
    "lf": {
        "value": "第一段\n[SPLIT]\n第二段",
        "sections": ("第一段", "第二段"),
    },
    "crlf": {
        "value": "第一段\r\n[SPLIT]\r\n第二段",
        "sections": ("第一段", "第二段"),
    },
    "lowercase": {
        "value": "第一段\n[split]\n第二段",
        "sections": None,
    },
    "mixed_case": {
        "value": "第一段\n[Split]\n第二段",
        "sections": None,
    },
    "leading_space": {
        "value": "第一段\n [SPLIT]\n第二段",
        "sections": None,
    },
    "trailing_space": {
        "value": "第一段\n[SPLIT] \n第二段",
        "sections": None,
    },
    "inline_prefix": {
        "value": "前文[SPLIT]\n第二段",
        "sections": None,
    },
    "inline_suffix": {
        "value": "第一段\n[SPLIT]后文",
        "sections": None,
    },
    "empty_edges": {
        "value": "[SPLIT]\n第一段\n[SPLIT]",
        "sections": ("第一段",),
    },
    "adjacent": {
        "value": "第一段\n[SPLIT]\n[SPLIT]\n第二段",
        "sections": ("第一段", "第二段"),
    },
    "more_than_three": {
        "value": "第一段\n[SPLIT]\n第二段\n[SPLIT]\n第三段\n[SPLIT]\n第四段",
        "sections": ("第一段", "第二段", "第三段", "第四段"),
    },
    "ordinary": {
        "value": "没有控制标记的普通文本",
        "sections": None,
    },
}

CQ_SPLIT_MESSAGE = "前段[CQ:at,qq=10001]\n[SPLIT]\n后段[CQ:reply,id=10002]"

ORDERED_ATTACHMENT_FIXTURE = (
    ("image", "base64://fixture-image", None),
    ("audio", "base64://fixture-audio", None),
    ("video", "base64://fixture-video", None),
    ("document", "base64://fixture-document", "fixture-report.txt"),
)

SENSITIVE_MARKERS = (
    "Authorization",
    "Bearer ",
    "MILKY_ACCESS_TOKEN",
    "http://",
    "https://",
    "/Users/",
    "/private/",
)
