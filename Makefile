.PHONY: sync lint build-browser test test-unit test-browser browsers build check check-wheel check-floor demo native operations gallery profile profile-updates

sync:
	uv sync --locked
	npm ci

lint:
	uv run ruff check src examples tests bench scripts

build-browser:
	npm run build

test-unit:
	npm test
	uv run pytest -q tests/test_chart.py

test-browser:
	uv run pytest -q tests/test_browser.py

test:
	npm test
	uv run pytest -q

browsers:
	uv run playwright install chromium $(PLAYWRIGHT_ARGS)

build:
	uv build

check: lint build-browser test build

check-wheel: build
	uv run python scripts/check_wheel.py

check-floor:
	uv run python scripts/check_floor.py --python 3.10

demo:
	uv run uvicorn examples.app:app --host 127.0.0.1 --port 8055

native:
	uv run uvicorn examples.finops_app:app --host 127.0.0.1 --port 8056

profile:
	uv run python bench/profile_large.py

operations:
	uv run uvicorn examples.operations_app:app --host 127.0.0.1 --port 8057

gallery:
	uv run uvicorn examples.gallery_app:app --host 127.0.0.1 --port 8060

profile-updates:
	uv run python bench/updates.py

portfolio:
	uv run uvicorn examples.portfolio_app:app --host 127.0.0.1 --port 8058

profile-dashboard:
	uv run python bench/dashboard.py
