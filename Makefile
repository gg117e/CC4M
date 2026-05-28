# CC4M command shortcuts.
#
# Main entry points:
#   make web          # Visualization only, using existing dest/ artifacts.
#   make docker-web   # Clone detection + visualization with Docker.
#   make start        # Backward-compatible alias for docker-web.

PYTHON ?= python3.12

.PHONY: help start web docker-web build build-web analyze clean stop test lint

help:
	@echo "CC4M - command list"
	@echo ""
	@echo "Main entry points:"
	@echo "  make web          Visualization only (local Python, http://localhost:8000/visualize/)"
	@echo "  make docker-web   Clone detection + visualization (Docker, http://localhost:8000)"
	@echo "  make start        Alias for make docker-web"
	@echo ""
	@echo "Development / advanced:"
	@echo "  make build        Build all Docker images"
	@echo "  make build-web    Build the web-ui Docker image"
	@echo "  make analyze PROJECT=owner.repo"
	@echo "                    Run batch analysis in Docker"
	@echo "  make test         Run tests"
	@echo "  make lint         Run ruff"
	@echo "  make stop         Stop Docker containers"
	@echo "  make clean        Remove Docker containers, volumes, and local images"
	@echo ""
	@echo "PowerShell users can use Docker directly:"
	@echo "  docker compose up --build web-ui"

.venv:
	@command -v $(PYTHON) >/dev/null 2>&1 || { \
		echo "ERROR: $(PYTHON) was not found."; \
		echo "Install Python 3.12.x first, then rerun make web."; \
		exit 1; \
	}
	@$(PYTHON) -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else f'ERROR: Python 3.12.x is required, got {sys.version.split()[0]}')"
	@$(PYTHON) -c "import ensurepip" 2>/dev/null || { \
		echo "ERROR: $(PYTHON) ensurepip is not available."; \
		echo "On Debian/Ubuntu, run: sudo apt-get install -y python3.12-venv"; \
		exit 1; \
	}
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -U pip setuptools wheel
	.venv/bin/pip install -r requirements-web.txt

web: .venv
	.venv/bin/python main.py web-ui --host 127.0.0.1 --port 8000 --visualize-only

test: .venv
	.venv/bin/python -m pip install -q -r requirements-dev.txt
	.venv/bin/python -m pytest tests/ -q

lint: .venv
	.venv/bin/python -m pip install -q -r requirements-dev.txt
	.venv/bin/python -m ruff check src/

start: docker-web

docker-web:
	docker compose up --build web-ui

build:
	docker compose build

build-web:
	docker compose build web-ui

analyze:
ifndef PROJECT
	$(error PROJECT is not set. Usage: make analyze PROJECT=owner.repo)
endif
	docker compose run --rm analysis analyze --project $(PROJECT)

stop:
	docker compose down

clean:
	docker compose down -v --rmi local
