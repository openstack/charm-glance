#!/usr/bin/make

lint:
	@flake8 --exclude hooks/charmhelpers hooks
	@charm proof

sync:
	@charm-helper-sync -c charm-helpers-sync.yaml
