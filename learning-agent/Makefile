# ============================================================
#  Makefile — LearnPath Agent dev commands
#  Usage: make <target>
# ============================================================

.PHONY: help install setup run test-mcp lint clean

VENV     = venv
PYTHON   = $(VENV)/bin/python
PIP      = $(VENV)/bin/pip

# ── Default target ───────────────────────────────────────────
help:
	@echo ""
	@echo "  LearnPath Agent — available commands"
	@echo ""
	@echo "  make install     Create virtualenv + install dependencies"
	@echo "  make setup       Copy .env.example → .env (edit before running)"
	@echo "  make run         Launch ADK default web UI on localhost:8000"
	@echo "  make test-mcp    Run the MCP server directly (smoke test)"
	@echo "  make lint        Run ruff linter"
	@echo "  make clean       Remove __pycache__ and .pyc files"
	@echo ""

# ── Install ──────────────────────────────────────────────────
install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "✅  Virtualenv ready. Activate with: source venv/bin/activate"

# ── First-time setup ─────────────────────────────────────────
setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "✅  .env created. Open it and fill in your API keys."; \
	else \
		echo "⚠️   .env already exists — skipping."; \
	fi

# ── Run with ADK default web UI ──────────────────────────────
run:
	@if [ ! -f .env ]; then echo "❌  Run 'make setup' first."; exit 1; fi
	@set -a; source .env; set +a; \
	$(VENV)/bin/adk web agent --port 8000

# ── Test MCP server in isolation ─────────────────────────────
test-mcp:
	@set -a; source .env; set +a; \
	$(PYTHON) -c "\
import asyncio, json, sys; \
sys.path.insert(0, '.'); \
from mcp_server.youtube_mcp_server import _search_learning_resources, _score_resource_relevance; \
result = asyncio.run(_search_learning_resources( \
    goal='learn Python for data science', \
    topic='pandas dataframes', \
    level='beginner', \
    max_results=3 \
)); \
print(json.dumps(result, indent=2))"

# ── Lint ─────────────────────────────────────────────────────
lint:
	$(VENV)/bin/ruff check . --fix

# ── Clean ────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -name "*.pyc" -delete; \
	echo "✅  Cleaned."
