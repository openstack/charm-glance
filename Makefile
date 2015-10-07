#!/usr/bin/make
PYTHON := /usr/bin/env python

lint:
	@flake8 --exclude hooks/charmhelpers,tests/charmhelpers \
        actions hooks unit_tests tests
	@charm proof

test:
	@# Bundletester expects unit tests here.
	@$(PYTHON) /usr/bin/nosetests -v --nologcapture --with-coverage unit_tests

functional_test:
	@echo Starting Amulet tests...
	@juju test -v -p AMULET_HTTP_PROXY,AMULET_OS_VIP --timeout 2700

bin/charm_helpers_sync.py:
	@mkdir -p bin
	@bzr cat lp:charm-helpers/tools/charm_helpers_sync/charm_helpers_sync.py \
        > bin/charm_helpers_sync.py

sync: bin/charm_helpers_sync.py
	@$(PYTHON) bin/charm_helpers_sync.py -c charm-helpers-hooks.yaml
	@$(PYTHON) bin/charm_helpers_sync.py -c charm-helpers-tests.yaml

publish: lint test
	bzr push lp:charms/glance
	bzr push lp:charms/trusty/glance

all: test lint
