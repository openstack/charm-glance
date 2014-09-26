import glance_contexts as contexts
from mock import patch

from test_utils import (
    CharmTestCase
)

TO_PATCH = [
    'relation_ids',
    'is_relation_made',
    'service_name',
    'determine_apache_port',
    'determine_api_port',
]


class TestGlanceContexts(CharmTestCase):

    def setUp(self):
        super(TestGlanceContexts, self).setUp(contexts, TO_PATCH)

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

    mod_ch_context = 'charmhelpers.contrib.openstack.context'

    @patch('%s.ApacheSSLContext.canonical_names' % (mod_ch_context))
    @patch('%s.ApacheSSLContext.configure_ca' % (mod_ch_context))
    @patch('%s.config' % (mod_ch_context))
    @patch('%s.is_clustered' % (mod_ch_context))
    @patch('%s.determine_apache_port' % (mod_ch_context))
    @patch('%s.determine_api_port' % (mod_ch_context))
    @patch('%s.unit_get' % (mod_ch_context))
    @patch('%s.https' % (mod_ch_context))
    def test_apache_ssl_context_service_enabled(self, mock_https,
                                                mock_unit_get,
                                                mock_determine_api_port,
                                                mock_determine_apache_port,
                                                mock_is_clustered,
                                                mock_hookenv,
                                                mock_configure_ca,
                                                mock_cfg_canonical_names):
        mock_cfg_canonical_names.return_value = ['name.a']
        mock_https.return_value = True
        mock_unit_get.return_value = '1.2.3.4'
        mock_determine_api_port.return_value = '12'
        mock_determine_apache_port.return_value = '34'
        mock_is_clustered.return_value = False

        ctxt = contexts.ApacheSSLContext()
        with patch.object(ctxt, 'enable_modules') as mock_enable_modules:
            with patch.object(ctxt, 'configure_cert') as mock_configure_cert:
                self.assertEquals(ctxt(), {'endpoints': [('1.2.3.4',
                                                          '1.2.3.4',
                                                          34, 12)],
                                           'ext_ports': [34],
                                           'namespace': 'glance'})
                self.assertTrue(mock_https.called)
                mock_unit_get.assert_called_with('private-address')
                self.assertTrue(mock_enable_modules.called)
                self.assertTrue(mock_configure_cert.called)

    @patch('charmhelpers.contrib.openstack.context.config')
    @patch('glance_contexts.config')
    def test_glance_ipv6_context_service_enabled(self, mock_config,
                                                 mock_context_config):
        mock_config.return_value = True
        mock_context_config.return_value = True
        ctxt = contexts.GlanceIPv6Context()
        self.assertEquals(ctxt(), {'bind_host': '::',
                                   'registry_host': '[::]'})

    @patch('charmhelpers.contrib.openstack.context.config')
    @patch('glance_contexts.config')
    def test_glance_ipv6_context_service_disabled(self, mock_config,
                                                  mock_context_config):
        mock_config.return_value = False
        mock_context_config.return_value = False
        ctxt = contexts.GlanceIPv6Context()
        self.assertEquals(ctxt(), {'bind_host': '0.0.0.0',
                                   'registry_host': '0.0.0.0'})
