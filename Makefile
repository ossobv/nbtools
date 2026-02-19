.PHONY: all setup venv

all: setup

test: setup
	. .venv/bin/activate && pytest -s

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
