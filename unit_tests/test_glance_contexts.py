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

import glance_contexts as contexts
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
    'juju_log',
]


class TestGlanceContexts(CharmTestCase):

    def setUp(self):
        super(TestGlanceContexts, self).setUp(contexts, TO_PATCH)
        from charmhelpers.core.hookenv import cache
        self.cache = cache
        cache.clear()

    def test_glance_context(self):
        config = {
            'disk-formats': 'dfmt1',
            'container-formats': '',
            'filesystem-store-datadir': "/var/lib/glance/images/",
            'image-size-cap': ''}
        self.config.side_effect = lambda x: config[x]
        self.assertEqual(contexts.GlanceContext()(), {
            'disk_formats': 'dfmt1',
            'filesystem_store_datadir': "/var/lib/glance/images/"})

    def test_glance_context_container_fmt(self):
        config = {
            'disk-formats': 'dfmt1',
            'container-formats': 'cmft1',
            'filesystem-store-datadir': "/var/lib/glance/images/",
            'image-size-cap': ''}
        self.config.side_effect = lambda x: config[x]
        self.assertEqual(contexts.GlanceContext()(),
                         {'disk_formats': 'dfmt1',
                          'filesystem_store_datadir':
                             "/var/lib/glance/images/",
                          'container_formats': 'cmft1'})

    def test_glance_context_image_size_cap(self):
        config = {
            'disk-formats': 'dfmt1',
            'container-formats': 'cmft1',
            'filesystem-store-datadir': "/var/lib/glance/images/",
            'image-size-cap': '1TB'}
        self.config.side_effect = lambda x: config[x]
        self.assertEqual(contexts.GlanceContext()(),
                         {'disk_formats': 'dfmt1',
                          'container_formats': 'cmft1',
                          'filesystem_store_datadir':
                             "/var/lib/glance/images/",
                          'image_size_cap': 1099511627776})

    def test_swift_not_related(self):
        self.relation_ids.return_value = []
        self.assertEqual(contexts.ObjectStoreContext()(), {})

    def test_swift_related(self):
        self.relation_ids.return_value = ['object-store:0']
        self.assertEqual(contexts.ObjectStoreContext()(),
                         {'swift_store': True})

    def test_cinder_not_related(self):
        self.relation_ids.return_value = []
        self.assertEqual(contexts.CinderStoreContext()(), {})

    def test_cinder_related(self):
        self.relation_ids.return_value = ['cinder-volume-service:0']
        self.assertEqual(contexts.CinderStoreContext()(),
                         {'cinder_store': True})

    def test_cinder_related_via_subordinate(self):
        self.relation_ids.return_value = ['cinder-backend:0']
        self.assertEqual(contexts.CinderStoreContext()(),
                         {'cinder_store': True})

    def test_ceph_not_related(self):
        self.is_relation_made.return_value = False
        self.assertEqual(contexts.CephGlanceContext()(), {})

    def test_ceph_related(self):
        self.is_relation_made.return_value = True
        service = 'glance'
        self.service_name.return_value = service
        conf_dict = {
            'rbd-pool-name': None,
            'expose-image-locations': True,
            'pool-type': 'replicated',
        }
        self.config.side_effect = lambda x: conf_dict.get(x)
        self.assertEqual(
            contexts.CephGlanceContext()(),
            {'rbd_pool': service,
             'rbd_user': service,
             'expose_image_locations': True})
        self.config.assert_called_with('expose-image-locations')
        # Check user supplied pool name:
        conf_dict = {
            'rbd-pool-name': 'mypoolname',
            'expose-image-locations': True,
            'pool-type': 'replicated',
        }
        self.assertEqual(
            contexts.CephGlanceContext()(),
            {'rbd_pool': 'mypoolname',
             'rbd_user': service,
             'expose_image_locations': True})
        # Check erasure-coded pool type
        conf_dict = {
            'rbd-pool-name': None,
            'expose-image-locations': True,
            'pool-type': 'erasure-coded',
            'ec-rbd-metadata-pool': None,
        }
        self.assertEqual(
            contexts.CephGlanceContext()(),
            {'rbd_pool': "{}-metadata".format(service),
             'rbd_user': service,
             'expose_image_locations': True})
        # Ensure rbd-pool-name used for metadata pool name
        conf_dict = {
            'rbd-pool-name': 'foobar',
            'expose-image-locations': True,
            'pool-type': 'erasure-coded',
            'ec-rbd-metadata-pool': None,
        }
        self.assertEqual(
            contexts.CephGlanceContext()(),
            {'rbd_pool': "foobar-metadata",
             'rbd_user': service,
             'expose_image_locations': True})
        # Ensure ec-rbd-metadata-pool overrides everything
        conf_dict = {
            'rbd-pool-name': 'foobar',
            'expose-image-locations': True,
            'pool-type': 'erasure-coded',
            'ec-rbd-metadata-pool': 'another-metadata',
        }
        self.assertEqual(
            contexts.CephGlanceContext()(),
            {'rbd_pool': "another-metadata",
             'rbd_user': service,
             'expose_image_locations': True})

    def test_external_s3_not_configured(self):
        config = {
            's3-store-host': '',
            's3-store-access-key': '',
            's3-store-secret-key': '',
            's3-store-bucket': ''}
        self.config.side_effect = lambda x: config[x]
        self.assertEqual(contexts.ExternalS3Context()(), {})

    def test_external_s3_partially_configured(self):
        config = {}
        self.config.side_effect = lambda x: config[x]
        config = {
            's3-store-host': 'host',
            's3-store-access-key': '',
            's3-store-secret-key': '',
            's3-store-bucket': ''}
        self.assertEqual(contexts.ExternalS3Context()(), {})
        config = {
            's3-store-host': '',
            's3-store-access-key': 'key',
            's3-store-secret-key': '',
            's3-store-bucket': ''}
        self.assertEqual(contexts.ExternalS3Context()(), {})
        config = {
            's3-store-host': '',
            's3-store-access-key': '',
            's3-store-secret-key': 'key',
            's3-store-bucket': ''}
        self.assertEqual(contexts.ExternalS3Context()(), {})
        config = {
            's3-store-host': '',
            's3-store-access-key': '',
            's3-store-secret-key': '',
            's3-store-bucket': 'bucket'}
        self.assertEqual(contexts.ExternalS3Context()(), {})

    def test_external_s3_configured(self):
        host_name = 'http://my-object-storage.example.com:8080'
        access_key = 'my-access-key'
        secret_key = 'my-secret-key'
        bucket = 'my-bucket'
        config = {
            'expose-image-locations': True,
            's3-store-host': host_name,
            's3-store-access-key': access_key,
            's3-store-secret-key': secret_key,
            's3-store-bucket': bucket}
        self.config.side_effect = lambda x: config[x]
        expected_ctx = {
            'expose_image_locations': False,
            's3_store_host': host_name,
            's3_store_access_key': access_key,
            's3_store_secret_key': secret_key,
            's3_store_bucket': bucket
        }

        self.os_release.return_value = 'train'
        self.assertEqual(contexts.ExternalS3Context()(), {})

        self.os_release.return_value = 'ussuri'
        self.assertEqual(contexts.ExternalS3Context()(), expected_ctx)

    def test_multistore_below_mitaka(self):
        self.os_release.return_value = 'liberty'
        self.relation_ids.return_value = ['random_rid']
        self.assertEqual(contexts.MultiStoreContext()(),
                         {'known_stores': "glance.store.filesystem.Store,"
                                          "glance.store.http.Store,"
                                          "glance.store.rbd.Store,"
                                          "glance.store.swift.Store"})

    def test_multistore_for_mitaka_and_upper(self):
        self.os_release.return_value = 'mitaka'
        self.relation_ids.return_value = ['random_rid']
        self.assertEqual(contexts.MultiStoreContext()(),
                         {'known_stores': "glance.store.cinder.Store,"
                                          "glance.store.filesystem.Store,"
                                          "glance.store.http.Store,"
                                          "glance.store.rbd.Store,"
                                          "glance.store.swift.Store"})

    def test_multistore_defaults(self):
        self.relation_ids.return_value = []
        self.assertEqual(contexts.MultiStoreContext()(),
                         {'known_stores': "glance.store.filesystem.Store,"
                                          "glance.store.http.Store"})

    def test_multi_backend_no_relations_no_data_dir(self):
        self.relation_ids.return_value = []
        self.is_relation_made.return_value = False
        data_dir = ''
        conf_dict = {
            'filesystem-store-datadir': data_dir,
        }
        self.config.side_effect = lambda x: conf_dict.get(x)
        self.assertEqual(
            contexts.MultiBackendContext()(),
            {
                'enabled_backend_configs': {},
                'enabled_backends': None,
                'default_store_backend': None,
            })

    def test_multi_backend_no_relations(self):
        self.relation_ids.return_value = []
        self.is_relation_made.return_value = False
        data_dir = '/some/data/dir'
        conf_dict = {
            'filesystem-store-datadir': data_dir,
        }
        self.config.side_effect = lambda x: conf_dict.get(x)
        self.assertEqual(
            contexts.MultiBackendContext()(),
            {
                'enabled_backend_configs': {
                    'local': {
                        'filesystem_store_datadir': data_dir,
                        'store_description': 'Local filesystem store',
                    }
                },
                'enabled_backends': 'local:file',
                'default_store_backend': 'local',
            })

    def test_multi_backend_with_swift(self):
        # return relation_ids only for swift but not for cinder
        def _relation_ids(*args, **kwargs):
            if args[0] == 'object-store':
                return ["object-store:0"]

            return []

        self.maxDiff = None
        self.relation_ids.side_effect = _relation_ids
        self.is_relation_made.return_value = False
        data_dir = '/some/data/dir'
        conf_dict = {
            'filesystem-store-datadir': data_dir,
        }
        swift_conf = "/etc/glance/glance-swift.conf"
        self.config.side_effect = lambda x: conf_dict.get(x)
        self.assertEqual(
            contexts.MultiBackendContext()(),
            {
                'enabled_backend_configs': {
                    'local': {
                        'filesystem_store_datadir': data_dir,
                        'store_description': 'Local filesystem store',
                    },
                    'swift': {
                        "default_swift_reference": "swift",
                        "swift_store_config_file": swift_conf,
                        "swift_store_create_container_on_put": "true",
                    }
                },
                'enabled_backends': 'local:file, swift:swift',
                'default_store_backend': 'swift',
            })

    def test_multi_backend_with_cinder(self):
        # return relation_ids only for cinder but not for swift
        def _relation_ids(*args, **kwargs):
            if args[0] == 'cinder-volume-service':
                return ["cinder-volume-service:0"]

            return []

        self.maxDiff = None
        self.relation_ids.side_effect = _relation_ids
        self.is_relation_made.return_value = False
        data_dir = '/some/data/dir'
        conf_dict = {
            'filesystem-store-datadir': data_dir,
            'cinder-http-retries': 3,
            'cinder-state-transition-timeout': 30,
        }
        self.config.side_effect = lambda x: conf_dict.get(x)
        self.assertEqual(
            contexts.MultiBackendContext()(),
            {
                'enabled_backend_configs': {
                    'local': {
                        'filesystem_store_datadir': data_dir,
                        'store_description': 'Local filesystem store',
                    },
                    'cinder': {
                        'cinder_http_retries': 3,
                        'cinder_state_transition_timeout': 30,
                    }
                },
                'enabled_backends': 'local:file, cinder:cinder',
                'default_store_backend': 'cinder',
            })

    def test_multi_backend_with_cinder_volume_types_defined(self):
        # return relation_ids only for cinder but not for swift
        def _relation_ids(*args, **kwargs):
            if args[0] == 'cinder-volume-service':
                return ["cinder-volume-service:0"]

            return []

        self.maxDiff = None
        self.relation_ids.side_effect = _relation_ids
        self.is_relation_made.return_value = False
        data_dir = '/some/data/dir'
        conf_dict = {
            'filesystem-store-datadir': data_dir,
            'cinder-volume-types': 'volume-type-test',
            'cinder-http-retries': 3,
            'cinder-state-transition-timeout': 30,
        }
        self.config.side_effect = lambda x: conf_dict.get(x)
        self.assertEqual(
            contexts.MultiBackendContext()(),
            {
                'enabled_backend_configs': {
                    'local': {
                        'filesystem_store_datadir': data_dir,
                        'store_description': 'Local filesystem store',
                    },
                    'volume-type-test': {
                        'cinder_volume_type': 'volume-type-test',
                        'cinder_http_retries': 3,
                        'cinder_state_transition_timeout': 30,
                    }
                },
                'enabled_backends': 'local:file, volume-type-test:cinder',
                'default_store_backend': 'volume-type-test',
            })

    def test_multi_backend_with_ceph_no_swift(self):
        self.maxDiff = None
        self.relation_ids.return_value = []
        self.is_relation_made.return_value = True
        service = 'glance'
        self.service_name.return_value = service
        data_dir = '/some/data/dir'
        conf_dict = {
            'filesystem-store-datadir': data_dir,
            'rbd-pool-name': 'mypool',
        }
        self.config.side_effect = lambda x: conf_dict.get(x)
        self.assertEqual(
            contexts.MultiBackendContext()(),
            {
                'enabled_backend_configs': {
                    'local': {
                        'filesystem_store_datadir': data_dir,
                        'store_description': 'Local filesystem store',
                    },
                    'ceph': {
                        "rbd_store_chunk_size": 8,
                        "rbd_store_pool": 'mypool',
                        "rbd_store_user": service,
                        "rados_connect_timeout": 0,
                        "rbd_store_ceph_conf": "/etc/ceph/ceph.conf",
                    }
                },
                'enabled_backends': 'local:file, ceph:rbd',
                'default_store_backend': 'ceph',
            })

    def test_multi_backend_with_ceph_and_swift(self):
        # return relation_ids only for swift but not for cinder
        def _relation_ids(*args, **kwargs):
            if args[0] == 'object-store':
                return ["object-store:0"]

            return []

        self.maxDiff = None
        self.relation_ids.side_effect = _relation_ids
        self.is_relation_made.return_value = True
        service = 'glance'
        self.service_name.return_value = service
        data_dir = '/some/data/dir'
        swift_conf = "/etc/glance/glance-swift.conf"
        conf_dict = {
            'filesystem-store-datadir': data_dir,
            'rbd-pool-name': 'mypool',
        }
        self.config.side_effect = lambda x: conf_dict.get(x)
        self.assertEqual(
            contexts.MultiBackendContext()(),
            {
                'enabled_backend_configs': {
                    'local': {
                        'filesystem_store_datadir': data_dir,
                        'store_description': 'Local filesystem store',
                    },
                    'ceph': {
                        "rbd_store_chunk_size": 8,
                        "rbd_store_pool": 'mypool',
                        "rbd_store_user": service,
                        "rados_connect_timeout": 0,
                        "rbd_store_ceph_conf": "/etc/ceph/ceph.conf",
                    },
                    'swift': {
                        "default_swift_reference": "swift",
                        "swift_store_config_file": swift_conf,
                        "swift_store_create_container_on_put": "true",
                    }
                },
                'enabled_backends': 'local:file, ceph:rbd, swift:swift',
                'default_store_backend': 'ceph',
            })

    def test_multi_backend_with_ceph_and_cinder(self):
        # return relation_ids only for cinder but not for swift
        def _relation_ids(*args, **kwargs):
            if args[0] == 'cinder-volume-service':
                return ["cinder-volume-service:0"]

            return []

        self.maxDiff = None
        self.relation_ids.side_effect = _relation_ids
        self.is_relation_made.return_value = True
        service = 'glance'
        self.service_name.return_value = service
        data_dir = '/some/data/dir'
        conf_dict = {
            'filesystem-store-datadir': data_dir,
            'rbd-pool-name': 'mypool',
            'cinder-http-retries': 3,
            'cinder-state-transition-timeout': 30,
        }
        self.config.side_effect = lambda x: conf_dict.get(x)
        self.assertEqual(
            contexts.MultiBackendContext()(),
            {
                'enabled_backend_configs': {
                    'local': {
                        'filesystem_store_datadir': data_dir,
                        'store_description': 'Local filesystem store',
                    },
                    'ceph': {
                        "rbd_store_chunk_size": 8,
                        "rbd_store_pool": 'mypool',
                        "rbd_store_user": service,
                        "rados_connect_timeout": 0,
                        "rbd_store_ceph_conf": "/etc/ceph/ceph.conf",
                    },
                    'cinder': {
                        'cinder_http_retries': 3,
                        'cinder_state_transition_timeout': 30,
                    }
                },
                'enabled_backends': 'local:file, ceph:rbd, cinder:cinder',
                'default_store_backend': 'ceph',
            })

    def test_multi_backend_with_external_s3(self):
        self.maxDiff = None
        self.os_release.return_value = 'ussuri'
        self.relation_ids.return_value = []
        self.is_relation_made.return_value = False
        data_dir = '/some/data/dir'
        s3_host = 'http://my-object-storage.example.com:8080'
        s3_access_key = 'my-access-key'
        s3_secret_key = 'my-secret-key'
        s3_bucket = 'my-bucket'
        conf_dict = {
            'expose-image-locations': True,
            'filesystem-store-datadir': data_dir,
            's3-store-host': s3_host,
            's3-store-access-key': s3_access_key,
            's3-store-secret-key': s3_secret_key,
            's3-store-bucket': s3_bucket,
        }
        self.config.side_effect = lambda x: conf_dict.get(x)
        self.assertEqual(
            contexts.MultiBackendContext()(),
            {
                'enabled_backend_configs': {
                    'local': {
                        'filesystem_store_datadir': data_dir,
                        'store_description': 'Local filesystem store',
                    },
                    's3': {
                        "s3_store_host": s3_host,
                        "s3_store_access_key": s3_access_key,
                        "s3_store_secret_key": s3_secret_key,
                        "s3_store_bucket": s3_bucket,
                    }
                },
                'enabled_backends': 'local:file, s3:s3',
                'default_store_backend': 's3',
            })

    @patch('charmhelpers.contrib.openstack.context.relation_ids')
    @patch('charmhelpers.contrib.hahelpers.cluster.config_get')
    @patch('charmhelpers.contrib.openstack.context.https')
    def test_apache_ssl_context_service_enabled(self, mock_https,
                                                mock_config,
                                                mock_relation_ids):
        mock_relation_ids.return_value = []
        mock_config.return_value = 'true'
        mock_https.return_value = True

        ctxt = contexts.ApacheSSLContext()
        ctxt.enable_modules = MagicMock()
        ctxt.configure_cert = MagicMock()
        ctxt.configure_ca = MagicMock()
        ctxt.canonical_names = MagicMock()
        ctxt.get_network_addresses = MagicMock()
        ctxt.get_network_addresses.return_value = [('1.2.3.4', '1.2.3.4')]

        self.assertEqual(ctxt(), {'endpoints': [('1.2.3.4', '1.2.3.4',
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
        self.assertEqual(ctxt(), {'bind_host': '::',
                                  'registry_host': '[::]'})

    @patch('charmhelpers.contrib.openstack.context.config')
    @patch("subprocess.check_output")
    def test_glance_ipv6_context_service_disabled(self, mock_subprocess,
                                                  mock_config):
        self.config.return_value = False
        mock_config.return_value = False
        mock_subprocess.return_value = 'false'
        ctxt = contexts.GlanceIPv6Context()
        self.assertEqual(ctxt(), {'bind_host': '0.0.0.0',
                                  'registry_host': '0.0.0.0'})
