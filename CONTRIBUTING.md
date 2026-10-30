# Development

The project is a standalone package with a stable documented API. Node is needed to build the browser
adapter, not to use the installed Python wheel.

```sh
make sync
make browsers
make check
make check-wheel
make check-floor
```

`make check` runs Ruff, the frontend build, JavaScript/unit/browser tests, and
wheel/sdist builds. `make check-wheel` installs the wheel and a copied native
FinOps example in a temporary environment without either Plotly package and
runs real browser checks. `make check-floor` uses Python 3.10, Shiny 1.5.0, and
htmltools 0.6.0 in a separate `.venv-floor`.

Select another installed Playwright engine with `SHINY_CHARTS_BROWSER=firefox`
or `webkit` before `make test-browser`. Install it with
`uv run playwright install firefox webkit`. CI uses these same tests and has a
single `All checks passed` status for branch protection. Remote CI runs require
the project to be pushed; nothing in this local workflow publishes packages.

The checked-in `src/shiny_charts/www` bundle must match `npm run build`. CI checks
its diff. ECharts/zrender notices and linked legal comments travel with the wheel.
The frontend compiler owns engine-specific options; the Python API stays semantic.

Use Conventional Commits. Keep benchmark result/report files, DESIGN.md,
`.impeccable`, review captures, and generated design collateral out of commits.
Never publish, push, release, or send external messages without explicit approval.

See `docs/api-contract.md` before changing defaults or event fields. Add tests
for behavior that could regress, including empty/missing data, keys, modules,
view changes and lifecycle cleanup. Keep performance profiles separate from
functional tests; machine-dependent timings are not CI pass/fail thresholds.

`make operations` runs the second adoption app. `make profile-updates` compares
full/proxy rolling-window updates, including complete point paint and received
websocket bytes. Do not run browser tests concurrently with timing profiles.
`src/shiny_charts/_version.py` is the single version source; uv cache keys include
it so editable distribution metadata is refreshed when the version changes.

The default development environment also installs the `adoption` group for Portfolio
pulse. At the library dependency floor, those SDK-specific tests skip because its
optional SDK requires Shiny >=1.8. Run `tests/test_portfolio.py` with the default
environment. Include it in the Firefox/WebKit adoption checks. Generated benchmark
reports and design-review files remain local and must not be committed.
