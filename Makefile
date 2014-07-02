#!/usr/bin/make
PYTHON := /usr/bin/env python

lint:
	@flake8 --exclude hooks/charmhelpers hooks unit_tests
	@charm proof

test:
	@$(PYTHON) /usr/bin/nosetests --nologcapture --with-coverage unit_tests

bin/charm_helpers_sync.py:
	@mkdir -p bin
	@bzr cat lp:charm-helpers/tools/charm_helpers_sync/charm_helpers_sync.py \
        > bin/charm_helpers_sync.py

sync: bin/charm_helpers_sync.py
	@$(PYTHON) bin/charm_helpers_sync.py -c charm-helpers.yaml

publish: lint test
	bzr push lp:charms/glance
	bzr push lp:charms/trusty/glance
