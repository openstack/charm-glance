# Copyright 2016 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys

from mock import patch, MagicMock

os.environ['JUJU_UNIT_NAME'] = 'glance'

# python-apt is not installed as part of test-requirements but is imported by
# some charmhelpers modules so create a fake import.
mock_apt = MagicMock()
sys.modules['apt'] = mock_apt
mock_apt.apt_pkg = MagicMock()

with patch('actions.hooks.glance_utils.register_configs'):
    with patch('hooks.glance_utils.register_configs'):
            from actions import openstack_upgrade

from test_utils import CharmTestCase

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
