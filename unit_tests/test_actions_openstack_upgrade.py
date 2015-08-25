from mock import patch
import os

os.environ['JUJU_UNIT_NAME'] = 'glance'

with patch('hooks.glance_utils.register_configs') as register_configs:
    register_configs.return_value = None
    import openstack_upgrade

from test_utils import (
    CharmTestCase
)

TO_PATCH = [
    'config'
]


class TestGlanceUpgradeActions(CharmTestCase):

    def setUp(self):
        super(TestGlanceUpgradeActions, self).setUp(openstack_upgrade,
                                                    TO_PATCH)
        self.config.side_effect = self.test_config.get

    @patch.object(openstack_upgrade, 'action_set')
    @patch.object(openstack_upgrade, 'action_fail')
    @patch.object(openstack_upgrade, 'do_openstack_upgrade')
    @patch.object(openstack_upgrade, 'openstack_upgrade_available')
    @patch.object(openstack_upgrade, 'config_changed')
    @patch('charmhelpers.contrib.openstack.utils.config')
    def test_openstack_upgrade(self, _config, config_changed,
                               openstack_upgrade_available,
                               do_openstack_upgrade, action_fail,
                               action_set):
        _config.return_value = None
        openstack_upgrade_available.return_value = True

        self.test_config.set('action-managed-upgrade', True)

        openstack_upgrade.openstack_upgrade()

        self.assertTrue(do_openstack_upgrade.called)
        self.assertTrue(config_changed.called)
        self.assertFalse(action_fail.called)

    @patch.object(openstack_upgrade, 'action_set')
    @patch.object(openstack_upgrade, 'do_openstack_upgrade')
    @patch.object(openstack_upgrade, 'openstack_upgrade_available')
    @patch.object(openstack_upgrade, 'config_changed')
    @patch('charmhelpers.contrib.openstack.utils.config')
    def test_openstack_upgrade_not_configured(self, _config, config_changed,
                                              openstack_upgrade_available,
                                              do_openstack_upgrade,
                                              action_set):
        _config.return_value = None
        openstack_upgrade_available.return_value = True

        openstack_upgrade.openstack_upgrade()

        msg = ('action-managed-upgrade config is False, skipped upgrade.')

        action_set.assert_called_with({'outcome': msg})
        self.assertFalse(do_openstack_upgrade.called)

    @patch.object(openstack_upgrade, 'action_set')
    @patch.object(openstack_upgrade, 'do_openstack_upgrade')
    @patch.object(openstack_upgrade, 'openstack_upgrade_available')
    @patch.object(openstack_upgrade, 'config_changed')
    @patch('charmhelpers.contrib.openstack.utils.config')
    def test_openstack_upgrade_git_install(self, _config, config_changed,
                                           openstack_upgrade_available,
                                           do_openstack_upgrade,
                                           action_set):

        self.test_config.set('action-managed-upgrade', True)
        self.test_config.set('openstack-origin-git', True)

        openstack_upgrade.openstack_upgrade()

        msg = ('installed from source, skipped upgrade.')
        action_set.assert_called_with({'outcome': msg})
        self.assertFalse(do_openstack_upgrade.called)

    @patch.object(openstack_upgrade, 'action_set')
    @patch.object(openstack_upgrade, 'action_fail')
    @patch.object(openstack_upgrade, 'do_openstack_upgrade')
    @patch.object(openstack_upgrade, 'openstack_upgrade_available')
    @patch.object(openstack_upgrade, 'config_changed')
    @patch('traceback.format_exc')
    @patch('charmhelpers.contrib.openstack.utils.config')
    def test_openstack_upgrade_exception(self, _config, format_exc,
                                         config_changed,
                                         openstack_upgrade_available,
                                         do_openstack_upgrade,
                                         action_fail, action_set):
        _config.return_value = None
        self.test_config.set('action-managed-upgrade', True)
        openstack_upgrade_available.return_value = True

        e = OSError('something bad happened')
        do_openstack_upgrade.side_effect = e
        traceback = (
            "Traceback (most recent call last):\n"
            "  File \"actions/openstack_upgrade.py\", line 37, in openstack_upgrade\n"  # noqa
            "    openstack_upgrade(config(\'openstack-origin-git\'))\n"
            "  File \"/usr/lib/python2.7/dist-packages/mock.py\", line 964, in __call__\n"  # noqa
            "    return _mock_self._mock_call(*args, **kwargs)\n"
            "  File \"/usr/lib/python2.7/dist-packages/mock.py\", line 1019, in _mock_call\n"  # noqa
            "    raise effect\n"
            "OSError: something bad happened\n")
        format_exc.return_value = traceback

        openstack_upgrade.openstack_upgrade()

        msg = 'do_openstack_upgrade resulted in an unexpected error'
        action_fail.assert_called_with(msg)
        action_set.assert_called_with({'traceback': traceback})
