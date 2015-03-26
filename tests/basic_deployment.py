#!/usr/bin/python

import amulet

from charmhelpers.contrib.openstack.amulet.deployment import (
    OpenStackAmuletDeployment
)

from charmhelpers.contrib.openstack.amulet.utils import (
    OpenStackAmuletUtils,
    DEBUG, # flake8: noqa
    ERROR
)

# Use DEBUG to turn on debug logging
u = OpenStackAmuletUtils(ERROR)

class GlanceBasicDeployment(OpenStackAmuletDeployment):
    '''Amulet tests on a basic file-backed glance deployment.  Verify relations,
       service status, endpoint service catalog, create and delete new image.'''

#  TO-DO(beisner): 
#    * Add tests with different storage back ends
#    * Resolve Essex->Havana juju set charm bug

    def __init__(self, series=None, openstack=None, source=None, stable=False):
        '''Deploy the entire test environment.'''
        super(GlanceBasicDeployment, self).__init__(series, openstack, source, stable)
        self._add_services()
        self._add_relations()
        self._configure_services()
        self._deploy()
        self._initialize_tests()

    def _add_services(self):
        '''Add services

           Add the services that we're testing, where glance is local,
           and the rest of the service are from lp branches that are
           compatible with the local charm (e.g. stable or next).
           '''
        this_service = {'name': 'glance'}
        other_services = [{'name': 'mysql'}, {'name': 'rabbitmq-server'},
                          {'name': 'keystone'}]
        super(GlanceBasicDeployment, self)._add_services(this_service,
                                                         other_services)

    def _add_relations(self):
        '''Add relations for the services.'''
        relations = {'glance:identity-service': 'keystone:identity-service',
                     'glance:shared-db': 'mysql:shared-db',
                     'keystone:shared-db': 'mysql:shared-db',
                     'glance:amqp': 'rabbitmq-server:amqp'}
        super(GlanceBasicDeployment, self)._add_relations(relations)

    def _configure_services(self):
        '''Configure all of the services.'''
        keystone_config = {'admin-password': 'openstack',
                           'admin-token': 'ubuntutesting'}

        mysql_config = {'dataset-size': '50%'}
        configs = {'keystone': keystone_config,
                   'mysql': mysql_config}
        super(GlanceBasicDeployment, self)._configure_services(configs)

    def _initialize_tests(self):
        '''Perform final initialization before tests get run.'''
        # Access the sentries for inspecting service units
        self.mysql_sentry = self.d.sentry.unit['mysql/0']
        self.glance_sentry = self.d.sentry.unit['glance/0']
        self.keystone_sentry = self.d.sentry.unit['keystone/0']
        self.rabbitmq_sentry = self.d.sentry.unit['rabbitmq-server/0']

        # Authenticate admin with keystone
        self.keystone = u.authenticate_keystone_admin(self.keystone_sentry,
                                                      user='admin',
                                                      password='openstack',
                                                      tenant='admin')

        # Authenticate admin with glance endpoint
        self.glance = u.authenticate_glance_admin(self.keystone)

        u.log.debug('openstack release: {}'.format(self._get_openstack_release()))

    def test_services(self):
        '''Verify that the expected services are running on the
           corresponding service units.'''
        commands = {
            self.mysql_sentry: ['status mysql'],
            self.keystone_sentry: ['status keystone'],
            self.glance_sentry: ['status glance-api', 'status glance-registry'],
            self.rabbitmq_sentry: ['sudo service rabbitmq-server status']
        }
        u.log.debug('commands: {}'.format(commands))
        ret = u.validate_services(commands)
        if ret:
            amulet.raise_status(amulet.FAIL, msg=ret)

    def test_service_catalog(self):
        '''Verify that the service catalog endpoint data'''
        endpoint_vol = {'adminURL': u.valid_url,
                        'region': 'RegionOne',
                        'publicURL': u.valid_url,
                        'internalURL': u.valid_url}
        endpoint_id = {'adminURL': u.valid_url,
                       'region': 'RegionOne',
                       'publicURL': u.valid_url,
                       'internalURL': u.valid_url}
        if self._get_openstack_release() >= self.trusty_icehouse:
            endpoint_vol['id'] = u.not_null
            endpoint_id['id'] = u.not_null

        expected = {'image': [endpoint_id],
                    'identity': [endpoint_id]}
        actual = self.keystone.service_catalog.get_endpoints()

        ret = u.validate_svc_catalog_endpoint_data(expected, actual)
        if ret:
            amulet.raise_status(amulet.FAIL, msg=ret)

    def test_mysql_glance_db_relation(self):
        '''Verify the mysql:glance shared-db relation data'''
        unit = self.mysql_sentry
        relation = ['shared-db', 'glance:shared-db']
        expected = {
            'private-address': u.valid_ip,
            'db_host': u.valid_ip
        }
        ret = u.validate_relation_data(unit, relation, expected)
        if ret:
            message = u.relation_error('mysql shared-db', ret)
            amulet.raise_status(amulet.FAIL, msg=message)

    def test_glance_mysql_db_relation(self):
        '''Verify the glance:mysql shared-db relation data'''
        unit = self.glance_sentry
        relation = ['shared-db', 'mysql:shared-db']
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

    def test_keystone_glance_id_relation(self):
        '''Verify the keystone:glance identity-service relation data'''
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

    def test_glance_keystone_id_relation(self):
        '''Verify the glance:keystone identity-service relation data'''
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

    def test_rabbitmq_glance_amqp_relation(self):
        '''Verify the rabbitmq-server:glance amqp relation data'''
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

    def test_glance_rabbitmq_amqp_relation(self):
        '''Verify the glance:rabbitmq-server amqp relation data'''
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

    def test_image_create_delete(self):
        '''Create new cirros image in glance, verify, then delete it'''

        # Create a new image
        image_name = 'cirros-image-1'
        image_new = u.create_cirros_image(self.glance, image_name)

        # Confirm image is created and has status of 'active' 
        if not image_new:
            message = 'glance image create failed'
            amulet.raise_status(amulet.FAIL, msg=message)

        # Verify new image name
        images_list = list(self.glance.images.list())
        if images_list[0].name != image_name:
            message = 'glance image create failed or unexpected image name {}'.format(images_list[0].name)
            amulet.raise_status(amulet.FAIL, msg=message)

        # Delete the new image
        u.log.debug('image count before delete: {}'.format(len(list(self.glance.images.list()))))
        u.delete_image(self.glance, image_new)
        u.log.debug('image count after delete: {}'.format(len(list(self.glance.images.list()))))

    def test_glance_api_default_config(self):
        '''Verify default section configs in glance-api.conf and
           compare some of the parameters to relation data.'''
        unit = self.glance_sentry
        rel_gl_mq = unit.relation('amqp', 'rabbitmq-server:amqp')
        conf = '/etc/glance/glance-api.conf'
        expected = {'use_syslog': 'False',
                    'default_store': 'file',
                    'filesystem_store_datadir': '/var/lib/glance/images/',
                    'rabbit_userid': rel_gl_mq['username'],
                    'log_file': '/var/log/glance/api.log',
                    'debug': 'False',
                    'verbose': 'False'}
        section = 'DEFAULT'

        if self._get_openstack_release() <= self.precise_havana:
            # Defaults were different before icehouse
            expected['debug'] = 'True'
            expected['verbose'] = 'True'

        ret = u.validate_config_data(unit, conf, section, expected)
        if ret:
            message = "glance-api default config error: {}".format(ret)
            amulet.raise_status(amulet.FAIL, msg=message)

    def test_glance_api_auth_config(self):
        '''Verify authtoken section config in glance-api.conf using
           glance/keystone relation data.'''
        unit_gl = self.glance_sentry
        unit_ks = self.keystone_sentry
        rel_gl_mq = unit_gl.relation('amqp', 'rabbitmq-server:amqp')
        rel_ks_gl = unit_ks.relation('identity-service', 'glance:identity-service')
        conf = '/etc/glance/glance-api.conf'
        section = 'keystone_authtoken'

        if self._get_openstack_release() > self.precise_havana:
            # No auth config exists in this file before icehouse
            expected = {'admin_user': 'glance',
                    'admin_password': rel_ks_gl['service_password']}

            ret = u.validate_config_data(unit_gl, conf, section, expected)
            if ret:
                message = "glance-api auth config error: {}".format(ret)
                amulet.raise_status(amulet.FAIL, msg=message)

    def test_glance_api_paste_auth_config(self):
        '''Verify authtoken section config in glance-api-paste.ini using
           glance/keystone relation data.'''
        unit_gl = self.glance_sentry
        unit_ks = self.keystone_sentry
        rel_gl_mq = unit_gl.relation('amqp', 'rabbitmq-server:amqp')
        rel_ks_gl = unit_ks.relation('identity-service', 'glance:identity-service')
        conf = '/etc/glance/glance-api-paste.ini'
        section = 'filter:authtoken'

        if self._get_openstack_release() <= self.precise_havana:
            # No auth config exists in this file after havana
            expected = {'admin_user': 'glance',
                    'admin_password': rel_ks_gl['service_password']}

            ret = u.validate_config_data(unit_gl, conf, section, expected)
            if ret:
                message = "glance-api-paste auth config error: {}".format(ret)
                amulet.raise_status(amulet.FAIL, msg=message)

    def test_glance_registry_paste_auth_config(self):
        '''Verify authtoken section config in glance-registry-paste.ini using
           glance/keystone relation data.'''
        unit_gl = self.glance_sentry
        unit_ks = self.keystone_sentry
        rel_gl_mq = unit_gl.relation('amqp', 'rabbitmq-server:amqp')
        rel_ks_gl = unit_ks.relation('identity-service', 'glance:identity-service')
        conf = '/etc/glance/glance-registry-paste.ini'
        section = 'filter:authtoken'

        if self._get_openstack_release() <= self.precise_havana:
            # No auth config exists in this file after havana
            expected = {'admin_user': 'glance',
                    'admin_password': rel_ks_gl['service_password']}

            ret = u.validate_config_data(unit_gl, conf, section, expected)
            if ret:
                message = "glance-registry-paste auth config error: {}".format(ret)
                amulet.raise_status(amulet.FAIL, msg=message)

    def test_glance_registry_default_config(self):
        '''Verify default section configs in glance-registry.conf'''
        unit = self.glance_sentry
        conf = '/etc/glance/glance-registry.conf'
        expected = {'use_syslog': 'False',
                    'log_file': '/var/log/glance/registry.log',
                    'debug': 'False',
                    'verbose': 'False'}
        section = 'DEFAULT'

        if self._get_openstack_release() <= self.precise_havana:
            # Defaults were different before icehouse
            expected['debug'] = 'True'
            expected['verbose'] = 'True'

        ret = u.validate_config_data(unit, conf, section, expected)
        if ret:
            message = "glance-registry default config error: {}".format(ret)
            amulet.raise_status(amulet.FAIL, msg=message)

    def test_glance_registry_auth_config(self):
        '''Verify authtoken section config in glance-registry.conf
           using glance/keystone relation data.'''
        unit_gl = self.glance_sentry
        unit_ks = self.keystone_sentry
        rel_gl_mq = unit_gl.relation('amqp', 'rabbitmq-server:amqp')
        rel_ks_gl = unit_ks.relation('identity-service', 'glance:identity-service')
        conf = '/etc/glance/glance-registry.conf'
        section = 'keystone_authtoken'

        if self._get_openstack_release() > self.precise_havana:
            # No auth config exists in this file before icehouse
            expected = {'admin_user': 'glance',
                    'admin_password': rel_ks_gl['service_password']}

            ret = u.validate_config_data(unit_gl, conf, section, expected)
            if ret:
                message = "glance-registry keystone_authtoken config error: {}".format(ret)
                amulet.raise_status(amulet.FAIL, msg=message)

    def test_glance_api_database_config(self):
        '''Verify database config in glance-api.conf and
           compare with a db uri constructed from relation data.'''
        unit = self.glance_sentry
        conf = '/etc/glance/glance-api.conf'
        relation = self.mysql_sentry.relation('shared-db', 'glance:shared-db')
        db_uri = "mysql://{}:{}@{}/{}".format('glance', relation['password'],
                                              relation['db_host'], 'glance')
        expected = {'connection': db_uri, 'sql_idle_timeout': '3600'}
        section = 'database'

        if self._get_openstack_release() <= self.precise_havana:
            # Section and directive for this config changed in icehouse
            expected = {'sql_connection': db_uri, 'sql_idle_timeout': '3600'}
            section = 'DEFAULT'

        ret = u.validate_config_data(unit, conf, section, expected) 
        if ret:
            message = "glance db config error: {}".format(ret)
            amulet.raise_status(amulet.FAIL, msg=message)

    def test_glance_registry_database_config(self):
        '''Verify database config in glance-registry.conf and
           compare with a db uri constructed from relation data.'''
        unit = self.glance_sentry
        conf = '/etc/glance/glance-registry.conf'
        relation = self.mysql_sentry.relation('shared-db', 'glance:shared-db')
        db_uri = "mysql://{}:{}@{}/{}".format('glance', relation['password'],
                                              relation['db_host'], 'glance')
        expected = {'connection': db_uri, 'sql_idle_timeout': '3600'}
        section = 'database'

        if self._get_openstack_release() <= self.precise_havana:
            # Section and directive for this config changed in icehouse
            expected = {'sql_connection': db_uri, 'sql_idle_timeout': '3600'}
            section = 'DEFAULT'

        ret = u.validate_config_data(unit, conf, section, expected)
        if ret:
            message = "glance db config error: {}".format(ret)
            amulet.raise_status(amulet.FAIL, msg=message)

    def test_glance_endpoint(self):
        '''Verify the glance endpoint data.'''
        endpoints = self.keystone.endpoints.list()
        admin_port = internal_port = public_port = '9292'
        expected = {'id': u.not_null,
                    'region': 'RegionOne',
                    'adminurl': u.valid_url,
                    'internalurl': u.valid_url,
                    'publicurl': u.valid_url,
                    'service_id': u.not_null}
        ret = u.validate_endpoint_data(endpoints, admin_port, internal_port,
                                       public_port, expected)

        if ret:
            amulet.raise_status(amulet.FAIL,
                                msg='glance endpoint: {}'.format(ret))

    def test_keystone_endpoint(self):
        '''Verify the keystone endpoint data.'''
        endpoints = self.keystone.endpoints.list()
        admin_port = '35357'
        internal_port = public_port = '5000'
        expected = {'id': u.not_null,
                    'region': 'RegionOne',
                    'adminurl': u.valid_url,
                    'internalurl': u.valid_url,
                    'publicurl': u.valid_url,
                    'service_id': u.not_null}
        ret = u.validate_endpoint_data(endpoints, admin_port, internal_port,
                                       public_port, expected)
        if ret:
            amulet.raise_status(amulet.FAIL,
                                msg='keystone endpoint: {}'.format(ret))

    def _change_config(self):
        if self._get_openstack_release() > self.precise_havana:
            self.d.configure('glance', {'debug': 'True'})
        else:
            self.d.configure('glance', {'debug': 'False'})

    def _restore_config(self):
        if self._get_openstack_release() > self.precise_havana:
            self.d.configure('glance', {'debug': 'False'})
        else:
            self.d.configure('glance', {'debug': 'True'})

    def test_z_glance_restart_on_config_change(self):
        '''Verify that glance is restarted when the config is changed.

           Note(coreycb): The method name with the _z_ is a little odd
           but it forces the test to run last.  It just makes things
           easier because restarting services requires re-authorization.
           '''
        if self._get_openstack_release() <= self.precise_havana:
            # /!\ NOTE(beisner): Glance charm before Icehouse doesn't respond
            # to attempted config changes via juju / juju set.
            # https://bugs.launchpad.net/charms/+source/glance/+bug/1340307
            u.log.error('NOTE(beisner): skipping glance restart on config ' +
                        'change check due to bug 1340307.')
            return

        # Make config change to trigger a service restart
        self._change_config()

        if not u.service_restarted(self.glance_sentry, 'glance-api',
                                   '/etc/glance/glance-api.conf'):
            self._restore_config()
            message = "glance service didn't restart after config change"
            amulet.raise_status(amulet.FAIL, msg=message)

        if not u.service_restarted(self.glance_sentry, 'glance-registry',
                                   '/etc/glance/glance-registry.conf',
                                   sleep_time=0):
            self._restore_config()
            message = "glance service didn't restart after config change"
            amulet.raise_status(amulet.FAIL, msg=message)

        # Return to original config
        self._restore_config()

    def test_users(self):
        '''Verify expected users.'''
        user0 = {'name': 'glance',
                 'enabled': True,
                 'tenantId': u.not_null,
                 'id': u.not_null,
                 'email': 'juju@localhost'}
        user1 = {'name': 'admin',
                 'enabled': True,
                 'tenantId': u.not_null,
                 'id': u.not_null,
                 'email': 'juju@localhost'}
        expected = [user0, user1]
        actual = self.keystone.users.list()

        ret = u.validate_user_data(expected, actual)
        if ret:
            amulet.raise_status(amulet.FAIL, msg=ret)
