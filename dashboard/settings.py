"""兼容 Dashboard 的共享设置模块入口，不引入 HTTP 依赖。"""

import sys

from management import settings

sys.modules[__name__] = settings
