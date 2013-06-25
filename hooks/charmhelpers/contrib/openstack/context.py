from charmhelpers.core.hookenv import (
    config,
    local_unit,
    log,
    relation_get,
    relation_ids,
    related_units,
    unit_get,
)


class OSContextError(Exception):
    pass


def context_complete(ctxt):
    _missing = []
    for k, v in ctxt.iteritems():
        if v is None or v == '':
            _missing.append(k)
    if _missing:
        print 'Missing required data: %s' % ' '.join(_missing)
        return False
    return True


class OSContextGenerator(object):
    interfaces = []

    def __call__(self):
        raise NotImplementedError


class SharedDBContext(OSContextGenerator):
    interfaces = ['shared-db']

    def __call__(self):
        log('Generating template context for shared-db')
        conf = config()
        try:
            database = conf['database']
            username = conf['database-user']
        except KeyError as e:
            log('Could not generate shared_db context. '
                'Missing required charm config options: %s.' % e)
            raise OSContextError
        ctxt = {}
        for rid in relation_ids('shared-db'):
            for unit in related_units(rid):
                ctxt = {
                    'database_host': relation_get('db_host', rid=rid,
                                                  unit=unit),
                    'database': database,
                    'database_user': username,
                    'database_password': relation_get('password', rid=rid,
                                                      unit=unit)
                }
        if not context_complete(ctxt):
            return {}
        return ctxt


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
                    'admin_token': relation_get('admin_token', rid=rid,
                                                   unit=unit),
                    # XXX: Hard-coded http.
                    'service_protocol':  'http',
                    'auth_protocol':  'http',
                }
        if not context_complete(ctxt):
            return {}
        return ctxt


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
                    rabbitmq_host = relation_get('vip', rid=rid, unit=unit)
                else:
                    rabbitmq_host = relation_get('private-address',
                                                 rid=rid, unit=unit)
                ctxt = {
                    'rabbitmq_host': rabbitmq_host,
                    'rabbitmq_user': username,
                    'rabbitmq_password': relation_get('password', rid=rid,
                                                      unit=unit),
                    'rabbitmq_virtual_host': vhost,
                }
        if not context_complete(ctxt):
            return {}
        return ctxt


class CephContext(OSContextGenerator):
    interfaces = ['ceph']

    def __call__(self):
        '''This generates context for /etc/ceph/ceph.conf templates'''
        log('Generating tmeplate context for ceph')
        mon_hosts = []
        auth = None
        for rid in relation_ids('ceph'):
            for unit in related_units(rid):
                mon_hosts.append(relation_get('private-address', rid=rid,
                                              unit=unit))
                auth = relation_get('auth', rid=rid, unit=unit)

        ctxt = {
            'mon_hosts': ' '.join(mon_hosts),
            'auth': auth,
        }
        if not context_complete(ctxt):
            return {}
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
