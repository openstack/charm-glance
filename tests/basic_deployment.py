#!/usr/bin/env python
#
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

"""
Basic glance amulet functional tests.
"""

import amulet
import os
import yaml

from charmhelpers.contrib.openstack.amulet.deployment import (
    OpenStackAmuletDeployment
)

from charmhelpers.contrib.openstack.amulet.utils import (
    OpenStackAmuletUtils,
    DEBUG,
    # ERROR
)

# Use DEBUG to turn on debug logging
u = OpenStackAmuletUtils(DEBUG)


class GlanceBasicDeployment(OpenStackAmuletDeployment):
    """Amulet tests on a basic file-backed glance deployment.  Verify
    relations, service status, endpoint service catalog, create and
    delete new image."""

    SERVICES = ('apache2', 'haproxy', 'glance-api', 'glance-registry')

    def __init__(self, series=None, openstack=None, source=None, git=False,
                 stable=False):
        """Deploy the entire test environment."""
        super(GlanceBasicDeployment, self).__init__(series, openstack,
                                                    source, stable)
        self.git = git
        self._add_services()
        self._add_relations()
        self._configure_services()
        self._deploy()

        u.log.info('Waiting on extended status checks...')
        exclude_services = []
        self._auto_wait_for_status(exclude_services=exclude_services)

        self.d.sentry.wait()
        self._initialize_tests()

    def _assert_services(self, should_run):
        u.get_unit_process_ids(
            {self.glance_sentry: self.SERVICES},
            expect_success=should_run)

    def _add_services(self):
        """Add services

           Add the services that we're testing, where glance is local,
           and the rest of the service are from lp branches that are
           compatible with the local charm (e.g. stable or next).
           """
        this_service = {'name': 'glance'}
        other_services = [
            {'name': 'percona-cluster', 'constraints': {'mem': '3072M'}},
            {'name': 'rabbitmq-server'},
            {'name': 'keystone'},
        ]
        super(GlanceBasicDeployment, self)._add_services(this_service,
                                                         other_services)

    def _add_relations(self):
        """Add relations for the services."""
        relations = {'glance:identity-service': 'keystone:identity-service',
                     'glance:shared-db': 'percona-cluster:shared-db',
                     'keystone:shared-db': 'percona-cluster:shared-db',
                     'glance:amqp': 'rabbitmq-server:amqp'}
        super(GlanceBasicDeployment, self)._add_relations(relations)

    def _configure_services(self):
        """Configure all of the services."""
        glance_config = {}
        if self.git:
            amulet_http_proxy = os.environ.get('AMULET_HTTP_PROXY')

            reqs_repo = 'git://github.com/openstack/requirements'
            glance_repo = 'git://github.com/openstack/glance'
            if self._get_openstack_release() == self.trusty_icehouse:
                reqs_repo = 'git://github.com/coreycb/requirements'
                glance_repo = 'git://github.com/coreycb/glance'

            branch = 'stable/' + self._get_openstack_release_string()

            openstack_origin_git = {
                'repositories': [
                    {'name': 'requirements',
                     'repository': reqs_repo,
                     'branch': branch},
                    {'name': 'glance',
                     'repository': glance_repo,
                     'branch': branch},
                ],
                'directory': '/mnt/openstack-git',
                'http_proxy': amulet_http_proxy,
                'https_proxy': amulet_http_proxy,
            }
            glance_config['openstack-origin-git'] = \
                yaml.dump(openstack_origin_git)

        keystone_config = {
            'admin-password': 'openstack',
            'admin-token': 'ubuntutesting',
        }
        pxc_config = {
            'dataset-size': '25%',
            'max-connections': 1000,
            'root-password': 'ChangeMe123',
            'sst-password': 'ChangeMe123',
        }
        configs = {
            'glance': glance_config,
            'keystone': keystone_config,
            'percona-cluster': pxc_config,
        }
        super(GlanceBasicDeployment, self)._configure_services(configs)

    def _initialize_tests(self):
        """Perform final initialization before tests get run."""
        # Access the sentries for inspecting service units
        self.pxc_sentry = self.d.sentry['percona-cluster'][0]
        self.glance_sentry = self.d.sentry['glance'][0]
        self.keystone_sentry = self.d.sentry['keystone'][0]
        self.rabbitmq_sentry = self.d.sentry['rabbitmq-server'][0]
        u.log.debug('openstack release val: {}'.format(
            self._get_openstack_release()))
        u.log.debug('openstack release str: {}'.format(
            self._get_openstack_release_string()))

        # Authenticate admin with keystone
        self.keystone = u.authenticate_keystone_admin(self.keystone_sentry,
                                                      user='admin',
                                                      password='openstack',
                                                      tenant='admin')
        # Authenticate admin with glance endpoint
        self.glance = u.authenticate_glance_admin(self.keystone)

    def test_100_services(self):
        """Verify that the expected services are running on the
           corresponding service units."""
        services = {
            self.keystone_sentry: ['keystone'],
            self.glance_sentry: ['glance-api', 'glance-registry'],
            self.rabbitmq_sentry: ['rabbitmq-server']
        }
        if self._get_openstack_release() >= self.trusty_liberty:
            services[self.keystone_sentry] = ['apache2']
        ret = u.validate_services_by_name(services)
        if ret:
            amulet.raise_status(amulet.FAIL, msg=ret)

    def test_102_service_catalog(self):
        """Verify that the service catalog endpoint data is valid."""
        u.log.debug('Checking keystone service catalog...')
        endpoint_check = {
            'adminURL': u.valid_url,
            'id': u.not_null,
            'region': 'RegionOne',
            'publicURL': u.valid_url,
            'internalURL': u.valid_url
        }
        expected = {
            'image': [endpoint_check],
            'identity': [endpoint_check]
        }
        actual = self.keystone.service_catalog.get_endpoints()

        ret = u.validate_svc_catalog_endpoint_data(expected, actual)
        if ret:
            amulet.raise_status(amulet.FAIL, msg=ret)

    def test_104_glance_endpoint(self):
        """Verify the glance endpoint data."""
        u.log.debug('Checking glance api endpoint data...')
        endpoints = self.keystone.endpoints.list()
        admin_port = internal_port = public_port = '9292'
        expected = {
            'id': u.not_null,
            'region': 'RegionOne',
            'adminurl': u.valid_url,
            'internalurl': u.valid_url,
            'publicurl': u.valid_url,
            'service_id': u.not_null
        }
        ret = u.validate_endpoint_data(endpoints, admin_port, internal_port,
                                       public_port, expected)

        if ret:
            amulet.raise_status(amulet.FAIL,
                                msg='glance endpoint: {}'.format(ret))

    def test_106_keystone_endpoint(self):
        """Verify the keystone endpoint data."""
        u.log.debug('Checking keystone api endpoint data...')
        endpoints = self.keystone.endpoints.list()
        admin_port = '35357'
        internal_port = public_port = '5000'
        expected = {
            'id': u.not_null,
            'region': 'RegionOne',
            'adminurl': u.valid_url,
            'internalurl': u.valid_url,
            'publicurl': u.valid_url,
            'service_id': u.not_null
        }
        ret = u.validate_endpoint_data(endpoints, admin_port, internal_port,
                                       public_port, expected)
        if ret:
            amulet.raise_status(amulet.FAIL,
                                msg='keystone endpoint: {}'.format(ret))

    def test_110_users(self):
        """Verify expected users."""
        u.log.debug('Checking keystone users...')
        expected = [
            {'name': 'glance',
             'enabled': True,
             'tenantId': u.not_null,
             'id': u.not_null,
             'email': 'juju@localhost'},
            {'name': 'admin',
             'enabled': True,
             'tenantId': u.not_null,
             'id': u.not_null,
             'email': 'juju@localhost'}
        ]
        actual = self.keystone.users.list()
        ret = u.validate_user_data(expected, actual)
        if ret:
            amulet.raise_status(amulet.FAIL, msg=ret)

    def test_115_memcache(self):
        u.validate_memcache(self.glance_sentry,
                            '/etc/glance/glance-api.conf',
                            self._get_openstack_release(),
                            earliest_release=self.trusty_mitaka)
        u.validate_memcache(self.glance_sentry,
                            '/etc/glance/glance-registry.conf',
                            self._get_openstack_release(),
                            earliest_release=self.trusty_mitaka)

    def test_200_mysql_glance_db_relation(self):
        """Verify the mysql:glance shared-db relation data"""
        u.log.debug('Checking mysql to glance shared-db relation data...')
        unit = self.pxc_sentry
        relation = ['shared-db', 'glance:shared-db']
        expected = {
            'private-address': u.valid_ip,
            'db_host': u.valid_ip
        }
        ret = u.validate_relation_data(unit, relation, expected)
        if ret:
            message = u.relation_error('mysql shared-db', ret)
            amulet.raise_status(amulet.FAIL, msg=message)

    def test_201_glance_mysql_db_relation(self):
        """Verify the glance:mysql shared-db relation data"""
        u.log.debug('Checking glance to mysql shared-db relation data...')
        unit = self.glance_sentry
        relation = ['shared-db', 'percona-cluster:shared-db']
        expected = {
            'private-address': u.valid_ip,
            'hostname': u.valid_ip,
            'username': 'glance',
            'database': 'glance'
        }
        ret = u.validate_relation_data(unit, relation, expected)
        if ret:
            message = u.relation_error('glance shared-db', ret)
            amulet.raise_status(amulet.FAIL, msg=message)

    def test_202_keystone_glance_id_relation(self):
        """Verify the keystone:glance identity-service relation data"""
        u.log.debug('Checking keystone to glance id relation data...')
        unit = self.keystone_sentry
        relation = ['identity-service',
                    'glance:identity-service']
        expected = {
            'service_protocol': 'http',
            'service_tenant': 'services',
            'admin_token': 'ubuntutesting',
            'service_password': u.not_null,
            'service_port': '5000',
            'auth_port': '35357',
            'auth_protocol': 'http',
            'private-address': u.valid_ip,
            'auth_host': u.valid_ip,
            'service_username': 'glance',
            'service_tenant_id': u.not_null,
            'service_host': u.valid_ip
        }
        ret = u.validate_relation_data(unit, relation, expected)
        if ret:
            message = u.relation_error('keystone identity-service', ret)
            amulet.raise_status(amulet.FAIL, msg=message)

    def test_203_glance_keystone_id_relation(self):
        """Verify the glance:keystone identity-service relation data"""
        u.log.debug('Checking glance to keystone relation data...')
        unit = self.glance_sentry
        relation = ['identity-service',
                    'keystone:identity-service']
        expected = {
            'service': 'glance',
            'region': 'RegionOne',
            'public_url': u.valid_url,
            'internal_url': u.valid_url,
            'admin_url': u.valid_url,
            'private-address': u.valid_ip
        }
        ret = u.validate_relation_data(unit, relation, expected)
        if ret:
            message = u.relation_error('glance identity-service', ret)
            amulet.raise_status(amulet.FAIL, msg=message)

    def test_204_rabbitmq_glance_amqp_relation(self):
        """Verify the rabbitmq-server:glance amqp relation data"""
        u.log.debug('Checking rmq to glance amqp relation data...')
        unit = self.rabbitmq_sentry
        relation = ['amqp', 'glance:amqp']
        expected = {
            'private-address': u.valid_ip,
            'password': u.not_null,
            'hostname': u.valid_ip
        }
        ret = u.validate_relation_data(unit, relation, expected)
        if ret:
            message = u.relation_error('rabbitmq amqp', ret)
            amulet.raise_status(amulet.FAIL, msg=message)

    def test_205_glance_rabbitmq_amqp_relation(self):
        """Verify the glance:rabbitmq-server amqp relation data"""
        u.log.debug('Checking glance to rmq amqp relation data...')
        unit = self.glance_sentry
        relation = ['amqp', 'rabbitmq-server:amqp']
        expected = {
            'private-address': u.valid_ip,
            'vhost': 'openstack',
            'username': u.not_null
        }
        ret = u.validate_relation_data(unit, relation, expected)
        if ret:
            message = u.relation_error('glance amqp', ret)
            amulet.raise_status(amulet.FAIL, msg=message)

    def _get_keystone_authtoken_expected_dict(self, rel_ks_gl):
        """Return expected authtoken dict for OS release"""
        auth_uri = ('http://%s:%s/' %
                    (rel_ks_gl['auth_host'], rel_ks_gl['service_port']))
        auth_url = ('http://%s:%s/' %
                    (rel_ks_gl['auth_host'], rel_ks_gl['auth_port']))
        if self._get_openstack_release() >= self.trusty_mitaka:
            expected = {
                'keystone_authtoken': {
                    'auth_uri': auth_uri.rstrip('/'),
                    'auth_url': auth_url.rstrip('/'),
                    'auth_type': 'password',
                    'project_domain_name': 'default',
                    'user_domain_name': 'default',
                    'project_name': 'services',
                    'username': rel_ks_gl['service_username'],
                    'password': rel_ks_gl['service_password'],
                    'signing_dir': '/var/cache/glance'
                }
            }
        elif self._get_openstack_release() >= self.trusty_liberty:
            expected = {
                'keystone_authtoken': {
                    'auth_uri': auth_uri.rstrip('/'),
                    'auth_url': auth_url.rstrip('/'),
                    'auth_plugin': 'password',
                    'project_domain_id': 'default',
                    'user_domain_id': 'default',
                    'project_name': 'services',
                    'username': rel_ks_gl['service_username'],
                    'password': rel_ks_gl['service_password'],
                    'signing_dir': '/var/cache/glance'
                }
            }
        elif self._get_openstack_release() >= self.trusty_kilo:
            expected = {
                'keystone_authtoken': {
                    'project_name': 'services',
                    'username': 'glance',
                    'password': rel_ks_gl['service_password'],
                    'auth_uri': u.valid_url,
                    'auth_url': u.valid_url,
                    'signing_dir': '/var/cache/glance',
                }
            }
        else:
            expected = {
                'keystone_authtoken': {
                    'auth_uri': u.valid_url,
                    'auth_host': rel_ks_gl['auth_host'],
                    'auth_port': rel_ks_gl['auth_port'],
                    'auth_protocol': rel_ks_gl['auth_protocol'],
                    'admin_tenant_name': 'services',
                    'admin_user': 'glance',
                    'admin_password': rel_ks_gl['service_password'],
                    'signing_dir': '/var/cache/glance',
                }
            }

        return expected

    def test_300_glance_api_default_config(self):
        """Verify default section configs in glance-api.conf and
           compare some of the parameters to relation data."""
        u.log.debug('Checking glance api config file...')
        unit = self.glance_sentry
        unit_ks = self.keystone_sentry
        rel_mq_gl = self.rabbitmq_sentry.relation('amqp', 'glance:amqp')
        rel_ks_gl = unit_ks.relation('identity-service',
                                     'glance:identity-service')
        rel_my_gl = self.pxc_sentry.relation('shared-db', 'glance:shared-db')
        db_uri = "mysql://{}:{}@{}/{}".format('glance', rel_my_gl['password'],
                                              rel_my_gl['db_host'], 'glance')
        conf = '/etc/glance/glance-api.conf'
        expected = {
            'DEFAULT': {
                'debug': 'False',
                'verbose': 'False',
                'use_syslog': 'False',
                'log_file': '/var/log/glance/api.log',
                'bind_host': '0.0.0.0',
                'bind_port': '9282',
                'registry_host': '0.0.0.0',
                'registry_port': '9191',
                'registry_client_protocol': 'http',
                'delayed_delete': 'False',
                'scrub_time': '43200',
                'notification_driver': 'rabbit',
                'scrubber_datadir': '/var/lib/glance/scrubber',
                'image_cache_dir': '/var/lib/glance/image-cache/',
                'db_enforce_mysql_charset': 'False'
            },
        }

        expected.update(self._get_keystone_authtoken_expected_dict(rel_ks_gl))

        if self._get_openstack_release() >= self.trusty_kilo:
            # Kilo or later
            expected['oslo_messaging_rabbit'] = {
                'rabbit_userid': 'glance',
                'rabbit_virtual_host': 'openstack',
                'rabbit_password': rel_mq_gl['password'],
                'rabbit_host': rel_mq_gl['hostname']
            }
            expected['glance_store'] = {
                'filesystem_store_datadir': '/var/lib/glance/images/',
                'stores': 'glance.store.filesystem.'
                          'Store,glance.store.http.Store',
                'default_store': 'file'
            }
            expected['database'] = {
                'idle_timeout': '3600',
                'connection': db_uri
            }
            expected['DEFAULT']['notification_driver'] = 'messagingv2'
        else:
            # Juno or earlier
            expected['DEFAULT'].update({
                'rabbit_userid': 'glance',
                'rabbit_virtual_host': 'openstack',
                'rabbit_password': rel_mq_gl['password'],
                'rabbit_host': rel_mq_gl['hostname'],
                'filesystem_store_datadir': '/var/lib/glance/images/',
                'default_store': 'file',
            })
            expected['database'] = {
                'sql_idle_timeout': '3600',
                'connection': db_uri
            }

        for section, pairs in expected.iteritems():
            ret = u.validate_config_data(unit, conf, section, pairs)
            if ret:
                message = "glance api config error: {}".format(ret)
                amulet.raise_status(amulet.FAIL, msg=message)

    def test_302_glance_registry_default_config(self):
        """Verify configs in glance-registry.conf"""
        u.log.debug('Checking glance registry config file...')
        unit = self.glance_sentry
        unit_ks = self.keystone_sentry
        rel_ks_gl = unit_ks.relation('identity-service',
                                     'glance:identity-service')
        rel_my_gl = self.pxc_sentry.relation('shared-db', 'glance:shared-db')
        db_uri = "mysql://{}:{}@{}/{}".format('glance', rel_my_gl['password'],
                                              rel_my_gl['db_host'], 'glance')
        conf = '/etc/glance/glance-registry.conf'

        expected = {
            'DEFAULT': {
                'use_syslog': 'False',
                'log_file': '/var/log/glance/registry.log',
                'debug': 'False',
                'verbose': 'False',
                'bind_host': '0.0.0.0',
                'bind_port': '9191'
            },
        }

        if self._get_openstack_release() >= self.trusty_kilo:
            # Kilo or later
            expected['database'] = {
                'idle_timeout': '3600',
                'connection': db_uri
            }
        else:
            # Juno or earlier
            expected['database'] = {
                'idle_timeout': '3600',
                'connection': db_uri
            }

        expected.update(self._get_keystone_authtoken_expected_dict(rel_ks_gl))

        for section, pairs in expected.iteritems():
            ret = u.validate_config_data(unit, conf, section, pairs)
            if ret:
                message = "glance registry paste config error: {}".format(ret)
                amulet.raise_status(amulet.FAIL, msg=message)

    def test_410_glance_image_create_delete(self):
        """Create new cirros image in glance, verify, then delete it."""
        u.log.debug('Creating, checking and deleting glance image...')
        img_new = u.create_cirros_image(self.glance, "cirros-image-1")
        img_id = img_new.id
        u.delete_resource(self.glance.images, img_id, msg="glance image")

    def test_900_glance_restart_on_config_change(self):
        """Verify that the specified services are restarted when the config
           is changed."""
        sentry = self.glance_sentry
        juju_service = 'glance'

        # Expected default and alternate values
        set_default = {'use-syslog': 'False'}
        set_alternate = {'use-syslog': 'True'}

        # Config file affected by juju set config change
        conf_file = '/etc/glance/glance-api.conf'

        # Services which are expected to restart upon config change
        services = ['glance-api', 'glance-registry']

        # Make config change, check for service restarts
        u.log.debug('Making config change on {}...'.format(juju_service))
        self.d.configure(juju_service, set_alternate)

        sleep_time = 30
        for s in services:
            u.log.debug("Checking that service restarted: {}".format(s))
            if not u.service_restarted(sentry, s,
                                       conf_file, sleep_time=sleep_time):
                self.d.configure(juju_service, set_default)
                msg = "service {} didn't restart after config change".format(s)
                amulet.raise_status(amulet.FAIL, msg=msg)
            sleep_time = 0

        self.d.configure(juju_service, set_default)

    def test_901_pause_resume(self):
        """Test pause and resume actions."""
        u.log.debug('Checking pause and resume actions...')

        unit = self.d.sentry['glance'][0]
        unit_name = unit.info['unit_name']
        u.log.debug("Unit name: {}".format(unit_name))

        u.log.debug('Checking for active status on {}'.format(unit_name))
        assert u.status_get(unit)[0] == "active"

        u.log.debug('Running pause action on {}'.format(unit_name))
        self._assert_services(should_run=True)
        action_id = u.run_action(unit, "pause")
        u.log.debug('Waiting on action {}'.format(action_id))
        assert u.wait_on_action(action_id), "Pause action failed."
        self._assert_services(should_run=False)

        u.log.debug('Running resume action on {}'.format(unit_name))
        action_id = u.run_action(unit, "resume")
        u.log.debug('Waiting on action {}'.format(action_id))
        assert u.wait_on_action(action_id), "Resume action failed"
        self._assert_services(should_run=True)
