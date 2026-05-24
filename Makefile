.PHONY: gate backend-gate frontend-gate install

# Full lint / type / test gate across both packages. Runs the backend half
# then the frontend half; make stops at the first target that exits non-zero.
gate: backend-gate frontend-gate

# Backend gate. Assumes the project's tools are on PATH — i.e. an activated
# Python venv locally (see backend/README.md), or the CI runner's
# setup-python environment after `make install`.
backend-gate:
	cd backend && ruff check . && mypy src && pytest

# Frontend gate. `npm run build` is included because it surfaces type/config
# issues that lint misses.
frontend-gate:
	cd frontend && npm run typecheck && npm run lint && npm run build

# Install both halves' dependencies. Run inside an activated Python venv
# locally; CI installs into the runner's setup-python environment.
install:
	cd backend && pip install -e ".[dev]"
	cd frontend && npm install
