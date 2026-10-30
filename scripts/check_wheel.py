"""Install and browser-test the built wheel with runtime deps, without Plotly."""

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

root = Path(__file__).parents[1]
wheel = max((root / "dist").glob("*.whl"), key=lambda path: path.stat().st_mtime)
with zipfile.ZipFile(wheel) as archive:
    for name in (
        "shiny-charts.js",
        "shiny-charts.css",
        "ECHARTS-LICENSE.txt",
        "ECHARTS-NOTICE.txt",
        "ZRENDER-LICENSE.txt",
        "shiny-charts.js.LEGAL.txt",
    ):
        assert archive.getinfo("shiny_charts/www/" + name).file_size > 0
    assert "shiny_charts/_proxy.py" in archive.namelist()
    assert "shiny_charts/py.typed" in archive.namelist()
with tempfile.TemporaryDirectory(prefix="shiny-charts-wheel-") as tmp:
    tmp = Path(tmp)
    env_dir = tmp / "venv"
    python = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(["uv", "venv", str(env_dir), "--python", sys.executable], check=True)
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel), "playwright"], check=True
    )
    # The isolated environment can resolve a newer Playwright than uv.lock.
    # Install its matching browser instead of relying on the developer's cache.
    subprocess.run([str(python), "-m", "playwright", "install", "chromium"], check=True)
    # Copy the native example to prove it runs with the wheel's runtime deps.
    shutil.copytree(
        root / "examples", tmp / "examples", ignore=shutil.ignore_patterns("__pycache__", "app.py")
    )
    shutil.copy(root / "scripts/wheel_smoke.py", tmp / "wheel_smoke.py")
    subprocess.run([str(python), str(tmp / "wheel_smoke.py")], cwd=tmp, check=True)
    # SDK is example-only: first prove minimal chart runtime, then the adoption.
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), "shinyhub-bookmarks==0.5.2"], check=True
    )
    shutil.copy(root / "scripts/portfolio_wheel_smoke.py", tmp / "portfolio_wheel_smoke.py")
    subprocess.run([str(python), str(tmp / "portfolio_wheel_smoke.py")], cwd=tmp, check=True)
print(
    "Wheel runtime, adoption APIs, FinOps/operations proxies, and optional Portfolio "
    "adoption passed without Plotly."
)
