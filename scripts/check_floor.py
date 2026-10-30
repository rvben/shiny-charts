"""Run the complete suite at the declared minimum runtime dependencies."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--python", default=sys.executable)
parser.add_argument("--install-browser", action="store_true")
args = parser.parse_args()
root = Path(__file__).parents[1]
env_dir = root / ".venv-floor"
python = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(*command):
    subprocess.run(command, cwd=root, check=True)


run("uv", "venv", str(env_dir), "--python", args.python)
run(
    "uv",
    "pip",
    "install",
    "--python",
    str(python),
    "-e",
    str(root),
    "shiny==1.5.0",
    "htmltools==0.6.0",
    "--group",
    str(root / "pyproject.toml") + ":dev",
)
if args.install_browser:
    run(str(python), "-m", "playwright", "install", "--with-deps", "chromium")
run(str(python), "-m", "pytest", "-q")
