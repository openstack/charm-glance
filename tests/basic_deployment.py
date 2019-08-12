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
import time

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

    def __init__(self, series=None, openstack=None, source=None,
                 stable=True):
        """Deploy the entire test environment."""
        super(GlanceBasicDeployment, self).__init__(series, openstack,
                                                    source, stable)
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
        if self._get_openstack_release() >= self.bionic_stein:
            services = ('apache2', 'haproxy', 'glance-api')
        else:
            services = ('apache2', 'haproxy', 'glance-api', 'glance-registry')

        u.get_unit_process_ids(
            {self.glance_sentry: services},
            expect_success=should_run)

    def _add_services(self):
        """Add services

           Add the services that we're testing, where glance is local,
           and the rest of the service are from lp branches that are
           compatible with the local charm (e.g. stable or next).
           """
        this_service = {'name': 'glance'}
        other_services = [
            self.get_percona_service_entry(),
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
        self.keystone_session, self.keystone = u.get_default_keystone_session(
            self.keystone_sentry,
            openstack_release=self._get_openstack_release())

        force_v1_client = False
        if self._get_openstack_release() == self.trusty_icehouse:
            # Updating image properties (such as arch or hypervisor) using the
            # v2 api in icehouse results in:
            # https://bugs.launchpad.net/python-glanceclient/+bug/1371559
            u.log.debug('Forcing glance to use v1 api')
            force_v1_client = True

        # Authenticate admin with glance endpoint
        self.glance = u.authenticate_glance_admin(
            self.keystone,
            force_v1_client=force_v1_client)

    def test_100_services(self):
        """Verify that the expected services are running on the
           corresponding service units."""
        services = {
            self.keystone_sentry: ['keystone'],
            self.rabbitmq_sentry: ['rabbitmq-server'],
        }
        if self._get_openstack_release() >= self.bionic_stein:
            services.update(
                {self.glance_sentry: ['glance-api']})
        else:
            services.update(
                {self.glance_sentry: ['glance-api', 'glance-registry']})
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

        ret = u.validate_svc_catalog_endpoint_data(
            expected,
            actual,
            openstack_release=self._get_openstack_release())
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
        ret = u.validate_endpoint_data(
            endpoints,
            admin_port,
            internal_port,
            public_port,
            expected,
            openstack_release=self._get_openstack_release())
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
        ret = u.validate_endpoint_data(
            endpoints,
            admin_port,
            internal_port,
            public_port,
            expected,
            openstack_release=self._get_openstack_release())
        if ret:
            amulet.raise_status(amulet.FAIL,
                                msg='keystone endpoint: {}'.format(ret))

    def test_110_users(self):
        """Verify expected users."""
        u.log.debug('Checking keystone users...')
        if self._get_openstack_release() >= self.xenial_queens:
            expected = [
                {'name': 'glance',
                 'enabled': True,
                 'default_project_id': u.not_null,
                 'id': u.not_null,
                 'email': 'juju@localhost'}
            ]
            domain = self.keystone.domains.find(name='service_domain')
            actual = self.keystone.users.list(domain=domain)
            api_version = 3
        else:
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
            api_version = 2
        ret = u.validate_user_data(expected, actual, api_version)
        if ret:
            amulet.raise_status(amulet.FAIL, msg=ret)

    def test_115_memcache(self):
        u.validate_memcache(self.glance_sentry,
                            '/etc/glance/glance-api.conf',
                            self._get_openstack_release(),
                            earliest_release=self.trusty_mitaka)
        if self._get_openstack_release() < self.bionic_stein:
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

    def test_302_glance_registry_default_config(self):
        """Verify configs in glance-registry.conf"""
        if self._get_openstack_release() >= self.bionic_stein:
            u.log.debug('Skipping check of glance registry config file for '
                        '>= bionic-stein')
            return
        u.log.debug('Checking glance registry config file...')
        unit = self.glance_sentry
        rel_my_gl = self.pxc_sentry.relation('shared-db', 'glance:shared-db')
        if self._get_openstack_release() < self.xenial_queens:
            dialect = 'mysql'
        else:
            dialect = 'mysql+pymysql'
        db_uri = "{}://{}:{}@{}/{}".format(dialect,
                                           'glance',
                                           rel_my_gl['password'],
                                           rel_my_gl['db_host'],
                                           'glance')
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

    def test_411_set_disk_format(self):
        sleep_time = 30
        if self._get_openstack_release() >= self.trusty_kilo:
            section = 'image_format'
        elif self._get_openstack_release() > self.trusty_icehouse:
            section = 'DEFAULT'
        else:
            u.log.debug('Test not supported before juno')
            return
        sentry = self.glance_sentry
        juju_service = 'glance'

        # Expected default and alternate values
        set_default = {
            'disk-formats': 'ami,ari,aki,vhd,vmdk,raw,qcow2,vdi,iso,root-tar'}
        set_alternate = {'disk-formats': 'qcow2'}

        # Config file affected by juju set config change
        conf_file = '/etc/glance/glance-api.conf'

        # Make config change, check for service restarts
        u.log.debug('Setting disk format {}...'.format(juju_service))
        self.d.configure(juju_service, set_alternate)

        u.log.debug('Sleeping to let hooks fire')
        time.sleep(sleep_time)
        u.log.debug("Checking disk format option has updated")
        ret = u.validate_config_data(
            sentry,
            conf_file,
            section,
            {'disk_formats': 'qcow2'})
        if ret:
            msg = "disk_formats was not updated in section {} in {}".format(
                section,
                conf_file)
            amulet.raise_status(amulet.FAIL, msg=msg)

        self.d.configure(juju_service, set_default)

    def test_500_security_checklist_action(self):
        """Verify expected result on a default install"""
        u.log.debug("Testing security-checklist")
        sentry_unit = self.glance_sentry

        action_id = u.run_action(sentry_unit, "security-checklist")
        u.wait_on_action(action_id)
        data = amulet.actions.get_action_output(action_id, full_output=True)
        assert data.get(u"status") == "failed", \
            "Security check is expected to not pass by default"

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
        services = {
            'glance-api': conf_file,
        }
        if self._get_openstack_release() < self.bionic_stein:
            services.update({'glance-registry': conf_file})

        # Make config change, check for service restarts
        u.log.debug('Making config change on {}...'.format(juju_service))
        mtime = u.get_sentry_time(sentry)
        self.d.configure(juju_service, set_alternate)

        sleep_time = 30
        for s, conf_file in services.iteritems():
            u.log.debug("Checking that service restarted: {}".format(s))
            if not u.validate_service_config_changed(sentry, mtime, s,
                                                     conf_file,
                                                     retry_count=4,
                                                     retry_sleep_time=20,
                                                     sleep_time=sleep_time):
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
