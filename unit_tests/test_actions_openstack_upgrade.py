from mock import patch
import os

os.environ['JUJU_UNIT_NAME'] = 'glance'

with patch('actions.hooks.glance_utils.register_configs'):
    with patch('hooks.glance_utils.register_configs'):
            from actions import openstack_upgrade

from test_utils import (
    CharmTestCase
)

TO_PATCH = [
    'config_changed',
    'do_openstack_upgrade'
]


class TestGlanceUpgradeActions(CharmTestCase):

    def setUp(self):
        super(TestGlanceUpgradeActions, self).setUp(openstack_upgrade,
                                                    TO_PATCH)

    @patch('actions.charmhelpers.contrib.openstack.utils.config')
    @patch('actions.charmhelpers.contrib.openstack.utils.action_set')
    @patch('actions.charmhelpers.contrib.openstack.utils.git_install_requested')  # noqa
    @patch('actions.charmhelpers.contrib.openstack.utils.openstack_upgrade_available')  # noqa
    @patch('actions.charmhelpers.contrib.openstack.utils.juju_log')
    @patch('subprocess.check_output')
    def test_openstack_upgrade_true(self, _check_output, log, upgrade_avail,
                                    git_requested, action_set, config):
        _check_output.return_value = 'null'
        git_requested.return_value = False
        upgrade_avail.return_value = True
        config.return_value = True

        openstack_upgrade.openstack_upgrade()

        self.assertTrue(self.do_openstack_upgrade.called)
        self.assertTrue(self.config_changed.called)

    @patch('actions.charmhelpers.contrib.openstack.utils.config')
    @patch('actions.charmhelpers.contrib.openstack.utils.action_set')
    @patch('actions.charmhelpers.contrib.openstack.utils.git_install_requested')  # noqa
    @patch('actions.charmhelpers.contrib.openstack.utils.openstack_upgrade_available')  # noqa
    @patch('actions.charmhelpers.contrib.openstack.utils.juju_log')
    @patch('subprocess.check_output')
    def test_openstack_upgrade_false(self, _check_output, log, upgrade_avail,
                                     git_requested, action_set, config):
        _check_output.return_value = 'null'
        git_requested.return_value = False
        upgrade_avail.return_value = True
        config.return_value = False

        openstack_upgrade.openstack_upgrade()

        self.assertFalse(self.do_openstack_upgrade.called)
        self.assertFalse(self.config_changed.called)
