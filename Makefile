.PHONY: dev venv test lint screenshots build dist clean

VENV ?= .venv
PY := $(VENV)/bin/python

venv:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --quiet --upgrade pip
	$(VENV)/bin/pip install --quiet -e ".[dev]"

dev: venv ## install dev environment
	@echo "run:  source $(VENV)/bin/activate && rdpstudio"

test: venv ## run the test suite (incl. live sshd integration)
	QT_QPA_PLATFORM=offscreen $(PY) -m pytest

lint: venv
	$(VENV)/bin/ruff check src tests scripts

format: venv
	$(VENV)/bin/ruff check --fix src tests scripts

screenshots: venv ## offscreen GUI captures into docs/screenshots
	QT_QPA_PLATFORM=offscreen $(PY) scripts/dev_screenshots.py docs/screenshots

build: venv ## PyInstaller onedir build
	$(VENV)/bin/pip install --quiet pyinstaller
	$(VENV)/bin/pyinstaller packaging/rdpstudio.spec

dist: build
	@echo "artifacts in dist/KB-Remote"

clean:
	rm -rf build dist *.spec.bak .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

help:
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
