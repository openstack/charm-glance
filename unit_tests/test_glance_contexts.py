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
    'os_release',
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

    def test_cinder_not_related(self):
        self.relation_ids.return_value = []
        self.assertEquals(contexts.CinderStoreContext()(), {})

    def test_cinder_related(self):
        self.relation_ids.return_value = ['cinder-volume-service:0']
        self.assertEquals(contexts.CinderStoreContext()(),
                          {'cinder_store': True})

    def test_cinder_related_via_subordinate(self):
        self.relation_ids.return_value = ['cinder-backend:0']
        self.assertEquals(contexts.CinderStoreContext()(),
                          {'cinder_store': True})

    def test_ceph_not_related(self):
        self.is_relation_made.return_value = False
        self.assertEquals(contexts.CephGlanceContext()(), {})

    def test_ceph_related(self):
        self.is_relation_made.return_value = True
        service = 'glance'
        self.service_name.return_value = service
        self.config.return_value = True
        self.assertEquals(
            contexts.CephGlanceContext()(),
            {'rbd_pool': service,
             'rbd_user': service,
             'expose_image_locations': True})
        self.config.assert_called_with('expose-image-locations')

    def test_multistore_below_mitaka(self):
        self.os_release.return_value = 'liberty'
        self.relation_ids.return_value = ['random_rid']
        self.assertEquals(contexts.MultiStoreContext()(),
                          {'known_stores': "glance.store.filesystem.Store,"
                                           "glance.store.http.Store,"
                                           "glance.store.rbd.Store,"
                                           "glance.store.swift.Store"})

    def test_multistore_for_mitaka_and_upper(self):
        self.os_release.return_value = 'mitaka'
        self.relation_ids.return_value = ['random_rid']
        self.assertEquals(contexts.MultiStoreContext()(),
                          {'known_stores': "glance.store.filesystem.Store,"
                                           "glance.store.http.Store,"
                                           "glance.store.rbd.Store,"
                                           "glance.store.swift.Store,"
                                           "glance.store.cinder.Store"})

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
