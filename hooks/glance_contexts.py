from charmhelpers.core.hookenv import (
    config,
    relation_ids,
    service_name,
)

from charmhelpers.contrib.openstack.context import (
    OSContextGenerator
)

from charmhelpers.contrib.hahelpers.cluster_utils import (
    determine_api_port,
    determine_haproxy_port,
)


class CephContext(OSContextGenerator):
    interfaces = ['ceph']

    def __call__(self):
        """
        Used to generate template context to be added to glance-api.conf in
        the presence of a ceph relation.
        """
        if not relation_ids('ceph'):
            return {}
        service = service_name()
        return {
            # ensure_ceph_pool() creates pool based on service name.
            'rbd_pool': service,
            'rbd_user': service,
        }


class HAProxyContext(OSContextGenerator):
    interfaces = ['ceph']

    def __call__(self):
        '''
        Extends the main charmhelpers HAProxyContext with a port mapping
        specific to this charm.
        Also used to extend cinder.conf context with correct api_listening_port
        '''
        haproxy_port = determine_haproxy_port(config('api-listening-port'))
        api_port = determine_api_port(config('api-listening-port'))

        ctxt = {
            'service_ports': {'cinder_api': [haproxy_port, api_port]},
            'osapi_volume_listen_port': api_port,
        }
        return ctxt
