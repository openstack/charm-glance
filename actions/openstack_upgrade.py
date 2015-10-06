#!/usr/bin/python

from charmhelpers.contrib.openstack.utils import (
    do_action_openstack_upgrade,
)

from hooks.glance_relations import (
    config_changed,
    CONFIGS
)

from hooks.glance_utils import do_openstack_upgrade


def openstack_upgrade():
    """Upgrade packages to config-set Openstack version.

    If the charm was installed from source we cannot upgrade it.
    For backwards compatibility a config flag must be set for this
    code to run, otherwise a full service level upgrade will fire
    on config-changed."""
    if (do_action_openstack_upgrade('glance-common',
                                    do_openstack_upgrade,
                                    CONFIGS)):
        config_changed()

if __name__ == '__main__':
    openstack_upgrade()
