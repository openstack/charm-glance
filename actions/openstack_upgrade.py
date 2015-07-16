#!/usr/bin/python
import sys

sys.path.append('hooks/')

from charmhelpers.core.hookenv import config
from glance_relations import config_changed

from charmhelpers.contrib.openstack.utils import (
    openstack_upgrade_available,
    juju_log
)

from glance_utils import (
    do_openstack_upgrade,
    register_configs
)


CONFIGS = register_configs()

def openstack_upgrade():
    if config('action_managed_upgrade'):
      juju_log('Upgrading OpenStack release')
      do_openstack_upgrade(CONFIGS)
      config_changed()
    else:
      juju_log('action_managed_upgrade set to false, OpenStack upgrade aborted.')

if __name__ == '__main__':
    openstack_upgrade()
