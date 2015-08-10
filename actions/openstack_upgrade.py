#!/usr/bin/python
import sys
import traceback

sys.path.append('hooks/')

from charmhelpers.core.hookenv import (
    action_set,
    action_fail,
    config
)

from glance_relations import config_changed

from charmhelpers.contrib.openstack.utils import (
    juju_log,
    git_install_requested,
    openstack_upgrade_available
)

from glance_utils import (
    do_openstack_upgrade,
    register_configs
)


CONFIGS = register_configs()


def openstack_upgrade():
    """Upgrade packages to config-set Openstack version.

    If the charm was installed from source we cannot upgrade it.
    For backwards compatibility a config flag must be set for this
    code to run, otherwise a full service level upgrade will fire
    on config-changed."""

    if git_install_requested():
        action_set({'outcome': 'installed from source, skipped upgrade.'})
    else:
        if openstack_upgrade_available('glance-common'):
            if config('action-managed-upgrade'):
                juju_log('Upgrading OpenStack release')

                try:
                    do_openstack_upgrade(CONFIGS)
                    action_set({'outcome': 'success, upgrade completed.'})
                except:
                    action_set({'outcome': 'upgrade failed, see traceback.'})
                    action_set({'traceback': traceback.format_exc()})
                    action_fail('do_openstack_upgrade resulted in an '
                                'unexpected error')

                config_changed()
            else:
                action_set({'outcome': 'invalid config, skipped upgrade.'})
        else:
            action_set({'outcome': 'no upgrade available.'})

if __name__ == '__main__':
    openstack_upgrade()
