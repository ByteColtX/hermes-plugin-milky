"""按显式开关运行真实 Hermes prompt section 集成检查。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HERMES_ROOT = Path(
    os.environ.get("HERMES_SOURCE_ROOT", "/Users/bytecolt/PythonProjects/hermes-agent")
).resolve()


@pytest.mark.skipif(
    os.environ.get("RUN_HERMES_INTEGRATION") != "1",
    reason="真实 Hermes 集成必须显式使用 RUN_HERMES_INTEGRATION=1",
)
def test_real_hermes_prompt_lifecycle() -> None:
    """真实 Hermes 宿主验证新建、restore、rebuild 和 section 冻结。"""

    if not (HERMES_ROOT / "pyproject.toml").is_file():
        pytest.skip("当前环境没有 Hermes 源码 checkout")
    integration_python = os.environ.get("HERMES_INTEGRATION_PYTHON")
    if not integration_python:
        pytest.skip("需要 HERMES_INTEGRATION_PYTHON 指向 Python 3.13+ 的 Hermes 环境")
    if not Path(integration_python).is_file():
        pytest.skip("HERMES_INTEGRATION_PYTHON 不存在")
    result = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(HERMES_ROOT),
            "--python",
            integration_python,
            "--no-sync",
            str(PROJECT_ROOT / "scripts" / "hermes_prompt_integration.py"),
        ],
        cwd=PROJECT_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "real Hermes prompt integration: passed" in result.stdout
