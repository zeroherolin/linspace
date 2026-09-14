PYTHON ?= python3

.PHONY: help check build
help:
	@echo './linspace configure   Save the site profile to local/site.json'
	@echo 'sudo ./linspace deploy Build, deploy and verify the configured site'
	@echo './linspace verify      Check public HTTPS without changing channel data'
	@echo './linspace build       Write release bundles to dist/'
	@echo 'make check             Run offline checks and tests'

build:
	@$(PYTHON) scripts/cli.py build

check:
	@$(PYTHON) scripts/check.py
