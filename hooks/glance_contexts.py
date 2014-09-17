from charmhelpers.core.hookenv import (
    is_relation_made,
    relation_ids,
    service_name,
    config,
    relation_get,
    related_units,
)

from charmhelpers.contrib.openstack.context import (
    OSContextGenerator,
    ApacheSSLContext as SSLContext,
)

from charmhelpers.contrib.hahelpers.cluster import (
    determine_apache_port,
    determine_api_port,
)

from charmhelpers.contrib.network.ip import (
    get_ipv6_addr,
    format_ipv6_addr,
)


class CephGlanceContext(OSContextGenerator):
    interfaces = ['ceph-glance']

    def __call__(self):
        """Used to generate template context to be added to glance-api.conf in
        the presence of a ceph relation.
        """
        if not is_relation_made(relation="ceph",
                                keys="key"):
            return {}
        service = service_name()
        return {
            # ensure_ceph_pool() creates pool based on service name.
            'rbd_pool': service,
            'rbd_user': service,
        }


class ObjectStoreContext(OSContextGenerator):
    interfaces = ['object-store']

    def __call__(self):
        """Object store config.
        Used to generate template context to be added to glance-api.conf in
        the presence of a 'object-store' relation.
        """
        if not relation_ids('object-store'):
            return {}
        return {
            'swift_store': True,
        }


class HAProxyContext(OSContextGenerator):
    interfaces = ['cluster']

    def __call__(self):
        '''Extends the main charmhelpers HAProxyContext with a port mapping
        specific to this charm.
        Also used to extend glance-api.conf context with correct bind_port
        '''
        haproxy_port = 9292
        apache_port = determine_apache_port(9292)
        api_port = determine_api_port(9292)

        ctxt = {
            'service_ports': {'glance_api': [haproxy_port, apache_port]},
            'bind_port': api_port,
        }
        return ctxt


class ApacheSSLContext(SSLContext):
    interfaces = ['https']
    external_ports = [9292]
    service_namespace = 'glance'

    def __call__(self):
        return super(ApacheSSLContext, self).__call__()


class LoggingConfigContext(OSContextGenerator):

    def __call__(self):
        return {'debug': config('debug'), 'verbose': config('verbose')}


class GlanceIPv6Context(OSContextGenerator):

    def __call__(self):
        ctxt = {}
        if config('prefer-ipv6'):
            ipv6_addr = get_ipv6_addr()
            ctxt['bind_host'] = ipv6_addr
            ctxt['registry_host'] = '[%s]' % ipv6_addr
            for rid in relation_ids('shared-db'):
                for unit in related_units(rid):
                    rdata = relation_get(rid=rid, unit=unit)
                    db_host = format_ipv6_addr(rdata.get('db_host'))
                    if db_host is not None:
                        ctxt['database_host'] = db_host
        else:
            ctxt['bind_host'] = '0.0.0.0'
            ctxt['registry_host'] = '0.0.0.0'
        return ctxt
