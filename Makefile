#!/usr/bin/make

lint:
	@flake8 --exclude hooks/charmhelpers hooks
	@flake8 unit_tests
	@charm proof

sync:
	@charm-helper-sync -c charm-helpers.yaml

test:
	@$(PYTHON) /usr/bin/nosetests --nologcapture --with-coverage  unit_tests
