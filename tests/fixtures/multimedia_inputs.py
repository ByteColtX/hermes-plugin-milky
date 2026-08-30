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

SENSITIVE_MEDIA_MARKERS = (
    "Authorization",
    "Bearer ",
    "fixture-access-token",
    "base64://UklGRg==",
    "/Users/",
    "/private/",
)
