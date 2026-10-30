"""Matched native/Plotly comparison: uv run uvicorn examples.app:app --port 8055."""

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.routing import Mount

from examples.finops import make_app

charts_app = make_app("charts")
plotly_app = make_app("plotly")
app = Starlette(
    routes=[Mount("/charts", charts_app), Mount("/plotly", plotly_app), Mount("/", charts_app)],
    middleware=[Middleware(GZipMiddleware)],
)
