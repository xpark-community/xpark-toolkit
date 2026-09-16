# Makefile for xpark-toolkit
#
# Common developer commands. Run `make help` to see all targets.
# Tools are invoked via the `$(PYTHON)` shim so a virtualenv is preferred:
#   python -m venv .venv && source .venv/bin/activate && pip install ruff mypy pytest
#
# Override the interpreter / dirs from the command line, e.g.:
#   make lint PYTHON=python3.11
#   make format PY_DIRS=provisioning

PYTHON ?= python3
PY_DIRS := provisioning diagnostics maintenance
PY_FILES := $(shell find $(PY_DIRS) -name '*.py' -type f 2>/dev/null)

# Tools — resolved on first use so the Makefile works even if some are absent.
RUFF := $(shell command -v ruff 2>/dev/null)
MYPY := $(shell command -v mypy 2>/dev/null)
PYTEST := $(shell command -v pytest 2>/dev/null)

.PHONY: help install install-dev format format-check lint type test check clean

# Default target ---------------------------------------------------------------

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Install ----------------------------------------------------------------------

install: ## Install runtime dependencies (provisioning tools)
	$(PYTHON) -m pip install -U "modelscope" "huggingface_hub" "cos-python-sdk-v5"

install-dev: ## Install developer dependencies (ruff, mypy, pytest)
	$(PYTHON) -m pip install -U "ruff" "mypy" "pytest"

# Formatting -------------------------------------------------------------------

format: ## Format code in place (ruff)
	@if [ -z "$(RUFF)" ]; then echo "ruff not installed; run: make install-dev"; exit 1; fi
	$(RUFF) format $(PY_DIRS)
	$(RUFF) check --fix $(PY_DIRS)

format-check: ## Check formatting without writing (CI-friendly)
	@if [ -z "$(RUFF)" ]; then echo "ruff not installed; run: make install-dev"; exit 1; fi
	$(RUFF) format --check $(PY_DIRS)
	$(RUFF) check $(PY_DIRS)

# Linting & types --------------------------------------------------------------

lint: ## Lint with ruff
	@if [ -z "$(RUFF)" ]; then echo "ruff not installed; run: make install-dev"; exit 1; fi
	$(RUFF) check $(PY_DIRS)

type: ## Type-check with mypy
	@if [ -z "$(MYPY)" ]; then echo "mypy not installed; run: make install-dev"; exit 1; fi
	$(MYPY) $(PY_FILES)

# Tests ------------------------------------------------------------------------

test: ## Run the test suite with pytest
	@if [ -z "$(PYTEST)" ]; then echo "pytest not installed; run: make install-dev"; exit 1; fi
	$(PYTEST) $(PY_DIRS)

# Aggregate --------------------------------------------------------------------

check: lint type test ## Run lint + type + test

# Cleanup ----------------------------------------------------------------------

clean: ## Remove Python build/test artifacts
	find $(PY_DIRS) -type d -name '__pycache__' -prune -exec rm -rf {} +
	find $(PY_DIRS) -type d -name '.pytest_cache' -prune -exec rm -rf {} +
	find $(PY_DIRS) -type d -name '.mypy_cache' -prune -exec rm -rf {} +
	find $(PY_DIRS) -type d -name '.ruff_cache' -prune -exec rm -rf {} +
