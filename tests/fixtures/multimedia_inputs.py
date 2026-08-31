"""多媒体出站测试使用的脱敏输入形状。"""

SYNTHETIC_MEDIA_URIS = {
    "remote_image": "https://media.example.invalid/fixture-image.png",
    "remote_animation": "http://media.example.invalid/fixture-animation.gif",
    "inline_audio": "base64://UklGRg==",
    "local_image": "/fixture/workspace/image.png",
    "local_audio": "file:///fixture/workspace/audio.ogg",
    "local_video": "/fixture/workspace/video.mp4",
    "local_document": "/fixture/workspace/report.txt",
    "empty": "",
    "unknown_scheme": "ftp://media.example.invalid/fixture.bin",
}

SYNTHETIC_FILE_NAMES = {
    "image": "fixture-image.png",
    "audio": "fixture-audio.ogg",
    "video": "fixture-video.mp4",
    "document": "fixture-report.txt",
}

# 记录本次接口收缩后的所有权，避免把 Hermes 继承入口和插件实现混为一谈。
MEDIA_ENTRY_OWNERSHIP = {
    "adapter_native": (
        "send",
        "send_image",
        "send_image_file",
        "send_voice",
        "send_video",
        "send_document",
    ),
    "adapter_inherited": ("send_animation", "send_multiple_images"),
    "sender_native": ("send", "send_image", "send_voice", "send_video", "send_document"),
    "sender_removed": ("send_animation", "send_image_file", "send_file"),
    "adapter_removed": ("send_animation", "send_file"),
}

SENSITIVE_MEDIA_MARKERS = (
    "Authorization",
    "Bearer ",
    "fixture-access-token",
    "base64://UklGRg==",
    "/Users/",
    "/private/",
)
