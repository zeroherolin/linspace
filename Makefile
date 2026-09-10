PYTHON ?= python3

.PHONY: help check build
help:
	@echo './linspace configure   Set domain, homepage, and public files'
	@echo 'sudo ./linspace deploy Build, deploy, and verify the configured site'
	@echo './linspace verify      Check public HTTPS without modifying stash'
	@echo 'make check             Run offline development checks'

build:
	@$(PYTHON) scripts/cli.py build

check:
	@$(PYTHON) scripts/check.py
