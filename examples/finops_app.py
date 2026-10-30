"""Native FinOps app: uv run uvicorn examples.finops_app:app --port 8056."""

from examples.finops import make_app

app = make_app(comparison=False)
