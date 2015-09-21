from mock import patch
import os

os.environ['JUJU_UNIT_NAME'] = 'glance'

with patch('charmhelpers.core.hookenv.config') as config:
    with patch('actions.hooks.glance_utils.register_configs'):
        from actions import git_reinstall

from test_utils import (
    CharmTestCase
)

TO_PATCH = [
    'config',
    'git_install_requested',
]


openstack_origin_git = \
    """repositories:
         - {name: requirements,
            repository: 'git://git.openstack.org/openstack/requirements',
            branch: stable/juno}
         - {name: glance,
            repository: 'git://git.openstack.org/openstack/glance',
            branch: stable/juno}"""


class TestGlanceActions(CharmTestCase):

    def setUp(self):
        super(TestGlanceActions, self).setUp(git_reinstall, TO_PATCH)
        self.config.side_effect = self.test_config.get
        self.git_install_requested.return_value = True

    @patch.object(git_reinstall, 'action_set')
    @patch.object(git_reinstall, 'action_fail')
    @patch.object(git_reinstall, 'git_install')
    @patch.object(git_reinstall, 'config_changed')
    def test_git_reinstall(self, config_changed, git_install, action_fail,
                           action_set):
        config.return_value = openstack_origin_git
        self.test_config.set('openstack-origin-git', openstack_origin_git)

        git_reinstall.git_reinstall()

        git_install.assert_called_with(openstack_origin_git)
        self.assertTrue(git_install.called)
        self.assertTrue(config_changed.called)
        self.assertFalse(action_set.called)
        self.assertFalse(action_fail.called)

    @patch.object(git_reinstall, 'action_set')
    @patch.object(git_reinstall, 'action_fail')
    @patch.object(git_reinstall, 'git_install')
    @patch.object(git_reinstall, 'config_changed')
    def test_git_reinstall_not_configured(self, config_changed, git_install,
                                          action_fail, action_set):
        config.return_value = None
        self.git_install_requested.return_value = False

        git_reinstall.git_reinstall()

        msg = 'openstack-origin-git is not configured'
        action_fail.assert_called_with(msg)
        self.assertFalse(git_install.called)
        self.assertFalse(action_set.called)

    @patch.object(git_reinstall, 'action_set')
    @patch.object(git_reinstall, 'action_fail')
    @patch.object(git_reinstall, 'git_install')
    @patch.object(git_reinstall, 'config_changed')
    @patch('traceback.format_exc')
    def test_git_reinstall_exception(self, format_exc, config_changed,
                                     git_install, action_fail, action_set):
        config.return_value = openstack_origin_git
        e = OSError('something bad happened')
        git_install.side_effect = e
        traceback = (
            "Traceback (most recent call last):\n"
            "  File \"actions/git_reinstall.py\", line 37, in git_reinstall\n"
            "    git_install(config(\'openstack-origin-git\'))\n"
            "  File \"/usr/lib/python2.7/dist-packages/mock.py\", line 964, in __call__\n"  # noqa
            "    return _mock_self._mock_call(*args, **kwargs)\n"
            "  File \"/usr/lib/python2.7/dist-packages/mock.py\", line 1019, in _mock_call\n"  # noqa
            "    raise effect\n"
            "OSError: something bad happened\n")
        format_exc.return_value = traceback

        git_reinstall.git_reinstall()

        msg = 'git-reinstall resulted in an unexpected error'
        action_fail.assert_called_with(msg)
        action_set.assert_called_with({'traceback': traceback})
