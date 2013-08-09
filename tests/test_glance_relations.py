from mock import call, patch, MagicMock

from tests.test_utils import CharmTestCase

import hooks.glance_utils as utils

_reg = utils.register_configs
_map = utils.restart_map

utils.register_configs = MagicMock()
utils.restart_map = MagicMock()

import hooks.glance_relations as relations

utils.register_configs = _reg
utils.restart_map = _map

TO_PATCH = [
    # charmhelpers.core.hookenv
    'Hooks',
    'config',
    'juju_log',
    'relation_ids',
    'relation_set',
    'service_name',
    'unit_get',
    # charmhelpers.core.host
    'apt_install',
    'apt_update',
    'restart_on_change',
    'service_stop',
    #charmhelpers.contrib.openstack.utils
    'configure_installation_source',
    'get_os_codename_package',
    # charmhelpers.contrib.hahelpers.cluster_utils
    'eligible_leader',
    'is_clustered',
    # glance_utils
    'restart_map',
    'register_configs',
    'do_openstack_upgrade',
    'migrate_database',
    # glance_relations
    'configure_https',
    # other
    'getstatusoutput',
    'check_call',
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
        self.assertTrue(self.apt_update.called)
        self.apt_install.assert_called_with(['apache2', 'glance', 'python-mysqldb',
                                             'python-swift', 'python-keystone',
                                             'uuid', 'haproxy'])

    def test_db_joined(self):
        self.unit_get.return_value = 'glance.foohost.com'
        relations.db_joined()
        self.relation_set.assert_called_with(database='glance', username='glance',
                                             hostname='glance.foohost.com')
        self.unit_get.assert_called_with('private-address')

    @patch.object(relations, 'CONFIGS')
    def test_db_changed_missing_relation_data(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = []
        relations.db_changed()
        self.juju_log.assert_called_with(
            'shared-db relation incomplete. Peer not ready?'
        )

    def _shared_db_test(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['shared-db']
        configs.write = MagicMock()
        relations.db_changed()

    @patch.object(relations, 'CONFIGS')
    def test_db_changed_no_essex(self, configs):
        self._shared_db_test(configs)
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
        self.getstatusoutput.return_value = (0, "version")
        self._shared_db_test(configs)
        self.assertEquals([call('/etc/glance/glance-registry.conf')],
                           configs.write.call_args_list)
        self.juju_log.assert_called_with(
            'Cluster leader, performing db sync'
        )
        self.migrate_database.assert_called_with()

    @patch.object(relations, 'CONFIGS')
    def test_db_changed_with_essex_setting_version_control(self, configs):
        self.get_os_codename_package.return_value = "essex"
        self.getstatusoutput.return_value = (1, "version")
        self._shared_db_test(configs)
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
    def test_image_service_joined(self, configs):
        # look at compute joined
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['https']
        configs.write = MagicMock()
        relations.image_service_joined()
        self.assertTrue(self.eligible_leader.called)
