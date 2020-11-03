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
from mock import patch, call, MagicMock, mock_open

os.environ['JUJU_UNIT_NAME'] = 'glance'
import glance_utils as utils

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
    'apt_purge',
    'apt_autoremove',
    'filter_missing_packages',
    'mkdir',
    'os_release',
    'service_start',
    'service_stop',
    'service_name',
    'install_alternative',
    'lsb_release',
    'os_application_version_set',
    'enable_memcache',
    'token_cache_pkgs',
    'set_db_initialised',
]

DPKG_OPTS = [
    '--option', 'Dpkg::Options::=--force-confnew',
    '--option', 'Dpkg::Options::=--force-confdef',
]


class TestGlanceUtils(CharmTestCase):

    def setUp(self):
        super(TestGlanceUtils, self).setUp(utils, TO_PATCH)
        self.config.side_effect = self.test_config.get

    @patch('subprocess.check_call')
    def test_migrate_database(self, check_call):
        "It migrates database with cinder-manage"
        utils.migrate_database()
        check_call.assert_called_with(['glance-manage', 'db_sync'])
        self.set_db_initialised.assert_called_once_with()

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

    @patch('os.path.exists')
    def test_register_configs_mitaka(self, exists):
        exists.return_value = True
        self.os_release.return_value = 'mitaka'
        self.relation_ids.return_value = False
        configs = utils.register_configs()
        calls = []
        for conf in [utils.GLANCE_REGISTRY_CONF,
                     utils.GLANCE_API_CONF,
                     utils.GLANCE_SWIFT_CONF,
                     utils.HAPROXY_CONF,
                     utils.HTTPS_APACHE_24_CONF]:
            calls.append(
                call(conf,
                     utils.CONFIG_FILES[conf]['hook_contexts'])
            )
        configs.register.assert_has_calls(calls, any_order=True)

    def test_restart_map_rocky(self):
        self.enable_memcache.return_value = True
        self.config.side_effect = None
        self.service_name.return_value = 'glance'
        self.os_release.return_value = 'rocky'

        ex_map = OrderedDict([
            (utils.GLANCE_REGISTRY_CONF, ['glance-registry']),
            (utils.GLANCE_API_CONF, ['glance-api']),
            (utils.GLANCE_SWIFT_CONF, ['glance-api']),
            (utils.GLANCE_POLICY_FILE, ['glance-api', 'glance-registry']),
            (utils.ceph_config_file(), ['glance-api', 'glance-registry']),
            (utils.HAPROXY_CONF, ['haproxy']),
            (utils.HTTPS_APACHE_CONF, ['apache2']),
            (utils.HTTPS_APACHE_24_CONF, ['apache2']),
            (utils.APACHE_PORTS_CONF, ['apache2']),
            (utils.MEMCACHED_CONF, ['memcached']),
        ])
        self.assertEqual(ex_map, utils.restart_map())
        self.enable_memcache.return_value = False
        del ex_map[utils.MEMCACHED_CONF]
        self.assertEqual(ex_map, utils.restart_map())

    def test_restart_map_stein(self):
        self.enable_memcache.return_value = True
        self.config.side_effect = None
        self.service_name.return_value = 'glance'
        self.os_release.return_value = 'stein'

        ex_map = OrderedDict([
            (utils.GLANCE_API_CONF, ['glance-api']),
            (utils.GLANCE_SWIFT_CONF, ['glance-api']),
            (utils.GLANCE_POLICY_FILE, ['glance-api']),
            (utils.ceph_config_file(), ['glance-api']),
            (utils.HAPROXY_CONF, ['haproxy']),
            (utils.HTTPS_APACHE_CONF, ['apache2']),
            (utils.HTTPS_APACHE_24_CONF, ['apache2']),
            (utils.APACHE_PORTS_CONF, ['apache2']),
            (utils.MEMCACHED_CONF, ['memcached']),
        ])
        self.assertEqual(ex_map, utils.restart_map())
        self.enable_memcache.return_value = False
        del ex_map[utils.MEMCACHED_CONF]
        self.assertEqual(ex_map, utils.restart_map())

    @patch.object(utils.os.path, 'isdir')
    def test_restart_map_stein_ssl(self, isdir):
        isdir.return_value = True
        self.enable_memcache.return_value = True
        self.config.side_effect = None
        self.service_name.return_value = 'glance'
        self.os_release.return_value = 'stein'

        ex_map = OrderedDict([
            (utils.GLANCE_API_CONF, ['glance-api']),
            (utils.GLANCE_SWIFT_CONF, ['glance-api']),
            (utils.GLANCE_POLICY_FILE, ['glance-api']),
            (utils.ceph_config_file(), ['glance-api']),
            (utils.HAPROXY_CONF, ['haproxy']),
            (utils.HTTPS_APACHE_CONF, ['apache2']),
            (utils.HTTPS_APACHE_24_CONF, ['apache2']),
            (utils.APACHE_PORTS_CONF, ['apache2']),
            (utils.MEMCACHED_CONF, ['memcached']),
            ('{}/*'.format(utils.APACHE_SSL_DIR),
             ['glance-api', 'apache2']),
        ])
        self.assertEqual(ex_map, utils.restart_map())
        self.enable_memcache.return_value = False
        del ex_map[utils.MEMCACHED_CONF]
        self.assertEqual(ex_map, utils.restart_map())

    @patch.object(utils, 'token_cache_pkgs')
    def test_determine_packages(self, token_cache_pkgs):
        self.config.side_effect = None
        self.os_release.return_value = 'queens'
        token_cache_pkgs.return_value = []
        ex = utils.PACKAGES
        self.assertEqual(set(ex), set(utils.determine_packages()))
        token_cache_pkgs.return_value = ['memcached']
        ex.append('memcached')
        self.assertEqual(set(ex), set(utils.determine_packages()))

    @patch.object(utils, 'migrate_database')
    def test_openstack_upgrade_leader(self, migrate):
        self.config.side_effect = None
        self.config.return_value = 'cloud:precise-havana'
        self.os_release.return_value = 'havana'
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
    def test_openstack_upgrade_rocky(self, migrate):
        self.config.side_effect = None
        self.config.return_value = 'cloud:bionic-rocky'
        self.os_release.return_value = 'rocky'
        self.is_elected_leader.return_value = True
        self.get_os_codename_install_source.return_value = 'rocky'
        self.filter_missing_packages.return_value = ['python-glance']
        configs = MagicMock()
        utils.do_openstack_upgrade(configs)
        self.assertTrue(configs.write_all.called)
        self.apt_install.assert_called_with(utils.determine_packages(),
                                            fatal=True)
        self.apt_upgrade.assert_called_with(options=DPKG_OPTS,
                                            fatal=True, dist=True)
        self.apt_purge.assert_called_with(['python-glance'], fatal=True)
        self.apt_autoremove.assert_called_with(purge=True, fatal=True)
        configs.set_release.assert_called_with(openstack_release='rocky')
        self.assertTrue(migrate.called)

    @patch.object(utils, 'migrate_database')
    def test_openstack_upgrade_not_leader(self, migrate):
        self.config.side_effect = None
        self.config.return_value = 'cloud:precise-havana'
        self.os_release.return_value = 'havana'
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

    @patch.object(utils, 'get_managed_services_and_ports')
    @patch.object(utils, 'get_optional_interfaces')
    @patch.object(utils, 'REQUIRED_INTERFACES')
    @patch.object(utils, 'services')
    @patch.object(utils, 'make_assess_status_func')
    def test_assess_status_func(self,
                                make_assess_status_func,
                                services,
                                REQUIRED_INTERFACES,
                                get_optional_interfaces,
                                get_managed_services_and_ports):
        get_managed_services_and_ports.return_value = (['s1'], [])
        services.return_value = 's1'
        REQUIRED_INTERFACES.copy.return_value = {'int': ['test 1']}
        get_optional_interfaces.return_value = {'opt': ['test 2']}
        utils.assess_status_func('test-config')
        # ports=None whilst port checks are disabled.
        make_assess_status_func.assert_called_once_with(
            'test-config',
            {'int': ['test 1'], 'opt': ['test 2']},
            charm_func=utils.check_optional_config_and_relations,
            services=['s1'], ports=None)

    def test_pause_unit_helper(self):
        with patch.object(utils, '_pause_resume_helper') as prh:
            utils.pause_unit_helper('random-config')
            prh.assert_called_once_with(utils.pause_unit, 'random-config')
        with patch.object(utils, '_pause_resume_helper') as prh:
            utils.resume_unit_helper('random-config')
            prh.assert_called_once_with(utils.resume_unit, 'random-config')

    @patch.object(utils, 'get_managed_services_and_ports')
    @patch.object(utils, 'services')
    def test_pause_resume_helper(self, services,
                                 get_managed_services_and_ports):
        f = MagicMock()
        services.return_value = ['s1']
        get_managed_services_and_ports.return_value = (['s1'], [])
        with patch.object(utils, 'assess_status_func') as asf:
            asf.return_value = 'assessor'
            utils._pause_resume_helper(f, 'some-config')
            asf.assert_called_once_with('some-config')
            # ports=None whilst port checks are disabled.
            f.assert_called_once_with('assessor', services=['s1'], ports=None)

    @patch.object(utils, 'os_release')
    @patch.object(utils, 'os')
    @patch.object(utils, 'kv')
    def test_reinstall_paste_ini(self, kv, _os, mock_os_release):
        """Ensure that paste.ini files are re-installed"""
        mock_os_release.return_value = 'pike'
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

    @patch.object(utils, 'os_release')
    @patch.object(utils, 'os')
    @patch.object(utils, 'kv')
    def test_reinstall_paste_ini_queens(self, kv, _os, mock_os_release):
        """Ensure that paste.ini files are re-installed"""
        mock_os_release.return_value = 'queens'
        _os.path.exists.return_value = True
        test_kv = SimpleKV()
        kv.return_value = test_kv

        utils.reinstall_paste_ini()
        self.apt_install.assert_called_with(
            packages=['glance-api', 'glance-registry'],
            options=utils.REINSTALL_OPTIONS,
            fatal=True
        )

    @patch.object(utils, 'os_release')
    @patch.object(utils, 'os')
    @patch.object(utils, 'kv')
    def test_reinstall_paste_ini_rocky(self, kv, _os, mock_os_release):
        """Ensure that paste.ini files are re-installed"""
        mock_os_release.return_value = 'queens'
        _os.path.exists.return_value = True
        test_kv = SimpleKV()
        kv.return_value = test_kv

        self.apt_install.reset_mock()
        mock_os_release.return_value = 'rocky'
        utils.reinstall_paste_ini()
        self.apt_install.assert_called_with(
            packages=['glance-common'],
            options=utils.REINSTALL_OPTIONS,
            fatal=True
        )

    @patch.object(os.path, 'exists')
    @patch.object(utils, 'os_release')
    @patch.object(utils, 'kv')
    def test_reinstall_paste_ini_idempotent(self, kv, mock_os_release,
                                            mock_exists):
        """Ensure that re-running does not re-install files"""
        mock_exists.return_value = True
        mock_os_release.return_value = "queens"
        test_kv = SimpleKV()
        test_kv.set(utils.PASTE_INI_MARKER, True)
        kv.return_value = test_kv
        utils.reinstall_paste_ini()
        self.assertFalse(self.apt_install.called)

    @patch.object(os.path, 'exists')
    @patch.object(utils, 'os_release')
    @patch.object(utils, 'kv')
    def test_reinstall_paste_ini_fix_upgrade(self, kv, mock_os_release,
                                             mock_exists):
        mock_exists.return_value = False
        mock_os_release.return_value = "queens"
        test_kv = SimpleKV()
        test_kv.set(utils.PASTE_INI_MARKER, True)
        kv.return_value = test_kv
        utils.reinstall_paste_ini()
        self.assertTrue(self.apt_install.called)

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

    @patch.object(utils, 'config')
    @patch.object(utils, 'json')
    @patch.object(utils, 'update_json_file')
    @patch.object(utils, 'kv')
    @patch.object(utils, 'os_release')
    def test_update_image_location_policy(self, mock_os_release, mock_kv,
                                          mock_update_json_file, mock_json,
                                          mock_config):
        db_vals = {}
        config = {'restrict-image-location-operations': False}

        def fake_config(key):
            return config.get(key)

        def fake_db_get(key):
            return db_vals.get(key)

        db_obj = mock_kv.return_value
        db_obj.get = MagicMock()
        db_obj.get.side_effect = fake_db_get
        db_obj.set = MagicMock()

        mock_config.side_effect = fake_config

        fake_open = mock_open()
        with patch.object(utils, 'open', fake_open, create=True):
            mock_json.loads.return_value = {'get_image_location': '',
                                            'set_image_location': '',
                                            'delete_image_location': ''}

            mock_os_release.return_value = 'icehouse'
            utils.update_image_location_policy()
            self.assertFalse(mock_kv.called)

            # Function has no effect in ussuri onwards
            mock_os_release.return_value = 'ussuri'
            utils.update_image_location_policy()
            self.assertFalse(mock_kv.called)

            mock_os_release.return_value = 'kilo'
            utils.update_image_location_policy()
            self.assertTrue(mock_kv.called)

            mock_update_json_file.assert_has_calls([
                call('/etc/glance/policy.json',
                     {'get_image_location': '',
                      'set_image_location': '',
                      'delete_image_location': ''})])

            mock_update_json_file.reset_mock()
            config['restrict-image-location-operations'] = True
            utils.update_image_location_policy()
            mock_update_json_file.assert_has_calls([
                call('/etc/glance/policy.json',
                     {'get_image_location': 'role:admin',
                      'set_image_location': 'role:admin',
                      'delete_image_location': 'role:admin'})])

            db_obj.get.assert_has_calls([call('policy_get_image_location'),
                                         call('policy_set_image_location'),
                                         call('policy_delete_image_location')])

    @patch.object(utils, 'CephBlueStoreCompressionContext')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_request_access_to_group')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_create_replicated_pool')
    def test_create_pool_op(self, mock_create_pool,
                            mock_request_access,
                            mock_bluestore_compression):
        self.service_name.return_value = 'glance'
        self.test_config.set('ceph-osd-replication-count', 3)
        self.test_config.set('ceph-pool-weight', 6)
        utils.get_ceph_request()
        mock_create_pool.assert_called_once_with(
            name='glance',
            replica_count=3,
            weight=6,
            group='images',
            app_name='rbd')
        mock_request_access.assert_not_called()

        self.test_config.set('restrict-ceph-pools', True)
        utils.get_ceph_request()
        mock_create_pool.assert_called_with(name='glance', replica_count=3,
                                            weight=6, group='images',
                                            app_name='rbd')
        mock_request_access.assert_has_calls([
            call(
                name='images',
                object_prefix_permissions={'class-read': ['rbd_children']},
                permission='rwx'),
        ])

        # confirm operation with bluestore compression
        mock_create_pool.reset_mock()
        mock_bluestore_compression().get_kwargs.return_value = {
            'compression_mode': 'fake',
        }
        utils.get_ceph_request()
        mock_create_pool.assert_called_once_with(
            name='glance',
            replica_count=3,
            weight=6,
            group='images',
            app_name='rbd',
            compression_mode='fake')

    @patch.object(utils, 'CephBlueStoreCompressionContext')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_create_erasure_pool')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_create_erasure_profile')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_request_access_to_group')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_create_pool')
    def test_create_ec_pool_op(self, mock_create_pool,
                               mock_request_access,
                               mock_create_erasure_profile,
                               mock_create_erasure_pool,
                               mock_bluestore_compression):
        self.service_name.return_value = 'glance'
        self.test_config.set('ceph-osd-replication-count', 3)
        self.test_config.set('ceph-pool-weight', 6)
        self.test_config.set('pool-type', 'erasure-coded')
        self.test_config.set('ec-profile-plugin', 'isa')
        self.test_config.set('ec-profile-k', 6)
        self.test_config.set('ec-profile-m', 2)
        self.test_config.set('rbd-pool-name', 'glance')
        utils.get_ceph_request()
        mock_create_pool.assert_called_once_with(
            name='glance-metadata',
            replica_count=3,
            weight=0.06,
            group='images',
            app_name='rbd')
        mock_create_erasure_profile.assert_called_once_with(
            name='glance-profile',
            k=6, m=2,
            lrc_locality=None,
            lrc_crush_locality=None,
            shec_durability_estimator=None,
            clay_helper_chunks=None,
            clay_scalar_mds=None,
            device_class=None,
            erasure_type='isa',
            erasure_technique=None,
        )
        mock_create_erasure_pool.assert_called_once_with(
            name='glance',
            erasure_profile='glance-profile',
            weight=5.94,
            group='images',
            app_name='rbd',
            allow_ec_overwrites=True)
        mock_request_access.assert_not_called()

        # confirm operation with bluestore compression
        mock_create_erasure_pool.reset_mock()
        mock_bluestore_compression().get_kwargs.return_value = {
            'compression_mode': 'fake',
        }
        utils.get_ceph_request()
        mock_create_erasure_pool.assert_called_once_with(
            name='glance',
            erasure_profile='glance-profile',
            weight=5.94,
            group='images',
            app_name='rbd',
            allow_ec_overwrites=True,
            compression_mode='fake')
