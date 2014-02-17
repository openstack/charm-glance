from mock import patch
import glance_contexts as contexts

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

    @patch('charmhelpers.contrib.openstack.context.determine_apache_port')
    @patch('charmhelpers.contrib.openstack.context.determine_api_port')
    @patch('charmhelpers.contrib.openstack.context.unit_get')
    @patch('charmhelpers.contrib.openstack.context.https')
    def test_apache_ssl_context_service_enabled(self, mock_https,
                                                mock_unit_get,
                                                mock_determine_api_port,
                                                mock_determine_apache_port):
        mock_https.return_value = True
        mock_unit_get.return_value = '1.2.3.4'
        mock_determine_api_port.return_value = '12'
        mock_determine_apache_port.return_value = '34'

        ctxt = contexts.ApacheSSLContext()
        with patch.object(ctxt, 'enable_modules') as mock_enable_modules:
            with patch.object(ctxt, 'configure_cert') as mock_configure_cert:
                self.assertEquals(ctxt(), {'endpoints': [(34, 12)],
                                           'private_address': '1.2.3.4',
                                           'namespace': 'glance'})
                self.assertTrue(mock_https.called)
                mock_unit_get.assert_called_with('private-address')
