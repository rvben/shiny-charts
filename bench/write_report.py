"""Generate a local decision report from measured results, never guessed figures."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
result = json.loads((ROOT / "bench/results.json").read_text())
summary = result["summary"]
native, plotly = summary["charts"], summary["plotly"]

source = (ROOT / "examples/finops.py").read_text()
tree = ast.parse(source)
chart_lines = {"render_chart": 0, "render_plotly": 0}
for node in ast.walk(tree):
    if not isinstance(node, ast.FunctionDef):
        continue
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id in chart_lines:
            chart_lines[target.id] += sum(
                bool(line.strip())
                for line in source.splitlines()[decorator.lineno - 1 : node.end_lineno]
            )


def kb(value):
    return f"{value / 1000:,.1f} kB"


bundles = result["bundle_bytes"]
lines = [
    "# Alpha decision report",
    "",
    "The alpha demonstrates a focused alternative for everyday Shiny dashboards. "
    "The strongest measured gain is cold startup; the strongest product gain is automatic "
    "host-theme integration and a smaller semantic chart API. "
    f"This run measured warm updates at {native['warm']['update_ms_median']} ms "
    f"versus {plotly['warm']['update_ms_median']} ms for styled shiny-plotly. "
    "The initial prototype run was near parity; these timings are workload-specific. "
    "There is no websocket-size advantage.",
    "",
    "## Controlled comparison",
    "",
    "Both routes render the same 2,400 synthetic requests, four SVG charts, the same "
    "workload colors, stable request IDs, success metadata, histogram bins and intervals. "
    "Plotly has explicit dashboard templates, compact margins, proper hover formatting, "
    "transparent backgrounds and uirevision. Both routes use the same Shiny version and "
    "shared server-side aggregation. The prototype includes an HTML toolbar/data table; "
    "the baseline uses Plotly's built-in controls.",
    "",
    "| Metric (median) | shiny-charts | Styled shiny-plotly |",
    "| --- | ---: | ---: |",
    f"| Cold dashboard ready | {native['cold']['first_dashboard_ms_median']} ms | {plotly['cold']['first_dashboard_ms_median']} ms |",
    f"| Cold HTTP transfer | {kb(native['cold']['http_bytes_median'])} | {kb(plotly['cold']['http_bytes_median'])} |",
    f"| Initial websocket | {kb(native['cold']['websocket_bytes_median'])} | {kb(plotly['cold']['websocket_bytes_median'])} |",
    f"| Warm dashboard ready | {native['warm']['first_dashboard_ms_median']} ms | {plotly['warm']['first_dashboard_ms_median']} ms |",
    f"| Warm update round trip | {native['warm']['update_ms_median']} ms | {plotly['warm']['update_ms_median']} ms |",
    f"| Websocket per update | {kb(native['warm']['update_websocket_bytes_median'])} | {kb(plotly['warm']['update_websocket_bytes_median'])} |",
    f"| Browser bundle (raw) | {kb(bundles['charts']['raw'])} | {kb(bundles['plotly']['raw'])} |",
    f"| Browser bundle (same gzip algorithm) | {kb(bundles['charts']['gzip'])} | {kb(bundles['plotly']['gzip'])} |",
    "",
    f"{native['cold']['samples']} alternating cold/warm runs per engine; 8 reactive updates "
    "per visit. Headless Chromium, 1440 × 1000, no CPU/network throttling, "
    f"{result['platform']}, Python {result['python']}, Chromium {result['chromium']}. "
    "Timing ends after all four chart renders and an animation frame. Update timing "
    "includes Playwright click overhead. HTTP bytes include headers; websocket bytes are "
    "received UTF-8 payloads. Fonts and shared UI assets contribute to HTTP totals. "
    "The dashboard serves gzip; shiny-plotly also serves its own precompressed bundle. "
    "Warm revisits reuse the same browser context; cold runs use a new context. "
    "These figures describe this workload and machine, not all chart types or platforms.",
    "",
    f"Versions: {result['versions']}. Measured {result['date']}.",
    "",
    "## Practical reasons to switch",
    "",
    "- Charts inherit the host's font, surfaces, foreground, grid and palette tokens. "
    "Changes to ancestor themes/classes/styles update the browser without rebuilding figures on the server.",
    "- A band, currency formatting and a budget annotation are semantic operations. "
    "The user doesn't construct helper traces or repeat low-level layout settings.",
    "- Stable workload colors and record IDs survive filtering. The default view revision "
    "keeps zoom and legend choices; changing it explicitly resets them.",
    "- CSV, SVG/PNG export and a keyboard-selectable data-table preview are included. "
    "Bins expose their actual range/count and edge convention.",
    "- A modular bundle covers the implemented dashboard chart families without loading "
    "the full Plotly feature set. A custom Plotly partial bundle could narrow this advantage.",
    "",
    f"The four chart render functions occupy {chart_lines['render_chart']} nonblank lines "
    f"for the prototype and {chart_lines['render_plotly']} for Plotly under the same Python "
    "formatter. This excludes shared data and UI, and excludes Plotly's additional "
    "theme/layout helpers. It is an example-specific maintenance comparison, not a "
    "general productivity statistic.",
    "",
    "## Limits of the switching case",
    "",
    "Keep shiny-plotly for existing Plotly figures or specialized features. This is not "
    "a compatible Plotly renderer and there is no automatic figure conversion. The "
    "prototype lacks 3D, maps, facets, arbitrary mixed-axis layers, lasso selection, "
    "server-side resampling and incremental trace updates. Full reactive updates are "
    "used. Canvas is supported, but this benchmark uses SVG for both engines. "
    "Accessibility includes descriptions, keyboard controls and a table preview; "
    "it is not a claim of complete accessible chart exploration. R and Shinylive "
    "bindings have not been validated.",
    "",
    "## Reproduce",
    "",
    "```sh",
    "uv sync",
    "npm ci",
    "npm run build",
    "uv run python -m uvicorn examples.app:app --host 127.0.0.1 --port 8055",
    "# In another terminal:",
    "uv run python bench/run.py --rounds 5",
    "uv run python bench/write_report.py",
    "```",
    "",
    "`bench/results.json` contains every sample, engine asset transfer, library version "
    "and summary. Both it and this report are local working artifacts.",
    "",
]
(ROOT / "bench/report.md").write_text("\n".join(lines))
print(ROOT / "bench/report.md")
