#!/usr/bin/make

lint:
	@echo "Running flake8 tests: "
	@flake8 --exclude hooks/charmhelpers hooks unit_tests tests
	@echo "OK"
	@echo "Running charm proof: "
	@charm proof
	@echo "OK"

sync:
	@charm-helper-sync -c charm-helpers-hooks.yaml
	@charm-helper-sync -c charm-helpers-tests.yaml

unit_test:
	@$(PYTHON) /usr/bin/nosetests --nologcapture --with-coverage  unit_tests

test:
	@echo Starting Amulet tests...
	# /!\ Note: The -v should only be temporary until Amulet sends
	# raise_status() messages to stderr:
	#   https://bugs.launchpad.net/amulet/+bug/1320357
	@juju test -v -p AMULET_HTTP_PROXY

publish: lint unit_test
	bzr push lp:charms/glance
	bzr push lp:charms/trusty/glance

all: unit_test lint
