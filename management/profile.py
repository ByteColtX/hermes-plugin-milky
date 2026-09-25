"""绑定注册时由宿主确认的 profile，不在命令中猜测环境来源。"""

from contextvars import copy_context

from config import _parse_allowed_chats, resolve_settings
from management import settings
from management.errors import ManagementError


class ProfileSettings:
    """在独立上下文副本中读取和保存同一注册 profile 的设置。"""

    def __init__(self) -> None:
        self._context = copy_context()
        try:
            from hermes_constants import get_hermes_home

            self.home = get_hermes_home().resolve()
        except ImportError:
            self.home = None

    def _run(self, method, *args):
        """拒绝注册来源不明或宿主作用域漂移。"""

        def invoke():
            from hermes_constants import get_hermes_home

            if self.home is None or get_hermes_home().resolve() != self.home:
                raise ManagementError("unsupported")
            return method(*args)

        return self._context.copy().run(invoke)

    def is_current(self) -> bool:
        """确认 core 当前执行 profile 与注册所有者相同，不借用其他 profile。"""
        try:
            from hermes_constants import get_hermes_home

            return self.home is not None and get_hermes_home().resolve() == self.home
        except Exception:  # noqa: BLE001 - 能力缺失保持 unsupported
            return False

    def read(self):
        """读取完整可核验版本与有效规则。"""
        return self._run(settings.read)

    def save(self, version, rules):
        """仅保存白名单单键，不更改其他配置。"""
        return self._run(settings.save, version, {"allowed_chats": sorted(rules)})

    def allowed_chats(self):
        """每次完整连接重新读取单项配置，不重新加载其他启动字段。"""

        def read_rules():
            native, legacy, _explicit, env, _token = settings._inputs()
            if "allowed_chats" in native or "allowed_chats" in legacy:
                resolved = resolve_settings(
                    settings={"allowed_chats": native["allowed_chats"]}
                    if "allowed_chats" in native
                    else {},
                    legacy={"allowed_chats": legacy["allowed_chats"]}
                    if "allowed_chats" in legacy
                    else {},
                    allow_missing=True,
                )
                return frozenset(resolved["effective"]["allowed_chats"])
            return _parse_allowed_chats(env.get("MILKY_ALLOWED_CHATS"))

        return self._run(read_rules)
