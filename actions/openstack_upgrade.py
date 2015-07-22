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
    git_install_requested
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
        action_fail('Openstack upgrade failed to run due to charm being '
                    'installed from source.')
    else:
        if config('action_managed_upgrade'):
            juju_log('Upgrading OpenStack release')

            try:
                do_openstack_upgrade(CONFIGS)
            except:
                action_set({'traceback': traceback.format_exc()})
                action_fail('do_openstack_upgrade resulted in an '
                            'unexpected error')

            config_changed()
        else:
            action_fail('action_managed_upgrade set to false, OpenStack '
                        'upgrade aborted.')

if __name__ == '__main__':
    openstack_upgrade()
