.PHONY: all fmt test setup venv

all: setup

test: setup
	. .venv/bin/activate && pytest
	python3 -m unittest contrib/redactr_poc.py

fmt: setup
	. .venv/bin/activate && flake8
	! LC_ALL=C grep -rnP --exclude='*.pyc' --exclude='*.swp' '[^\x00-\x7F]' \
	  src tests contrib

setup: venv

venv: .venv
	@echo "To activate the venv manually:"
	@echo ". .venv/bin/activate"
	@echo

.venv:
	python3 -m venv .venv --prompt nbtools-dev
	. .venv/bin/activate && \
	  pip install -e '.[dev]'
