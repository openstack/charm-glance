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

from collections import OrderedDict
from mock import patch, call, MagicMock

os.environ['JUJU_UNIT_NAME'] = 'glance'
import hooks.glance_utils as utils

from test_utils import (
    CharmTestCase,
    SimpleKV,
)

TO_PATCH = [
    'config',
    'log',
    'relation_ids',
    'get_os_codename_install_source',
    'configure_installation_source',
    'is_elected_leader',
    'templating',
    'apt_update',
    'apt_upgrade',
    'apt_install',
    'git_pip_venv_dir',
    'git_src_dir',
    'mkdir',
    'os_release',
    'pip_install',
    'render',
    'service_restart',
    'service_start',
    'service_stop',
    'service_name',
    'install_alternative',
    'lsb_release',
    'os_application_version_set',
    'enable_memcache',
    'token_cache_pkgs',
]

DPKG_OPTS = [
    '--option', 'Dpkg::Options::=--force-confnew',
    '--option', 'Dpkg::Options::=--force-confdef',
]

openstack_origin_git = \
    """repositories:
         - {name: requirements,
            repository: 'git://git.openstack.org/openstack/requirements',
            branch: stable/juno}
         - {name: glance,
            repository: 'git://git.openstack.org/openstack/glance',
            branch: stable/juno}"""


class TestGlanceUtils(CharmTestCase):

    def setUp(self):
        super(TestGlanceUtils, self).setUp(utils, TO_PATCH)
        self.config.side_effect = self.test_config.get_all

    @patch('subprocess.check_call')
    def test_migrate_database(self, check_call):
        "It migrates database with cinder-manage"
        utils.migrate_database()
        check_call.assert_called_with(['glance-manage', 'db_sync'])

    @patch('os.path.exists')
    def test_register_configs_apache(self, exists):
        exists.return_value = False
        self.os_release.return_value = 'grizzly'
        self.relation_ids.return_value = False
        configs = utils.register_configs()
        calls = []
        for conf in [utils.GLANCE_REGISTRY_CONF,
                     utils.GLANCE_API_CONF,
                     utils.HAPROXY_CONF,
                     utils.HTTPS_APACHE_CONF]:
            calls.append(
                call(conf,
                     utils.CONFIG_FILES[conf]['hook_contexts'])
            )
        configs.register.assert_has_calls(calls, any_order=True)

    @patch('os.path.exists')
    def test_register_configs_apache24(self, exists):
        exists.return_value = True
        self.os_release.return_value = 'grizzly'
        self.relation_ids.return_value = False
        configs = utils.register_configs()
        calls = []
        for conf in [utils.GLANCE_REGISTRY_CONF,
                     utils.GLANCE_API_CONF,
                     utils.HAPROXY_CONF,
                     utils.HTTPS_APACHE_24_CONF]:
            calls.append(
                call(conf,
                     utils.CONFIG_FILES[conf]['hook_contexts'])
            )
        configs.register.assert_has_calls(calls, any_order=True)

    @patch('os.path.exists')
    def test_register_configs_ceph(self, exists):
        exists.return_value = True
        self.os_release.return_value = 'grizzly'
        self.relation_ids.return_value = ['ceph:0']
        self.service_name.return_value = 'glance'
        configs = utils.register_configs()
        calls = []
        for conf in [utils.GLANCE_REGISTRY_CONF,
                     utils.GLANCE_API_CONF,
                     utils.HAPROXY_CONF,
                     utils.ceph_config_file()]:
            calls.append(
                call(conf,
                     utils.CONFIG_FILES[conf]['hook_contexts'])
            )
        configs.register.assert_has_calls(calls, any_order=True)
        self.mkdir.assert_called_with('/etc/ceph')

    def test_restart_map(self):
        self.enable_memcache.return_value = True
        self.config.side_effect = None
        self.service_name.return_value = 'glance'

        ex_map = OrderedDict([
            (utils.GLANCE_REGISTRY_CONF, ['glance-registry']),
            (utils.GLANCE_API_CONF, ['glance-api']),
            (utils.ceph_config_file(), ['glance-api', 'glance-registry']),
            (utils.HAPROXY_CONF, ['haproxy']),
            (utils.HTTPS_APACHE_CONF, ['apache2']),
            (utils.HTTPS_APACHE_24_CONF, ['apache2']),
            (utils.MEMCACHED_CONF, ['memcached'])
        ])
        self.assertEquals(ex_map, utils.restart_map())
        self.enable_memcache.return_value = False
        del ex_map[utils.MEMCACHED_CONF]
        self.assertEquals(ex_map, utils.restart_map())

    @patch.object(utils, 'token_cache_pkgs')
    @patch.object(utils, 'git_install_requested')
    def test_determine_packages(self, git_install_requested, token_cache_pkgs):
        self.config.side_effect = None
        token_cache_pkgs.return_value = []
        git_install_requested.return_value = False
        ex = utils.PACKAGES
        self.assertEquals(set(ex), set(utils.determine_packages()))
        token_cache_pkgs.return_value = ['memcached']
        ex.append('memcached')
        self.assertEquals(set(ex), set(utils.determine_packages()))

    @patch.object(utils, 'token_cache_pkgs')
    @patch.object(utils, 'git_install_requested')
    def test_determine_packages_git(self, git_install_requested,
                                    token_cache_pkgs):
        self.config.side_effect = None
        git_install_requested.return_value = True
        result = utils.determine_packages()
        ex = utils.PACKAGES + utils.BASE_GIT_PACKAGES
        for p in utils.GIT_PACKAGE_BLACKLIST:
            ex.remove(p)
        self.assertEquals(set(ex), set(result))

    @patch.object(utils, 'migrate_database')
    @patch.object(utils, 'git_install_requested')
    def test_openstack_upgrade_leader(self, git_requested, migrate):
        git_requested.return_value = True
        self.config.side_effect = None
        self.config.return_value = 'cloud:precise-havana'
        self.is_elected_leader.return_value = True
        self.get_os_codename_install_source.return_value = 'havana'
        configs = MagicMock()
        utils.do_openstack_upgrade(configs)
        self.assertTrue(configs.write_all.called)
        self.apt_install.assert_called_with(utils.determine_packages(),
                                            fatal=True)
        self.apt_upgrade.assert_called_with(options=DPKG_OPTS,
                                            fatal=True, dist=True)
        configs.set_release.assert_called_with(openstack_release='havana')
        self.assertTrue(migrate.called)

    @patch.object(utils, 'migrate_database')
    @patch.object(utils, 'git_install_requested')
    def test_openstack_upgrade_not_leader(self, git_requested, migrate):
        git_requested.return_value = True
        self.config.side_effect = None
        self.config.return_value = 'cloud:precise-havana'
        self.is_elected_leader.return_value = False
        self.get_os_codename_install_source.return_value = 'havana'
        configs = MagicMock()
        utils.do_openstack_upgrade(configs)
        self.assertTrue(configs.write_all.called)
        self.apt_install.assert_called_with(utils.determine_packages(),
                                            fatal=True)
        self.apt_upgrade.assert_called_with(options=DPKG_OPTS,
                                            fatal=True, dist=True)
        configs.set_release.assert_called_with(openstack_release='havana')
        self.assertFalse(migrate.called)

    @patch.object(utils, 'git_install_requested')
    @patch.object(utils, 'git_clone_and_install')
    @patch.object(utils, 'git_post_install')
    @patch.object(utils, 'git_pre_install')
    def test_git_install(self, git_pre, git_post, git_clone_and_install,
                         git_requested):
        projects_yaml = openstack_origin_git
        git_requested.return_value = True
        utils.git_install(projects_yaml)
        self.assertTrue(git_pre.called)
        git_clone_and_install.assert_called_with(openstack_origin_git,
                                                 core_project='glance')
        self.assertTrue(git_post.called)

    @patch.object(utils, 'mkdir')
    @patch.object(utils, 'write_file')
    @patch.object(utils, 'add_user_to_group')
    @patch.object(utils, 'add_group')
    @patch.object(utils, 'adduser')
    def test_git_pre_install(self, adduser, add_group, add_user_to_group,
                             write_file, mkdir):
        utils.git_pre_install()
        adduser.assert_called_with('glance', shell='/bin/bash',
                                   system_user=True)
        add_group.assert_called_with('glance', system_group=True)
        add_user_to_group.assert_called_with('glance', 'glance')
        expected = [
            call('/var/lib/glance', owner='glance',
                 group='glance', perms=0755, force=False),
            call('/var/lib/glance/images', owner='glance',
                 group='glance', perms=0755, force=False),
            call('/var/lib/glance/image-cache', owner='glance',
                 group='glance', perms=0755, force=False),
            call('/var/lib/glance/image-cache/incomplete', owner='glance',
                 group='glance', perms=0755, force=False),
            call('/var/lib/glance/image-cache/invalid', owner='glance',
                 group='glance', perms=0755, force=False),
            call('/var/lib/glance/image-cache/queue', owner='glance',
                 group='glance', perms=0755, force=False),
            call('/var/log/glance', owner='glance',
                 group='glance', perms=0755, force=False),
        ]
        self.assertEquals(mkdir.call_args_list, expected)
        expected = [
            call('/var/log/glance/glance-api.log', '', owner='glance',
                 group='glance', perms=0600),
            call('/var/log/glance/glance-registry.log', '', owner='glance',
                 group='glance', perms=0600),
        ]
        self.assertEquals(write_file.call_args_list, expected)

    @patch('os.path.join')
    @patch('os.path.exists')
    @patch('os.remove')
    @patch('os.symlink')
    @patch('shutil.copytree')
    @patch('shutil.rmtree')
    @patch('subprocess.check_call')
    def test_git_post_install_upstart(self, check_call, rmtree, copytree,
                                      symlink, remove, exists, join):
        projects_yaml = openstack_origin_git
        join.return_value = 'joined-string'
        self.git_pip_venv_dir.return_value = '/mnt/openstack-git/venv'
        self.lsb_release.return_value = {'DISTRIB_RELEASE': '15.04'}
        utils.git_post_install(projects_yaml)
        expected = [
            call('joined-string', '/etc/glance'),
        ]
        copytree.assert_has_calls(expected)
        expected = [
            call('joined-string', '/usr/local/bin/glance-manage'),
        ]
        symlink.assert_has_calls(expected, any_order=True)
        glance_api_context = {
            'service_description': 'Glance API server',
            'service_name': 'Glance',
            'user_name': 'glance',
            'start_dir': '/var/lib/glance',
            'process_name': 'glance-api',
            'executable_name': 'joined-string',
            'config_files': ['/etc/glance/glance-api.conf'],
            'log_file': '/var/log/glance/api.log',
        }
        glance_registry_context = {
            'service_description': 'Glance registry server',
            'service_name': 'Glance',
            'user_name': 'glance',
            'start_dir': '/var/lib/glance',
            'process_name': 'glance-registry',
            'executable_name': 'joined-string',
            'config_files': ['/etc/glance/glance-registry.conf'],
            'log_file': '/var/log/glance/registry.log',
        }
        expected = [
            call('git.upstart', '/etc/init/glance-api.conf',
                 glance_api_context, perms=0o644,
                 templates_dir='joined-string'),
            call('git.upstart', '/etc/init/glance-registry.conf',
                 glance_registry_context, perms=0o644,
                 templates_dir='joined-string'),
        ]
        self.assertEquals(self.render.call_args_list, expected)
        expected = [
            call('glance-api'),
            call('glance-registry'),
        ]
        self.assertEquals(self.service_restart.call_args_list, expected)

    @patch.object(utils, 'services')
    @patch('os.listdir')
    @patch('os.path.join')
    @patch('os.path.exists')
    @patch('os.symlink')
    @patch('shutil.copytree')
    @patch('shutil.rmtree')
    @patch('subprocess.check_call')
    def test_git_post_install_systemd(self, check_call, rmtree, copytree,
                                      symlink, exists, join, listdir,
                                      services):
        projects_yaml = openstack_origin_git
        join.return_value = 'joined-string'
        self.lsb_release.return_value = {'DISTRIB_RELEASE': '15.10'}
        utils.git_post_install(projects_yaml)

        expected = [
            call('git/glance-api.init.in.template', 'joined-string',
                 {'daemon_path': 'joined-string'}, perms=420),
            call('git/glance-glare.init.in.template', 'joined-string',
                 {'daemon_path': 'joined-string'}, perms=420),
            call('git/glance-registry.init.in.template', 'joined-string',
                 {'daemon_path': 'joined-string'}, perms=420),
        ]
        self.assertEquals(self.render.call_args_list, expected)

    def test_assess_status(self):
        with patch.object(utils, 'assess_status_func') as asf:
            callee = MagicMock()
            asf.return_value = callee
            utils.assess_status('test-config')
            asf.assert_called_once_with('test-config')
            callee.assert_called_once_with()
            self.os_application_version_set.assert_called_with(
                utils.VERSION_PACKAGE
            )

    @patch.object(utils, 'get_optional_interfaces')
    @patch.object(utils, 'REQUIRED_INTERFACES')
    @patch.object(utils, 'services')
    @patch.object(utils, 'make_assess_status_func')
    def test_assess_status_func(self,
                                make_assess_status_func,
                                services,
                                REQUIRED_INTERFACES,
                                get_optional_interfaces):
        services.return_value = 's1'
        REQUIRED_INTERFACES.copy.return_value = {'int': ['test 1']}
        get_optional_interfaces.return_value = {'opt': ['test 2']}
        utils.assess_status_func('test-config')
        # ports=None whilst port checks are disabled.
        make_assess_status_func.assert_called_once_with(
            'test-config',
            {'int': ['test 1'], 'opt': ['test 2']},
            charm_func=utils.check_optional_relations,
            services='s1', ports=None)

    def test_pause_unit_helper(self):
        with patch.object(utils, '_pause_resume_helper') as prh:
            utils.pause_unit_helper('random-config')
            prh.assert_called_once_with(utils.pause_unit, 'random-config')
        with patch.object(utils, '_pause_resume_helper') as prh:
            utils.resume_unit_helper('random-config')
            prh.assert_called_once_with(utils.resume_unit, 'random-config')

    @patch.object(utils, 'services')
    def test_pause_resume_helper(self, services):
        f = MagicMock()
        services.return_value = 's1'
        with patch.object(utils, 'assess_status_func') as asf:
            asf.return_value = 'assessor'
            utils._pause_resume_helper(f, 'some-config')
            asf.assert_called_once_with('some-config')
            # ports=None whilst port checks are disabled.
            f.assert_called_once_with('assessor', services='s1', ports=None)

    @patch.object(utils, 'os')
    @patch.object(utils, 'kv')
    def test_reinstall_paste_ini(self, kv, _os):
        """Ensure that paste.ini files are re-installed"""
        _os.path.exists.return_value = True
        test_kv = SimpleKV()
        kv.return_value = test_kv
        utils.reinstall_paste_ini()
        self.apt_install.assert_called_with(
            packages=['glance-api', 'glance-registry'],
            options=utils.REINSTALL_OPTIONS,
            fatal=True
        )
        _os.path.exists.assert_has_calls([
            call(utils.GLANCE_REGISTRY_PASTE),
            call(utils.GLANCE_API_PASTE),
        ])
        _os.remove.assert_has_calls([
            call(utils.GLANCE_REGISTRY_PASTE),
            call(utils.GLANCE_API_PASTE),
        ])
        self.assertTrue(test_kv.get(utils.PASTE_INI_MARKER))
        self.assertTrue(test_kv.flushed)

    @patch.object(utils, 'kv')
    def test_reinstall_paste_ini_idempotent(self, kv):
        """Ensure that re-running does not re-install files"""
        test_kv = SimpleKV()
        test_kv.set(utils.PASTE_INI_MARKER, True)
        kv.return_value = test_kv
        utils.reinstall_paste_ini()
        self.assertFalse(self.apt_install.called)

    def _test_is_api_ready(self, tgt):
        fake_config = MagicMock()
        with patch.object(utils, 'incomplete_relation_data') as ird:
            ird.return_value = (not tgt)
            self.assertEqual(utils.is_api_ready(fake_config), tgt)
            ird.assert_called_with(
                fake_config, utils.REQUIRED_INTERFACES)

    def test_is_api_ready_true(self):
        self._test_is_api_ready(True)

    def test_is_api_ready_false(self):
        self._test_is_api_ready(False)
