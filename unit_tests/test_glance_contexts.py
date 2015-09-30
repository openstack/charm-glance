from mock import patch, MagicMock

from hooks import glance_contexts as contexts


from test_utils import (
    CharmTestCase
)

TO_PATCH = [
    "config",
    'relation_ids',
    'is_relation_made',
    'service_name',
    'determine_apache_port',
    'determine_api_port',
]


class TestGlanceContexts(CharmTestCase):

    def setUp(self):
        super(TestGlanceContexts, self).setUp(contexts, TO_PATCH)
        from charmhelpers.core.hookenv import cache
        self.cache = cache
        cache.clear()

    def test_swift_not_related(self):
        self.relation_ids.return_value = []
        self.assertEquals(contexts.ObjectStoreContext()(), {})

    def test_swift_related(self):
        self.relation_ids.return_value = ['object-store:0']
        self.assertEquals(contexts.ObjectStoreContext()(),
                          {'swift_store': True})

    def test_ceph_not_related(self):
        self.is_relation_made.return_value = False
        self.assertEquals(contexts.CephGlanceContext()(), {})

    def test_ceph_related(self):
        self.is_relation_made.return_value = True
        service = 'glance'
        self.service_name.return_value = service
        self.assertEquals(
            contexts.CephGlanceContext()(),
            {'rbd_pool': service,
             'rbd_user': service})

    def test_multistore(self):
        self.relation_ids.return_value = ['random_rid']
        self.assertEquals(contexts.MultiStoreContext()(),
                          {'known_stores': "glance.store.filesystem.Store,"
                                           "glance.store.http.Store,"
                                           "glance.store.rbd.Store,"
                                           "glance.store.swift.Store"})

    def test_multistore_defaults(self):
        self.relation_ids.return_value = []
        self.assertEquals(contexts.MultiStoreContext()(),
                          {'known_stores': "glance.store.filesystem.Store,"
                                           "glance.store.http.Store"})

    @patch('charmhelpers.contrib.hahelpers.cluster.config_get')
    @patch('charmhelpers.contrib.openstack.context.https')
    def test_apache_ssl_context_service_enabled(self, mock_https,
                                                mock_config):
        mock_config.return_value = 'true'
        mock_https.return_value = True

        ctxt = contexts.ApacheSSLContext()
        ctxt.enable_modules = MagicMock()
        ctxt.configure_cert = MagicMock()
        ctxt.configure_ca = MagicMock()
        ctxt.canonical_names = MagicMock()
        ctxt.get_network_addresses = MagicMock()
        ctxt.get_network_addresses.return_value = [('1.2.3.4', '1.2.3.4')]

        self.assertEquals(ctxt(), {'endpoints': [('1.2.3.4', '1.2.3.4',
                                                  9282, 9272)],
                                   'ext_ports': [9282],
                                   'namespace': 'glance'})

    @patch('charmhelpers.contrib.openstack.context.config')
    @patch("subprocess.check_output")
    def test_glance_ipv6_context_service_enabled(self, mock_subprocess,
                                                 mock_config):
        self.config.return_value = True
        mock_config.return_value = True
        mock_subprocess.return_value = 'true'
        ctxt = contexts.GlanceIPv6Context()
        self.assertEquals(ctxt(), {'bind_host': '::',
                                   'registry_host': '[::]'})

    @patch('charmhelpers.contrib.openstack.context.config')
    @patch("subprocess.check_output")
    def test_glance_ipv6_context_service_disabled(self, mock_subprocess,
                                                  mock_config):
        self.config.return_value = False
        mock_config.return_value = False
        mock_subprocess.return_value = 'false'
        ctxt = contexts.GlanceIPv6Context()
        self.assertEquals(ctxt(), {'bind_host': '0.0.0.0',
                                   'registry_host': '0.0.0.0'})
