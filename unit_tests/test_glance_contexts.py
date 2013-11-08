from mock import patch
import glance_contexts as contexts

from test_utils import (
    CharmTestCase
)

TO_PATCH = [
    'relation_ids',
    'is_relation_made',
    'service_name',
    'determine_haproxy_port',
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

    def test_haproxy_configuration(self):
        self.determine_haproxy_port.return_value = 9292
        self.determine_api_port.return_value = 9282
        self.assertEquals(
            contexts.HAProxyContext()(),
            {'service_ports': {'glance_api': [9292, 9282]},
             'bind_port': 9282})

    @patch('charmhelpers.contrib.openstack.context.https')
    def test_apache_ssl_context_service_enabled(self,
                                                https):
        https.return_value = False
        self.assertEquals(contexts.ApacheSSLContext()(), {})
