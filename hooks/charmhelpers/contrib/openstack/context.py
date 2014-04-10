import json
import os
import time

from base64 import b64decode

from subprocess import (
    check_call
)


from charmhelpers.fetch import (
    apt_install,
    filter_installed_packages,
)

from charmhelpers.core.hookenv import (
    config,
    local_unit,
    log,
    relation_get,
    relation_ids,
    related_units,
    unit_get,
    unit_private_ip,
    ERROR,
)

from charmhelpers.contrib.hahelpers.cluster import (
    determine_apache_port,
    determine_api_port,
    https,
    is_clustered
)

from charmhelpers.contrib.hahelpers.apache import (
    get_cert,
    get_ca_cert,
)

from charmhelpers.contrib.openstack.neutron import (
    neutron_plugin_attribute,
)

CA_CERT_PATH = '/usr/local/share/ca-certificates/keystone_juju_ca_cert.crt'


class OSContextError(Exception):
    pass


def ensure_packages(packages):
    '''Install but do not upgrade required plugin packages'''
    required = filter_installed_packages(packages)
    if required:
        apt_install(required, fatal=True)


def context_complete(ctxt):
    _missing = []
    for k, v in ctxt.iteritems():
        if v is None or v == '':
            _missing.append(k)
    if _missing:
        log('Missing required data: %s' % ' '.join(_missing), level='INFO')
        return False
    return True


def config_flags_parser(config_flags):
    if config_flags.find('==') >= 0:
        log("config_flags is not in expected format (key=value)",
            level=ERROR)
        raise OSContextError
    # strip the following from each value.
    post_strippers = ' ,'
    # we strip any leading/trailing '=' or ' ' from the string then
    # split on '='.
    split = config_flags.strip(' =').split('=')
    limit = len(split)
    flags = {}
    for i in xrange(0, limit - 1):
        current = split[i]
        next = split[i + 1]
        vindex = next.rfind(',')
        if (i == limit - 2) or (vindex < 0):
            value = next
        else:
            value = next[:vindex]

        if i == 0:
            key = current
        else:
            # if this not the first entry, expect an embedded key.
            index = current.rfind(',')
            if index < 0:
                log("invalid config value(s) at index %s" % (i),
                    level=ERROR)
                raise OSContextError
            key = current[index + 1:]

        # Add to collection.
        flags[key.strip(post_strippers)] = value.rstrip(post_strippers)
    return flags


class OSContextGenerator(object):
    interfaces = []

    def __call__(self):
        raise NotImplementedError


class SharedDBContext(OSContextGenerator):
    interfaces = ['shared-db']

    def __init__(self,
                 database=None, user=None, relation_prefix=None, ssl_dir=None):
        '''
        Allows inspecting relation for settings prefixed with relation_prefix.
        This is useful for parsing access for multiple databases returned via
        the shared-db interface (eg, nova_password, quantum_password)
        '''
        self.relation_prefix = relation_prefix
        self.database = database
        self.user = user
        self.ssl_dir = ssl_dir

    def __call__(self):
        self.database = self.database or config('database')
        self.user = self.user or config('database-user')
        if None in [self.database, self.user]:
            log('Could not generate shared_db context. '
                'Missing required charm config options. '
                '(database name and user)')
            raise OSContextError
        ctxt = {}

        password_setting = 'password'
        if self.relation_prefix:
            password_setting = self.relation_prefix + '_password'

        for rid in relation_ids('shared-db'):
            for unit in related_units(rid):
                rdata = relation_get(rid=rid, unit=unit)
                ctxt = {
                    'database_host': rdata.get('db_host'),
                    'database': self.database,
                    'database_user': self.user,
                    'database_password': rdata.get(password_setting),
                    'database_type': 'mysql'
                }
                if context_complete(ctxt):
                    db_ssl(rdata, ctxt, self.ssl_dir)
                    return ctxt
        return {}


class PostgresqlDBContext(OSContextGenerator):
    interfaces = ['pgsql-db']

    def __init__(self, database=None):
        self.database = database

    def __call__(self):
        self.database = self.database or config('database')
        if self.database is None:
            log('Could not generate postgresql_db context. '
                'Missing required charm config options. '
                '(database name)')
            raise OSContextError
        ctxt = {}

        for rid in relation_ids(self.interfaces[0]):
            for unit in related_units(rid):
                ctxt = {
                    'database_host': relation_get('host', rid=rid, unit=unit),
                    'database': self.database,
                    'database_user': relation_get('user', rid=rid, unit=unit),
                    'database_password': relation_get('password', rid=rid, unit=unit),
                    'database_type': 'postgresql',
                }
                if context_complete(ctxt):
                    return ctxt
        return {}


def db_ssl(rdata, ctxt, ssl_dir):
    if 'ssl_ca' in rdata and ssl_dir:
        ca_path = os.path.join(ssl_dir, 'db-client.ca')
        with open(ca_path, 'w') as fh:
            fh.write(b64decode(rdata['ssl_ca']))
        ctxt['database_ssl_ca'] = ca_path
    elif 'ssl_ca' in rdata:
        log("Charm not setup for ssl support but ssl ca found")
        return ctxt
    if 'ssl_cert' in rdata:
        cert_path = os.path.join(
            ssl_dir, 'db-client.cert')
        if not os.path.exists(cert_path):
            log("Waiting 1m for ssl client cert validity")
            time.sleep(60)
        with open(cert_path, 'w') as fh:
            fh.write(b64decode(rdata['ssl_cert']))
        ctxt['database_ssl_cert'] = cert_path
        key_path = os.path.join(ssl_dir, 'db-client.key')
        with open(key_path, 'w') as fh:
            fh.write(b64decode(rdata['ssl_key']))
        ctxt['database_ssl_key'] = key_path
    return ctxt


class IdentityServiceContext(OSContextGenerator):
    interfaces = ['identity-service']

    def __call__(self):
        log('Generating template context for identity-service')
        ctxt = {}

        for rid in relation_ids('identity-service'):
            for unit in related_units(rid):
                rdata = relation_get(rid=rid, unit=unit)
                ctxt = {
                    'service_port': rdata.get('service_port'),
                    'service_host': rdata.get('service_host'),
                    'auth_host': rdata.get('auth_host'),
                    'auth_port': rdata.get('auth_port'),
                    'admin_tenant_name': rdata.get('service_tenant'),
                    'admin_user': rdata.get('service_username'),
                    'admin_password': rdata.get('service_password'),
                    'service_protocol':
                    rdata.get('service_protocol') or 'http',
                    'auth_protocol':
                    rdata.get('auth_protocol') or 'http',
                }
                if context_complete(ctxt):
                    # NOTE(jamespage) this is required for >= icehouse
                    # so a missing value just indicates keystone needs
                    # upgrading
                    ctxt['admin_tenant_id'] = rdata.get('service_tenant_id')
                    return ctxt
        return {}


class AMQPContext(OSContextGenerator):
    interfaces = ['amqp']

    def __init__(self, ssl_dir=None):
        self.ssl_dir = ssl_dir

    def __call__(self):
        log('Generating template context for amqp')
        conf = config()
        try:
            username = conf['rabbit-user']
            vhost = conf['rabbit-vhost']
        except KeyError as e:
            log('Could not generate shared_db context. '
                'Missing required charm config options: %s.' % e)
            raise OSContextError
        ctxt = {}
        for rid in relation_ids('amqp'):
            ha_vip_only = False
            for unit in related_units(rid):
                if relation_get('clustered', rid=rid, unit=unit):
                    ctxt['clustered'] = True
                    ctxt['rabbitmq_host'] = relation_get('vip', rid=rid,
                                                         unit=unit)
                else:
                    ctxt['rabbitmq_host'] = relation_get('private-address',
                                                         rid=rid, unit=unit)
                ctxt.update({
                    'rabbitmq_user': username,
                    'rabbitmq_password': relation_get('password', rid=rid,
                                                      unit=unit),
                    'rabbitmq_virtual_host': vhost,
                })

                ssl_port = relation_get('ssl_port', rid=rid, unit=unit)
                if ssl_port:
                    ctxt['rabbit_ssl_port'] = ssl_port
                ssl_ca = relation_get('ssl_ca', rid=rid, unit=unit)
                if ssl_ca:
                    ctxt['rabbit_ssl_ca'] = ssl_ca

                if relation_get('ha_queues', rid=rid, unit=unit) is not None:
                    ctxt['rabbitmq_ha_queues'] = True

                ha_vip_only = relation_get('ha-vip-only',
                                           rid=rid, unit=unit) is not None

                if context_complete(ctxt):
                    if 'rabbit_ssl_ca' in ctxt:
                        if not self.ssl_dir:
                            log(("Charm not setup for ssl support "
                                 "but ssl ca found"))
                            break
                        ca_path = os.path.join(
                            self.ssl_dir, 'rabbit-client-ca.pem')
                        with open(ca_path, 'w') as fh:
                            fh.write(b64decode(ctxt['rabbit_ssl_ca']))
                            ctxt['rabbit_ssl_ca'] = ca_path
                    # Sufficient information found = break out!
                    break
            # Used for active/active rabbitmq >= grizzly
            if ('clustered' not in ctxt or ha_vip_only) \
                    and len(related_units(rid)) > 1:
                rabbitmq_hosts = []
                for unit in related_units(rid):
                    rabbitmq_hosts.append(relation_get('private-address',
                                                       rid=rid, unit=unit))
                ctxt['rabbitmq_hosts'] = ','.join(rabbitmq_hosts)
        if not context_complete(ctxt):
            return {}
        else:
            return ctxt


class CephContext(OSContextGenerator):
    interfaces = ['ceph']

    def __call__(self):
        '''This generates context for /etc/ceph/ceph.conf templates'''
        if not relation_ids('ceph'):
            return {}

        log('Generating template context for ceph')

        mon_hosts = []
        auth = None
        key = None
        use_syslog = str(config('use-syslog')).lower()
        for rid in relation_ids('ceph'):
            for unit in related_units(rid):
                mon_hosts.append(relation_get('private-address', rid=rid,
                                              unit=unit))
                auth = relation_get('auth', rid=rid, unit=unit)
                key = relation_get('key', rid=rid, unit=unit)

        ctxt = {
            'mon_hosts': ' '.join(mon_hosts),
            'auth': auth,
            'key': key,
            'use_syslog': use_syslog
        }

        if not os.path.isdir('/etc/ceph'):
            os.mkdir('/etc/ceph')

        if not context_complete(ctxt):
            return {}

        ensure_packages(['ceph-common'])

        return ctxt


class HAProxyContext(OSContextGenerator):
    interfaces = ['cluster']

    def __call__(self):
        '''
        Builds half a context for the haproxy template, which describes
        all peers to be included in the cluster.  Each charm needs to include
        its own context generator that describes the port mapping.
        '''
        if not relation_ids('cluster'):
            return {}

        cluster_hosts = {}
        l_unit = local_unit().replace('/', '-')
        cluster_hosts[l_unit] = unit_get('private-address')

        for rid in relation_ids('cluster'):
            for unit in related_units(rid):
                _unit = unit.replace('/', '-')
                addr = relation_get('private-address', rid=rid, unit=unit)
                cluster_hosts[_unit] = addr

        ctxt = {
            'units': cluster_hosts,
        }
        if len(cluster_hosts.keys()) > 1:
            # Enable haproxy when we have enough peers.
            log('Ensuring haproxy enabled in /etc/default/haproxy.')
            with open('/etc/default/haproxy', 'w') as out:
                out.write('ENABLED=1\n')
            return ctxt
        log('HAProxy context is incomplete, this unit has no peers.')
        return {}


class ImageServiceContext(OSContextGenerator):
    interfaces = ['image-service']

    def __call__(self):
        '''
        Obtains the glance API server from the image-service relation.  Useful
        in nova and cinder (currently).
        '''
        log('Generating template context for image-service.')
        rids = relation_ids('image-service')
        if not rids:
            return {}
        for rid in rids:
            for unit in related_units(rid):
                api_server = relation_get('glance-api-server',
                                          rid=rid, unit=unit)
                if api_server:
                    return {'glance_api_servers': api_server}
        log('ImageService context is incomplete. '
            'Missing required relation data.')
        return {}


class ApacheSSLContext(OSContextGenerator):

    """
    Generates a context for an apache vhost configuration that configures
    HTTPS reverse proxying for one or many endpoints.  Generated context
    looks something like:
    {
        'namespace': 'cinder',
        'private_address': 'iscsi.mycinderhost.com',
        'endpoints': [(8776, 8766), (8777, 8767)]
    }

    The endpoints list consists of a tuples mapping external ports
    to internal ports.
    """
    interfaces = ['https']

    # charms should inherit this context and set external ports
    # and service namespace accordingly.
    external_ports = []
    service_namespace = None

    def enable_modules(self):
        cmd = ['a2enmod', 'ssl', 'proxy', 'proxy_http']
        check_call(cmd)

    def configure_cert(self):
        if not os.path.isdir('/etc/apache2/ssl'):
            os.mkdir('/etc/apache2/ssl')
        ssl_dir = os.path.join('/etc/apache2/ssl/', self.service_namespace)
        if not os.path.isdir(ssl_dir):
            os.mkdir(ssl_dir)
        cert, key = get_cert()
        with open(os.path.join(ssl_dir, 'cert'), 'w') as cert_out:
            cert_out.write(b64decode(cert))
        with open(os.path.join(ssl_dir, 'key'), 'w') as key_out:
            key_out.write(b64decode(key))
        ca_cert = get_ca_cert()
        if ca_cert:
            with open(CA_CERT_PATH, 'w') as ca_out:
                ca_out.write(b64decode(ca_cert))
            check_call(['update-ca-certificates'])

    def __call__(self):
        if isinstance(self.external_ports, basestring):
            self.external_ports = [self.external_ports]
        if (not self.external_ports or not https()):
            return {}

        self.configure_cert()
        self.enable_modules()

        ctxt = {
            'namespace': self.service_namespace,
            'private_address': unit_get('private-address'),
            'endpoints': []
        }
        if is_clustered():
            ctxt['private_address'] = config('vip')
        for api_port in self.external_ports:
            ext_port = determine_apache_port(api_port)
            int_port = determine_api_port(api_port)
            portmap = (int(ext_port), int(int_port))
            ctxt['endpoints'].append(portmap)
        return ctxt


class NeutronContext(OSContextGenerator):
    interfaces = []

    @property
    def plugin(self):
        return None

    @property
    def network_manager(self):
        return None

    @property
    def packages(self):
        return neutron_plugin_attribute(
            self.plugin, 'packages', self.network_manager)

    @property
    def neutron_security_groups(self):
        return None

    def _ensure_packages(self):
        [ensure_packages(pkgs) for pkgs in self.packages]

    def _save_flag_file(self):
        if self.network_manager == 'quantum':
            _file = '/etc/nova/quantum_plugin.conf'
        else:
            _file = '/etc/nova/neutron_plugin.conf'
        with open(_file, 'wb') as out:
            out.write(self.plugin + '\n')

    def ovs_ctxt(self):
        driver = neutron_plugin_attribute(self.plugin, 'driver',
                                          self.network_manager)
        config = neutron_plugin_attribute(self.plugin, 'config',
                                          self.network_manager)
        ovs_ctxt = {
            'core_plugin': driver,
            'neutron_plugin': 'ovs',
            'neutron_security_groups': self.neutron_security_groups,
            'local_ip': unit_private_ip(),
            'config': config
        }

        return ovs_ctxt

    def nvp_ctxt(self):
        driver = neutron_plugin_attribute(self.plugin, 'driver',
                                          self.network_manager)
        config = neutron_plugin_attribute(self.plugin, 'config',
                                          self.network_manager)
        nvp_ctxt = {
            'core_plugin': driver,
            'neutron_plugin': 'nvp',
            'neutron_security_groups': self.neutron_security_groups,
            'local_ip': unit_private_ip(),
            'config': config
        }

        return nvp_ctxt

    def neutron_ctxt(self):
        if https():
            proto = 'https'
        else:
            proto = 'http'
        if is_clustered():
            host = config('vip')
        else:
            host = unit_get('private-address')
        url = '%s://%s:%s' % (proto, host, '9696')
        ctxt = {
            'network_manager': self.network_manager,
            'neutron_url': url,
        }
        return ctxt

    def __call__(self):
        self._ensure_packages()

        if self.network_manager not in ['quantum', 'neutron']:
            return {}

        if not self.plugin:
            return {}

        ctxt = self.neutron_ctxt()

        if self.plugin == 'ovs':
            ctxt.update(self.ovs_ctxt())
        elif self.plugin == 'nvp':
            ctxt.update(self.nvp_ctxt())

        alchemy_flags = config('neutron-alchemy-flags')
        if alchemy_flags:
            flags = config_flags_parser(alchemy_flags)
            ctxt['neutron_alchemy_flags'] = flags

        self._save_flag_file()
        return ctxt


class OSConfigFlagContext(OSContextGenerator):

        """
        Responsible for adding user-defined config-flags in charm config to a
        template context.

        NOTE: the value of config-flags may be a comma-separated list of
              key=value pairs and some Openstack config files support
              comma-separated lists as values.
        """

        def __call__(self):
            config_flags = config('config-flags')
            if not config_flags:
                return {}

            flags = config_flags_parser(config_flags)
            return {'user_config_flags': flags}


class SubordinateConfigContext(OSContextGenerator):

    """
    Responsible for inspecting relations to subordinates that
    may be exporting required config via a json blob.

    The subordinate interface allows subordinates to export their
    configuration requirements to the principle for multiple config
    files and multiple serivces.  Ie, a subordinate that has interfaces
    to both glance and nova may export to following yaml blob as json:

        glance:
            /etc/glance/glance-api.conf:
                sections:
                    DEFAULT:
                        - [key1, value1]
            /etc/glance/glance-registry.conf:
                    MYSECTION:
                        - [key2, value2]
        nova:
            /etc/nova/nova.conf:
                sections:
                    DEFAULT:
                        - [key3, value3]


    It is then up to the principle charms to subscribe this context to
    the service+config file it is interestd in.  Configuration data will
    be available in the template context, in glance's case, as:
        ctxt = {
            ... other context ...
            'subordinate_config': {
                'DEFAULT': {
                    'key1': 'value1',
                },
                'MYSECTION': {
                    'key2': 'value2',
                },
            }
        }

    """

    def __init__(self, service, config_file, interface):
        """
        :param service     : Service name key to query in any subordinate
                             data found
        :param config_file : Service's config file to query sections
        :param interface   : Subordinate interface to inspect
        """
        self.service = service
        self.config_file = config_file
        self.interface = interface

    def __call__(self):
        ctxt = {}
        for rid in relation_ids(self.interface):
            for unit in related_units(rid):
                sub_config = relation_get('subordinate_configuration',
                                          rid=rid, unit=unit)
                if sub_config and sub_config != '':
                    try:
                        sub_config = json.loads(sub_config)
                    except:
                        log('Could not parse JSON from subordinate_config '
                            'setting from %s' % rid, level=ERROR)
                        continue

                    if self.service not in sub_config:
                        log('Found subordinate_config on %s but it contained'
                            'nothing for %s service' % (rid, self.service))
                        continue

                    sub_config = sub_config[self.service]
                    if self.config_file not in sub_config:
                        log('Found subordinate_config on %s but it contained'
                            'nothing for %s' % (rid, self.config_file))
                        continue

                    sub_config = sub_config[self.config_file]
                    for k, v in sub_config.iteritems():
                        ctxt[k] = v

        if not ctxt:
            ctxt['sections'] = {}

        return ctxt


class SyslogContext(OSContextGenerator):

    def __call__(self):
        ctxt = {
            'use_syslog': config('use-syslog')
        }
        return ctxt
