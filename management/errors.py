"""管理边界共享的固定错误分类。"""

PLUGIN_ID = "hermes-plugin-milky"


class ManagementError(Exception):
    """仅携带可对外展示的安全分类。"""

    def __init__(self, status: str, *, field: str | None = None):
        super().__init__(status)
        self.status = status
        self.field = field
