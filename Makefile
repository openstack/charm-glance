#!/usr/bin/make

lint:
	@echo "Running flake8 tests: "
	@flake8 --exclude hooks/charmhelpers hooks unit_tests
	@echo "OK"
	@echo "Running charm proof: "
	@charm proof
	@echo "OK"

sync:
	@charm-helper-sync -c charm-helpers.yaml

test:
	@$(PYTHON) /usr/bin/nosetests --nologcapture --with-coverage  unit_tests

all: test lint
