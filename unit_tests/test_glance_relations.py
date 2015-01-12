from mock import call, patch, MagicMock
import json
import os

from test_utils import CharmTestCase

os.environ['JUJU_UNIT_NAME'] = 'glance'
import glance_utils as utils

_reg = utils.register_configs
_map = utils.restart_map

utils.register_configs = MagicMock()
utils.restart_map = MagicMock()

import glance_relations as relations

relations.hooks._config_save = False

utils.register_configs = _reg
utils.restart_map = _map

TO_PATCH = [
    # charmhelpers.core.hookenv
    'Hooks',
    'canonical_url',
    'config',
    'juju_log',
    'is_relation_made',
    'local_unit',
    'open_port',
    'relation_ids',
    'relation_set',
    'relation_get',
    'service_name',
    'unit_get',
    # charmhelpers.core.host
    'apt_install',
    'apt_update',
    'restart_on_change',
    'service_stop',
    # charmhelpers.contrib.openstack.utils
    'configure_installation_source',
    'get_os_codename_package',
    'openstack_upgrade_available',
    # charmhelpers.contrib.hahelpers.cluster_utils
    'eligible_leader',
    # glance_utils
    'restart_map',
    'register_configs',
    'do_openstack_upgrade',
    'migrate_database',
    'ensure_ceph_keyring',
    'ceph_config_file',
    'update_nrpe_config',
    # other
    'call',
    'check_call',
    'execd_preinstall',
    'lsb_release',
    'filter_installed_packages',
    'get_hacluster_config',
    'get_netmask_for_address',
    'get_iface_for_address',
    'get_ipv6_addr',
    'sync_db_with_multi_ipv6_addresses',
]


class GlanceRelationTests(CharmTestCase):

    def setUp(self):
        super(GlanceRelationTests, self).setUp(relations, TO_PATCH)
        self.config.side_effect = self.test_config.get

    def test_install_hook(self):
        repo = 'cloud:precise-grizzly'
        self.test_config.set('openstack-origin', repo)
        self.service_stop.return_value = True
        relations.install_hook()
        self.configure_installation_source.assert_called_with(repo)
        self.apt_update.assert_called_with(fatal=True)
        self.apt_install.assert_called_with(['apache2', 'glance',
                                             'python-mysqldb',
                                             'python-swiftclient',
                                             'python-psycopg2',
                                             'python-keystone',
                                             'python-six',
                                             'uuid', 'haproxy'], fatal=True)
        self.assertTrue(self.execd_preinstall.called)

    def test_install_hook_precise_distro(self):
        self.test_config.set('openstack-origin', 'distro')
        self.lsb_release.return_value = {'DISTRIB_RELEASE': 12.04,
                                         'DISTRIB_CODENAME': 'precise'}
        self.service_stop.return_value = True
        relations.install_hook()
        self.configure_installation_source.assert_called_with(
            "cloud:precise-folsom"
        )

    def test_db_joined(self):
        self.unit_get.return_value = 'glance.foohost.com'
        self.is_relation_made.return_value = False
        relations.db_joined()
        self.relation_set.assert_called_with(database='glance',
                                             username='glance',
                                             hostname='glance.foohost.com')
        self.unit_get.assert_called_with('private-address')

    @patch.object(relations, 'sync_db_with_multi_ipv6_addresses')
    @patch.object(relations, 'get_ipv6_addr')
    def test_db_joined_with_ipv6(self, mock_get_ipv6_addr,
                                 mock_sync_db):
        self.test_config.set('prefer-ipv6', True)
        mock_get_ipv6_addr.return_value = ['2001:db8:1::1']
        mock_sync_db.return_value = MagicMock()
        self.is_relation_made.return_value = False
        relations.db_joined()
        relation_data = {
            'database': 'glance',
            'username': 'glance',
        }
        relation_data['hostname'] = '2001:db8:1::1'

        self.sync_db_with_multi_ipv6_addresses.assert_called_with_once(
            'glance', 'glance')
        self.get_ipv6_addr.assert_called_once()

    def test_postgresql_db_joined(self):
        self.unit_get.return_value = 'glance.foohost.com'
        self.is_relation_made.return_value = False
        relations.pgsql_db_joined()
        self.relation_set.assert_called_with(database='glance'),

    def test_db_joined_with_postgresql(self):
        self.is_relation_made.return_value = True

        with self.assertRaises(Exception) as context:
            relations.db_joined()
        self.assertEqual(context.exception.message,
                         'Attempting to associate a mysql database when there '
                         'is already associated a postgresql one')

    def test_postgresql_joined_with_db(self):
        self.is_relation_made.return_value = True

        with self.assertRaises(Exception) as context:
            relations.pgsql_db_joined()
        self.assertEqual(context.exception.message,
                         'Attempting to associate a postgresql database when'
                         ' there is already associated a mysql one')

    @patch.object(relations, 'CONFIGS')
    def test_db_changed_missing_relation_data(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = []
        relations.db_changed()
        self.juju_log.assert_called_with(
            'shared-db relation incomplete. Peer not ready?'
        )

    @patch.object(relations, 'CONFIGS')
    def test_postgresql_db_changed_missing_relation_data(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = []
        relations.pgsql_db_changed()
        self.juju_log.assert_called_with(
            'pgsql-db relation incomplete. Peer not ready?'
        )

    def _shared_db_test(self, configs, unit_name):
        self.relation_get.return_value = 'glance/0 glance/3'
        self.local_unit.return_value = unit_name
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['shared-db']
        configs.write = MagicMock()
        relations.db_changed()

    def _postgresql_db_test(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['pgsql-db']
        configs.write = MagicMock()
        relations.pgsql_db_changed()

    @patch.object(relations, 'CONFIGS')
    def test_db_changed_allowed(self, configs):
        self._shared_db_test(configs, 'glance/0')
        self.assertEquals([call('/etc/glance/glance-registry.conf'),
                           call('/etc/glance/glance-api.conf')],
                          configs.write.call_args_list)
        self.juju_log.assert_called_with(
            'Cluster leader, performing db sync'
        )
        self.migrate_database.assert_called_with()

    @patch.object(relations, 'CONFIGS')
    def test_db_changed_not_allowed(self, configs):
        self._shared_db_test(configs, 'glance/2')
        self.assertEquals([call('/etc/glance/glance-registry.conf'),
                           call('/etc/glance/glance-api.conf')],
                          configs.write.call_args_list)
        self.assertFalse(self.migrate_database.called)

    @patch.object(relations, 'CONFIGS')
    def test_postgresql_db_changed_no_essex(self, configs):
        self._postgresql_db_test(configs)
        self.assertEquals([call('/etc/glance/glance-registry.conf'),
                           call('/etc/glance/glance-api.conf')],
                          configs.write.call_args_list)
        self.juju_log.assert_called_with(
            'Cluster leader, performing db sync'
        )
        self.migrate_database.assert_called_with()

    @patch.object(relations, 'CONFIGS')
    def test_db_changed_with_essex_not_setting_version_control(self, configs):
        self.get_os_codename_package.return_value = "essex"
        self.call.return_value = 0
        self._shared_db_test(configs, 'glance/0')
        self.assertEquals([call('/etc/glance/glance-registry.conf')],
                          configs.write.call_args_list)
        self.juju_log.assert_called_with(
            'Cluster leader, performing db sync'
        )
        self.migrate_database.assert_called_with()

    @patch.object(relations, 'CONFIGS')
    def test_postgresql_db_changed_with_essex_not_setting_version_control(
            self, configs):
        self.get_os_codename_package.return_value = "essex"
        self.call.return_value = 0
        self._postgresql_db_test(configs)
        self.assertEquals([call('/etc/glance/glance-registry.conf')],
                          configs.write.call_args_list)
        self.juju_log.assert_called_with(
            'Cluster leader, performing db sync'
        )
        self.migrate_database.assert_called_with()

    @patch.object(relations, 'CONFIGS')
    def test_db_changed_with_essex_setting_version_control(self, configs):
        self.get_os_codename_package.return_value = "essex"
        self.call.return_value = 1
        self._shared_db_test(configs, 'glance/0')
        self.assertEquals([call('/etc/glance/glance-registry.conf')],
                          configs.write.call_args_list)
        self.check_call.assert_called_with(
            ["glance-manage", "version_control", "0"]
        )
        self.juju_log.assert_called_with(
            'Cluster leader, performing db sync'
        )
        self.migrate_database.assert_called_with()

    @patch.object(relations, 'CONFIGS')
    def test_postgresql_db_changed_with_essex_setting_version_control(
            self, configs):
        self.get_os_codename_package.return_value = "essex"
        self.call.return_value = 1
        self._postgresql_db_test(configs)
        self.assertEquals([call('/etc/glance/glance-registry.conf')],
                          configs.write.call_args_list)
        self.check_call.assert_called_with(
            ["glance-manage", "version_control", "0"]
        )
        self.juju_log.assert_called_with(
            'Cluster leader, performing db sync'
        )
        self.migrate_database.assert_called_with()

    def test_image_service_joined_leader(self):
        self.canonical_url.return_value = 'http://glancehost'
        relations.image_service_joined()
        args = {
            'glance-api-server': 'http://glancehost:9292',
            'relation_id': None
        }
        self.relation_set.assert_called_with(**args)

    def test_image_service_joined_specified_interface(self):
        self.canonical_url.return_value = 'http://glancehost'
        relations.image_service_joined(relation_id='image-service:1')
        args = {
            'glance-api-server': 'http://glancehost:9292',
            'relation_id': 'image-service:1',
        }
        self.relation_set.assert_called_with(**args)

    @patch.object(relations, 'CONFIGS')
    def test_object_store_joined_without_identity_service(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['']
        configs.write = MagicMock()
        relations.object_store_joined()
        self.juju_log.assert_called_with(
            'Deferring swift storage configuration until '
            'an identity-service relation exists'
        )

    @patch.object(relations, 'CONFIGS')
    def test_object_store_joined_with_identity_service_without_object_store(
            self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['identity-service']
        configs.write = MagicMock()
        relations.object_store_joined()
        self.juju_log.assert_called_with(
            'swift relation incomplete'
        )

    @patch.object(relations, 'CONFIGS')
    def test_object_store_joined_with_identity_service_with_object_store(
            self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['identity-service',
                                                  'object-store']
        configs.write = MagicMock()
        relations.object_store_joined()
        self.assertEquals([call('/etc/glance/glance-api.conf')],
                          configs.write.call_args_list)

    def test_ceph_joined(self):
        relations.ceph_joined()
        self.apt_install.assert_called_with(['ceph-common', 'python-ceph'])

    @patch.object(relations, 'CONFIGS')
    def test_ceph_changed_missing_relation_data(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = []
        configs.write = MagicMock()
        relations.ceph_changed()
        self.juju_log.assert_called_with(
            'ceph relation incomplete. Peer not ready?'
        )

    @patch.object(relations, 'CONFIGS')
    def test_ceph_changed_no_keyring(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['ceph']
        configs.write = MagicMock()
        self.ensure_ceph_keyring.return_value = False
        relations.ceph_changed()
        self.juju_log.assert_called_with(
            'Could not create ceph keyring: peer not ready?'
        )

    @patch("glance_relations.relation_set")
    @patch("glance_relations.relation_get")
    @patch.object(relations, 'CONFIGS')
    def test_ceph_changed_broker_send_rq(self, configs, mock_relation_get,
                                         mock_relation_set):
        configs.complete_contexts.return_value = ['ceph']
        self.service_name.return_value = 'glance'
        self.ensure_ceph_keyring.return_value = True
        self.relation_ids.return_value = ['ceph:0']
        relations.hooks.execute(['hooks/ceph-relation-changed'])
        self.ensure_ceph_keyring.assert_called_with(service='glance',
                                                    user='glance',
                                                    group='glance')
        req = {'api-version': 1,
               'ops': [{"op": "create-pool", "name": "glance", "replicas": 3}]}
        broker_dict = json.dumps(req)
        mock_relation_set.assert_called_with(broker_req=broker_dict,
                                             relation_id='ceph:0')
        for c in [call('/etc/glance/glance.conf')]:
            self.assertNotIn(c, configs.write.call_args_list)

    @patch("glance_relations.relation_get", autospec=True)
    @patch.object(relations, 'CONFIGS')
    def test_ceph_changed_with_key_and_relation_data(self, configs,
                                                     mock_relation_get):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['ceph']
        configs.write = MagicMock()
        self.ensure_ceph_keyring.return_value = True
        mock_relation_get.return_value = {'broker_rsp':
                                          json.dumps({'exit-code': 0})}
        relations.ceph_changed()
        self.assertEquals([call('/etc/glance/glance-api.conf'),
                           call(self.ceph_config_file())],
                          configs.write.call_args_list)

    def test_keystone_joined(self):
        self.canonical_url.return_value = 'http://glancehost'
        relations.keystone_joined()
        ex = {
            'region': 'RegionOne',
            'public_url': 'http://glancehost:9292',
            'admin_url': 'http://glancehost:9292',
            'service': 'glance',
            'internal_url': 'http://glancehost:9292',
            'relation_id': None,
        }
        self.relation_set.assert_called_with(**ex)

    def test_keystone_joined_with_relation_id(self):
        self.canonical_url.return_value = 'http://glancehost'
        relations.keystone_joined(relation_id='identity-service:0')
        ex = {
            'region': 'RegionOne',
            'public_url': 'http://glancehost:9292',
            'admin_url': 'http://glancehost:9292',
            'service': 'glance',
            'internal_url': 'http://glancehost:9292',
            'relation_id': 'identity-service:0',
        }
        self.relation_set.assert_called_with(**ex)

    @patch.object(relations, 'CONFIGS')
    def test_keystone_changes_incomplete(self, configs):
        configs.complete_contexts.return_value = []
        relations.keystone_changed()
        self.assertTrue(self.juju_log.called)
        self.assertFalse(configs.write.called)

    @patch.object(relations, 'configure_https')
    @patch.object(relations, 'CONFIGS')
    def test_keystone_changed_no_object_store_relation(self, configs,
                                                       configure_https):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['identity-service']
        configs.write = MagicMock()
        self.relation_ids.return_value = []
        relations.keystone_changed()
        self.assertEquals([call('/etc/glance/glance-api.conf'),
                           call('/etc/glance/glance-registry.conf'),
                           call('/etc/glance/glance-api-paste.ini'),
                           call('/etc/glance/glance-registry-paste.ini')],
                          configs.write.call_args_list)
        self.assertTrue(configure_https.called)

    @patch.object(relations, 'configure_https')
    @patch.object(relations, 'object_store_joined')
    @patch.object(relations, 'CONFIGS')
    def test_keystone_changed_with_object_store_relation(
            self, configs, object_store_joined, configure_https):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['identity-service']
        configs.write = MagicMock()
        self.relation_ids.return_value = ['object-store:0']
        relations.keystone_changed()
        self.assertEquals([call('/etc/glance/glance-api.conf'),
                           call('/etc/glance/glance-registry.conf'),
                           call('/etc/glance/glance-api-paste.ini'),
                           call('/etc/glance/glance-registry-paste.ini')],
                          configs.write.call_args_list)
        object_store_joined.assert_called_with()
        self.assertTrue(configure_https.called)

    @patch.object(relations, 'configure_https')
    def test_config_changed_no_openstack_upgrade(self, configure_https):
        self.openstack_upgrade_available.return_value = False
        relations.config_changed()
        self.open_port.assert_called_with(9292)
        self.assertTrue(configure_https.called)

    @patch.object(relations, 'configure_https')
    def test_config_changed_with_openstack_upgrade(self, configure_https):
        self.openstack_upgrade_available.return_value = True
        relations.config_changed()
        self.juju_log.assert_called_with(
            'Upgrading OpenStack release'
        )
        self.assertTrue(self.do_openstack_upgrade.called)
        self.assertTrue(configure_https.called)

    @patch.object(relations, 'CONFIGS')
    def test_cluster_changed(self, configs):
        self.test_config.set('prefer-ipv6', False)
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['cluster']
        configs.write = MagicMock()
        relations.cluster_changed()
        self.assertEquals([call('/etc/glance/glance-api.conf'),
                           call('/etc/haproxy/haproxy.cfg')],
                          configs.write.call_args_list)

    @patch.object(relations, 'relation_set')
    @patch.object(relations, 'CONFIGS')
    def test_cluster_changed_with_ipv6(self, configs, relation_set):
        self.test_config.set('prefer-ipv6', True)
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['cluster']
        configs.write = MagicMock()
        self.get_ipv6_addr.return_value = '2001:db8:1::1'
        self.relation_ids.return_value = ['cluster:0']
        relations.cluster_changed()
        self.assertEquals([call('/etc/glance/glance-api.conf'),
                           call('/etc/haproxy/haproxy.cfg')],
                          configs.write.call_args_list)

    @patch.object(relations, 'CONFIGS')
    def test_upgrade_charm(self, configs):
        self.filter_installed_packages.return_value = ['test']
        relations.upgrade_charm()
        self.apt_install.assert_called_with(['test'], fatal=True)
        self.assertTrue(configs.write_all.called)

    def test_ha_relation_joined(self):
        self.get_hacluster_config.return_value = {
            'ha-bindiface': 'em0',
            'ha-mcastport': '8080',
            'vip': '10.10.10.10',
        }
        self.get_iface_for_address.return_value = 'eth1'
        self.get_netmask_for_address.return_value = '255.255.0.0'
        relations.ha_relation_joined()
        args = {
            'corosync_bindiface': 'em0',
            'corosync_mcastport': '8080',
            'init_services': {'res_glance_haproxy': 'haproxy'},
            'resources': {'res_glance_eth1_vip': 'ocf:heartbeat:IPaddr2',
                          'res_glance_haproxy': 'lsb:haproxy'},
            'resource_params': {
                'res_glance_eth1_vip': 'params ip="10.10.10.10"'
                ' cidr_netmask="255.255.0.0" nic="eth1"',
                'res_glance_haproxy': 'op monitor interval="5s"'},
            'clones': {'cl_glance_haproxy': 'res_glance_haproxy'}
        }
        self.relation_set.assert_has_calls([
            call(groups={'grp_glance_vips': 'res_glance_eth1_vip'}),
            call(**args),
        ])

    def test_ha_relation_joined_with_ipv6(self):
        self.test_config.set('prefer-ipv6', True)
        self.get_hacluster_config.return_value = {
            'ha-bindiface': 'em0',
            'ha-mcastport': '8080',
            'vip': '2001:db8:1::1',
        }
        self.get_iface_for_address.return_value = 'eth1'
        self.get_netmask_for_address.return_value = '64'
        relations.ha_relation_joined()
        args = {
            'corosync_bindiface': 'em0',
            'corosync_mcastport': '8080',
            'init_services': {'res_glance_haproxy': 'haproxy'},
            'resources': {'res_glance_eth1_vip': 'ocf:heartbeat:IPv6addr',
                          'res_glance_haproxy': 'lsb:haproxy'},
            'resource_params': {
                'res_glance_eth1_vip': 'params ipv6addr="2001:db8:1::1"'
                ' cidr_netmask="64" nic="eth1"',
                'res_glance_haproxy': 'op monitor interval="5s"'},
            'clones': {'cl_glance_haproxy': 'res_glance_haproxy'}
        }
        self.relation_set.assert_called_with(**args)

    def test_ha_relation_changed_not_clustered(self):
        self.relation_get.return_value = False
        relations.ha_relation_changed()
        self.juju_log.assert_called_with(
            'ha_changed: hacluster subordinate is not fully clustered.'
        )

    @patch.object(relations, 'keystone_joined')
    @patch.object(relations, 'CONFIGS')
    def test_configure_https_enable_with_identity_service(
            self, configs, keystone_joined):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['https']
        configs.write = MagicMock()
        self.relation_ids.return_value = ['identity-service:0']
        relations.configure_https()
        cmd = ['a2ensite', 'openstack_https_frontend']
        self.check_call.assert_called_with(cmd)
        keystone_joined.assert_called_with(relation_id='identity-service:0')

    @patch.object(relations, 'keystone_joined')
    @patch.object(relations, 'CONFIGS')
    def test_configure_https_disable_with_keystone_joined(
            self, configs, keystone_joined):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['']
        configs.write = MagicMock()
        self.relation_ids.return_value = ['identity-service:0']
        relations.configure_https()
        cmd = ['a2dissite', 'openstack_https_frontend']
        self.check_call.assert_called_with(cmd)
        keystone_joined.assert_called_with(relation_id='identity-service:0')

    @patch.object(relations, 'image_service_joined')
    @patch.object(relations, 'CONFIGS')
    def test_configure_https_enable_with_image_service(
            self, configs, image_service_joined):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['https']
        configs.write = MagicMock()
        self.relation_ids.return_value = ['image-service:0']
        relations.configure_https()
        cmd = ['a2ensite', 'openstack_https_frontend']
        self.check_call.assert_called_with(cmd)
        image_service_joined.assert_called_with(relation_id='image-service:0')

    @patch.object(relations, 'image_service_joined')
    @patch.object(relations, 'CONFIGS')
    def test_configure_https_disable_with_image_service(
            self, configs, image_service_joined):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['']
        configs.write = MagicMock()
        self.relation_ids.return_value = ['image-service:0']
        relations.configure_https()
        cmd = ['a2dissite', 'openstack_https_frontend']
        self.check_call.assert_called_with(cmd)
        image_service_joined.assert_called_with(relation_id='image-service:0')

    def test_amqp_joined(self):
        relations.amqp_joined()
        self.relation_set.assert_called_with(
            username='glance',
            vhost='openstack')

    @patch.object(relations, 'CONFIGS')
    def test_amqp_changed_missing_relation_data(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = []
        relations.amqp_changed()
        self.juju_log.assert_called()

    @patch.object(relations, 'CONFIGS')
    def test_amqp_changed_relation_data(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['amqp']
        configs.write = MagicMock()
        relations.amqp_changed()
        self.assertEquals([call('/etc/glance/glance-api.conf')],
                          configs.write.call_args_list)
        self.assertFalse(self.juju_log.called)

    @patch.object(relations, 'image_service_joined')
    @patch.object(relations, 'keystone_joined')
    def test_ha_relation_changed(self, ks_joined, image_joined):
        self.relation_get.return_value = True
        self.relation_ids.side_effect = [['identity:0'], ['image:1']]
        relations.ha_relation_changed()
        ks_joined.assert_called_with('identity:0')
        image_joined.assert_called_with('image:1')

    @patch.object(relations, 'CONFIGS')
    def test_relation_broken(self, configs):
        relations.relation_broken()
        self.assertTrue(configs.write_all.called)
