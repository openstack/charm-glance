import json
import os

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
    WARNING,
)

from charmhelpers.contrib.hahelpers.cluster import (
    determine_api_port,
    determine_haproxy_port,
    https,
    is_clustered,
    peer_units,
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


class OSContextGenerator(object):
    interfaces = []

    def __call__(self):
        raise NotImplementedError


class SharedDBContext(OSContextGenerator):
    interfaces = ['shared-db']

    def __init__(self, database=None, user=None, relation_prefix=None):
        '''
        Allows inspecting relation for settings prefixed with relation_prefix.
        This is useful for parsing access for multiple databases returned via
        the shared-db interface (eg, nova_password, quantum_password)
        '''
        self.relation_prefix = relation_prefix
        self.database = database
        self.user = user

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
                passwd = relation_get(password_setting, rid=rid, unit=unit)
                ctxt = {
                    'database_host': relation_get('db_host', rid=rid,
                                                  unit=unit),
                    'database': self.database,
                    'database_user': self.user,
                    'database_password': passwd,
                }
                if context_complete(ctxt):
                    return ctxt
        return {}


class IdentityServiceContext(OSContextGenerator):
    interfaces = ['identity-service']

    def __call__(self):
        log('Generating template context for identity-service')
        ctxt = {}

        for rid in relation_ids('identity-service'):
            for unit in related_units(rid):
                ctxt = {
                    'service_port': relation_get('service_port', rid=rid,
                                                 unit=unit),
                    'service_host': relation_get('service_host', rid=rid,
                                                 unit=unit),
                    'auth_host': relation_get('auth_host', rid=rid, unit=unit),
                    'auth_port': relation_get('auth_port', rid=rid, unit=unit),
                    'admin_tenant_name': relation_get('service_tenant',
                                                      rid=rid, unit=unit),
                    'admin_user': relation_get('service_username', rid=rid,
                                               unit=unit),
                    'admin_password': relation_get('service_password', rid=rid,
                                                   unit=unit),
                    # XXX: Hard-coded http.
                    'service_protocol': 'http',
                    'auth_protocol': 'http',
                }
                if context_complete(ctxt):
                    return ctxt
        return {}


class AMQPContext(OSContextGenerator):
    interfaces = ['amqp']

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
                if context_complete(ctxt):
                    # Sufficient information found = break out!
                    break
            # Used for active/active rabbitmq >= grizzly
            ctxt['rabbitmq_hosts'] = []
            for unit in related_units(rid):
                ctxt['rabbitmq_hosts'].append(relation_get('private-address',
                                                           rid=rid, unit=unit))
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
        for ext_port in self.external_ports:
            if peer_units() or is_clustered():
                int_port = determine_haproxy_port(ext_port)
            else:
                int_port = determine_api_port(ext_port)
            portmap = (int(ext_port), int(int_port))
            ctxt['endpoints'].append(portmap)
        return ctxt


class NeutronContext(object):
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

        ovs_ctxt = {
            'core_plugin': driver,
            'neutron_plugin': 'ovs',
            'neutron_security_groups': self.neutron_security_groups,
            'local_ip': unit_private_ip(),
        }

        return ovs_ctxt

    def __call__(self):
        self._ensure_packages()

        if self.network_manager not in ['quantum', 'neutron']:
            return {}

        if not self.plugin:
            return {}

        ctxt = {'network_manager': self.network_manager}

        if self.plugin == 'ovs':
            ctxt.update(self.ovs_ctxt())

        self._save_flag_file()
        return ctxt


class OSConfigFlagContext(OSContextGenerator):
        '''
        Responsible adding user-defined config-flags in charm config to a
        to a template context.
        '''
        def __call__(self):
            config_flags = config('config-flags')
            if not config_flags or config_flags in ['None', '']:
                return {}
            config_flags = config_flags.split(',')
            flags = {}
            for flag in config_flags:
                if '=' not in flag:
                    log('Improperly formatted config-flag, expected k=v '
                        'got %s' % flag, level=WARNING)
                    continue
                k, v = flag.split('=')
                flags[k.strip()] = v
            ctxt = {'user_config_flags': flags}
            return ctxt


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
