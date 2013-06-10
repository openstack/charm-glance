#
# Copyright 2012 Canonical Ltd.
#
# This file is sourced from lp:openstack-charm-helpers
#
# Authors:
#  James Page <james.page@ubuntu.com>
#  Adam Gandelman <adamg@ubuntu.com>
#

from utils import (
    relation_ids,
    relation_list,
    relation_get,
    unit_get,
    reload,
    render_template
    )
import os

HAPROXY_CONF = '/etc/haproxy/haproxy.cfg'
HAPROXY_DEFAULT = '/etc/default/haproxy'


def configure_haproxy(service_ports):
    '''
    Configure HAProxy based on the current peers in the service
    cluster using the provided port map:

        "swift": [ 8080, 8070 ]

    HAproxy will also be reloaded/started if required

    service_ports: dict: dict of lists of [ frontend, backend ]
    '''
    cluster_hosts = {}
    cluster_hosts[os.getenv('JUJU_UNIT_NAME').replace('/', '-')] = \
        unit_get('private-address')
    for r_id in relation_ids('cluster'):
        for unit in relation_list(r_id):
            cluster_hosts[unit.replace('/', '-')] = \
                relation_get(attribute='private-address',
                             rid=r_id,
                             unit=unit)
    context = {
        'units': cluster_hosts,
        'service_ports': service_ports
        }
    with open(HAPROXY_CONF, 'w') as f:
        f.write(render_template(os.path.basename(HAPROXY_CONF),
                                context))
    with open(HAPROXY_DEFAULT, 'w') as f:
        f.write('ENABLED=1')

    reload('haproxy')
