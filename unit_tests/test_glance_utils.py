from mock import patch, call, MagicMock

from collections import OrderedDict
import os

os.environ['JUJU_UNIT_NAME'] = 'glance'

import hooks.glance_utils as utils
from test_utils import (
    CharmTestCase,
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
    'mkdir',
    'os_release',
    'pip_install',
    'service_start',
    'service_stop',
    'service_name',
    'install_alternative'
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
                     utils.GLANCE_API_PASTE_INI,
                     utils.GLANCE_REGISTRY_PASTE_INI,
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
                     utils.GLANCE_API_PASTE_INI,
                     utils.GLANCE_REGISTRY_PASTE_INI,
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
                     utils.GLANCE_API_PASTE_INI,
                     utils.GLANCE_REGISTRY_PASTE_INI,
                     utils.HAPROXY_CONF,
                     utils.ceph_config_file()]:
            calls.append(
                call(conf,
                     utils.CONFIG_FILES[conf]['hook_contexts'])
            )
        configs.register.assert_has_calls(calls, any_order=True)
        self.mkdir.assert_called_with('/etc/ceph')

    def test_restart_map(self):
        self.service_name.return_value = 'glance'

        ex_map = OrderedDict([
            (utils.GLANCE_REGISTRY_CONF, ['glance-registry']),
            (utils.GLANCE_API_CONF, ['glance-api']),
            (utils.GLANCE_API_PASTE_INI, ['glance-api']),
            (utils.GLANCE_REGISTRY_PASTE_INI, ['glance-registry']),
            (utils.ceph_config_file(), ['glance-api', 'glance-registry']),
            (utils.HAPROXY_CONF, ['haproxy']),
            (utils.HTTPS_APACHE_CONF, ['apache2']),
            (utils.HTTPS_APACHE_24_CONF, ['apache2'])
        ])
        self.assertEquals(ex_map, utils.restart_map())

    @patch.object(utils, 'git_install_requested')
    def test_determine_packages(self, git_install_requested):
        git_install_requested.return_value = False
        result = utils.determine_packages()
        ex = utils.PACKAGES
        self.assertEquals(set(ex), set(result))

    @patch.object(utils, 'git_install_requested')
    def test_determine_packages_git(self, git_install_requested):
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

    @patch.object(utils, 'git_src_dir')
    @patch.object(utils, 'service_restart')
    @patch.object(utils, 'render')
    @patch.object(utils, 'git_pip_venv_dir')
    @patch('os.path.join')
    @patch('os.path.exists')
    @patch('os.symlink')
    @patch('shutil.copytree')
    @patch('shutil.rmtree')
    @patch('subprocess.check_call')
    def test_git_post_install(self, check_call, rmtree, copytree, symlink,
                              exists, join, venv, render, service_restart,
                              git_src_dir):
        projects_yaml = openstack_origin_git
        join.return_value = 'joined-string'
        venv.return_value = '/mnt/openstack-git/venv'
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
        self.assertEquals(render.call_args_list, expected)
        expected = [
            call('glance-api'),
            call('glance-registry'),
        ]
        self.assertEquals(service_restart.call_args_list, expected)
