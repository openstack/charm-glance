#!/usr/bin/python
import sys

sys.path.append('hooks/')

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
    if openstack_upgrade_available('glance-common'):
        juju_log('Upgrading OpenStack release')
        do_openstack_upgrade(CONFIGS)


if __name__ == '__main__':
    openstack_upgrade()