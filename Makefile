.PHONY: all setup test venv

all: setup

test: setup
	. .venv/bin/activate && pytest
	python3 -m unittest contrib/redactr_poc.py

setup: venv

venv: .venv
	@echo "To activate the venv manually:"
	@echo ". .venv/bin/activate"
	@echo

.venv:
	python3 -m venv .venv
	. .venv/bin/activate && \
	  sed -i -e "s/PS1='(.venv)/PS1='(nbtools-dev)/" .venv/bin/activate && \
	  pip install -e '.[dev]'
