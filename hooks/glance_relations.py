#!/usr/bin/python
import sys

from glance_utils import (
    do_openstack_upgrade,
    ensure_ceph_pool,
    migrate_database,
    register_configs,
    restart_map,
    CLUSTER_RES,
    PACKAGES,
    SERVICES,
    CHARM,
    GLANCE_REGISTRY_CONF,
    GLANCE_REGISTRY_PASTE_INI,
    GLANCE_API_CONF,
    GLANCE_API_PASTE_INI,
    HAPROXY_CONF,
    ceph_config_file)

from charmhelpers.core.hookenv import (
    config,
    Hooks,
    log as juju_log,
    ERROR,
    open_port,
    is_relation_made,
    relation_get,
    relation_set,
    relation_ids,
    service_name,
    unit_get,
    UnregisteredHookError, )

from charmhelpers.core.host import (
    restart_on_change,
    service_stop
)

from charmhelpers.fetch import (
    apt_install,
    apt_update,
    filter_installed_packages,
    add_source
)

from charmhelpers.contrib.hahelpers.cluster import (
    eligible_leader,
    get_hacluster_config
)

from charmhelpers.contrib.openstack.utils import (
    configure_installation_source,
    get_os_codename_package,
    openstack_upgrade_available,
    lsb_release, )

from charmhelpers.contrib.storage.linux.ceph import ensure_ceph_keyring
from charmhelpers.payload.execd import execd_preinstall
from charmhelpers.contrib.network.ip import (
    get_address_in_network,
    get_netmask_for_address,
    get_iface_for_address,
    get_ipv6_addr,
)
from charmhelpers.contrib.openstack.ip import (
    canonical_url,
    PUBLIC, INTERNAL, ADMIN
)
from charmhelpers.contrib.peerstorage import peer_store

from subprocess import (
    check_call,
    call, )

hooks = Hooks()

CONFIGS = register_configs()


@hooks.hook('install')
def install_hook():
    juju_log('Installing glance packages')
    execd_preinstall()
    src = config('openstack-origin')
    if (lsb_release()['DISTRIB_CODENAME'] == 'precise' and
            src == 'distro'):
        src = 'cloud:precise-folsom'

    configure_installation_source(src)

    # Note(xianghui): Need to install haproxy(1.5.3) from trusty-backports
    # to support ipv6 address, so check is required to make sure not
    # breaking other versions.
    trusty = lsb_release()['DISTRIB_CODENAME'] == 'trusty'
    if config('prefer-ipv6') and trusty:
        add_source('deb http://archive.ubuntu.com/ubuntu trusty-backports'
                   ' main')
        add_source('deb-src http://archive.ubuntu.com/ubuntu trusty-backports'
                   ' main')

    apt_update(fatal=True)
    apt_install(PACKAGES, fatal=True)

    if config('prefer-ipv6') and trusty:
        apt_install('haproxy/trusty-backports', fatal=True)

    for service in SERVICES:
        service_stop(service)


@hooks.hook('shared-db-relation-joined')
def db_joined():
    if is_relation_made('pgsql-db'):
        # error, postgresql is used
        e = ('Attempting to associate a mysql database when there is already '
             'associated a postgresql one')
        juju_log(e, level=ERROR)
        raise Exception(e)
    if config('prefer-ipv6'):
        host = get_ipv6_addr()
    else:
        host = unit_get('private-address')

    relation_set(database=config('database'),
                 username=config('database-user'),
                 hostname=host)


@hooks.hook('pgsql-db-relation-joined')
def pgsql_db_joined():
    if is_relation_made('shared-db'):
        # raise error
        e = ('Attempting to associate a postgresql database when'
             ' there is already associated a mysql one')
        juju_log(e, level=ERROR)
        raise Exception(e)

    relation_set(database=config('database'))


@hooks.hook('shared-db-relation-changed')
@restart_on_change(restart_map())
def db_changed():
    rel = get_os_codename_package("glance-common")

    if 'shared-db' not in CONFIGS.complete_contexts():
        juju_log('shared-db relation incomplete. Peer not ready?')
        return

    CONFIGS.write(GLANCE_REGISTRY_CONF)
    # since folsom, a db connection setting in glance-api.conf is required.
    if rel != "essex":
        CONFIGS.write(GLANCE_API_CONF)

    if eligible_leader(CLUSTER_RES):
        if rel == "essex":
            status = call(['glance-manage', 'db_version'])
            if status != 0:
                juju_log('Setting version_control to 0')
                check_call(["glance-manage", "version_control", "0"])

        juju_log('Cluster leader, performing db sync')
        migrate_database()


@hooks.hook('pgsql-db-relation-changed')
@restart_on_change(restart_map())
def pgsql_db_changed():
    rel = get_os_codename_package("glance-common")

    if 'pgsql-db' not in CONFIGS.complete_contexts():
        juju_log('pgsql-db relation incomplete. Peer not ready?')
        return

    CONFIGS.write(GLANCE_REGISTRY_CONF)
    # since folsom, a db connection setting in glance-api.conf is required.
    if rel != "essex":
        CONFIGS.write(GLANCE_API_CONF)

    if eligible_leader(CLUSTER_RES):
        if rel == "essex":
            status = call(['glance-manage', 'db_version'])
            if status != 0:
                juju_log('Setting version_control to 0')
                check_call(["glance-manage", "version_control", "0"])

        juju_log('Cluster leader, performing db sync')
        migrate_database()


@hooks.hook('image-service-relation-joined')
def image_service_joined(relation_id=None):
    if not eligible_leader(CLUSTER_RES):
        return

    relation_data = {
        'glance-api-server':
        "{}:9292".format(canonical_url(CONFIGS, INTERNAL))
    }

    juju_log("%s: image-service_joined: To peer glance-api-server=%s" %
             (CHARM, relation_data['glance-api-server']))

    relation_set(relation_id=relation_id, **relation_data)


@hooks.hook('object-store-relation-joined')
@restart_on_change(restart_map())
def object_store_joined():

    if 'identity-service' not in CONFIGS.complete_contexts():
        juju_log('Deferring swift storage configuration until '
                 'an identity-service relation exists')
        return

    if 'object-store' not in CONFIGS.complete_contexts():
        juju_log('swift relation incomplete')
        return

    CONFIGS.write(GLANCE_API_CONF)


@hooks.hook('ceph-relation-joined')
def ceph_joined():
    apt_install(['ceph-common', 'python-ceph'])


@hooks.hook('ceph-relation-changed')
@restart_on_change(restart_map())
def ceph_changed():
    if 'ceph' not in CONFIGS.complete_contexts():
        juju_log('ceph relation incomplete. Peer not ready?')
        return

    service = service_name()

    if not ensure_ceph_keyring(service=service,
                               user='glance', group='glance'):
        juju_log('Could not create ceph keyring: peer not ready?')
        return

    CONFIGS.write(GLANCE_API_CONF)
    CONFIGS.write(ceph_config_file())

    if eligible_leader(CLUSTER_RES):
        _config = config()
        ensure_ceph_pool(service=service,
                         replicas=_config['ceph-osd-replication-count'])


@hooks.hook('identity-service-relation-joined')
def keystone_joined(relation_id=None):
    if not eligible_leader(CLUSTER_RES):
        juju_log('Deferring keystone_joined() to service leader.')
        return

    public_url = '{}:9292'.format(canonical_url(CONFIGS, PUBLIC))
    internal_url = '{}:9292'.format(canonical_url(CONFIGS, INTERNAL))
    admin_url = '{}:9292'.format(canonical_url(CONFIGS, ADMIN))
    relation_data = {
        'service': 'glance',
        'region': config('region'),
        'public_url': public_url,
        'admin_url': admin_url,
        'internal_url': internal_url, }

    relation_set(relation_id=relation_id, **relation_data)


@hooks.hook('identity-service-relation-changed')
@restart_on_change(restart_map())
def keystone_changed():
    if 'identity-service' not in CONFIGS.complete_contexts():
        juju_log('identity-service relation incomplete. Peer not ready?')
        return

    CONFIGS.write(GLANCE_API_CONF)
    CONFIGS.write(GLANCE_REGISTRY_CONF)

    CONFIGS.write(GLANCE_API_PASTE_INI)
    CONFIGS.write(GLANCE_REGISTRY_PASTE_INI)

    # Configure any object-store / swift relations now that we have an
    # identity-service
    if relation_ids('object-store'):
        object_store_joined()

    # possibly configure HTTPS for API and registry
    configure_https()


@hooks.hook('config-changed')
@restart_on_change(restart_map(), stopstart=True)
def config_changed():
    if openstack_upgrade_available('glance-common'):
        juju_log('Upgrading OpenStack release')
        do_openstack_upgrade(CONFIGS)

    open_port(9292)
    configure_https()

    # Pickup and changes due to network reference architecture
    # configuration
    [keystone_joined(rid) for rid in relation_ids('identity-service')]
    [image_service_joined(rid) for rid in relation_ids('image-service')]
    [cluster_joined(rid) for rid in relation_ids('cluster')]


@hooks.hook('cluster-relation-joined')
def cluster_joined(relation_id=None):
    address = get_address_in_network(config('os-internal-network'),
                                     unit_get('private-address'))
    relation_set(relation_id=relation_id,
                 relation_settings={'private-address': address})


@hooks.hook('cluster-relation-changed')
@restart_on_change(restart_map(), stopstart=True)
def cluster_changed():
    if config('prefer-ipv6'):
        peer_store('private-address', get_ipv6_addr())
    configure_https()
    CONFIGS.write(GLANCE_API_CONF)
    CONFIGS.write(HAPROXY_CONF)


@hooks.hook('upgrade-charm')
@restart_on_change(restart_map(), stopstart=True)
def upgrade_charm():
    apt_install(filter_installed_packages(PACKAGES), fatal=True)
    configure_https()
    CONFIGS.write_all()


@hooks.hook('ha-relation-joined')
def ha_relation_joined():
    cluster_config = get_hacluster_config()

    if config('prefer-ipv6'):
        res_ks_vip = 'ocf:heartbeat:IPv6addr'
        vip_params = 'ipv6addr'
    else:
        res_ks_vip = 'ocf:heartbeat:IPaddr2'
        vip_params = 'ip'

    resources = {
        'res_glance_haproxy': 'lsb:haproxy'
    }

    resource_params = {
        'res_glance_haproxy': 'op monitor interval="5s"'
    }

    vip_group = []
    for vip in cluster_config['vip'].split():
        iface = get_iface_for_address(vip)
        if iface is not None:
            vip_key = 'res_glance_{}_vip'.format(iface)
            resources[vip_key] = res_ks_vip
            resource_params[vip_key] = (
                'params {ip}="{vip}" cidr_netmask="{netmask}"'
                ' nic="{iface}"'.format(ip=vip_params,
                                        vip=vip,
                                        iface=iface,
                                        netmask=get_netmask_for_address(vip))
            )
            vip_group.append(vip_key)

    #if len(vip_group) > 1:
    relation_set(groups={'grp_glance_vips': ' '.join(vip_group)})

    init_services = {
        'res_glance_haproxy': 'haproxy',
    }

    clones = {
        'cl_glance_haproxy': 'res_glance_haproxy',
    }

    relation_set(init_services=init_services,
                 corosync_bindiface=cluster_config['ha-bindiface'],
                 corosync_mcastport=cluster_config['ha-mcastport'],
                 resources=resources,
                 resource_params=resource_params,
                 clones=clones)


@hooks.hook('ha-relation-changed')
def ha_relation_changed():
    clustered = relation_get('clustered')
    if not clustered or clustered in [None, 'None', '']:
        juju_log('ha_changed: hacluster subordinate is not fully clustered.')
        return
    if not eligible_leader(CLUSTER_RES):
        juju_log('ha_changed: hacluster complete but we are not leader.')
        return

    # reconfigure endpoint in keystone to point to clustered VIP.
    [keystone_joined(rid) for rid in relation_ids('identity-service')]

    # notify glance client services of reconfigured URL.
    [image_service_joined(rid) for rid in relation_ids('image-service')]


@hooks.hook('ceph-relation-broken',
            'identity-service-relation-broken',
            'object-store-relation-broken',
            'shared-db-relation-broken',
            'pgsql-db-relation-broken')
def relation_broken():
    CONFIGS.write_all()


def configure_https():
    '''Enables SSL API Apache config if appropriate and kicks
    identity-service and image-service with any required
    updates
    '''
    CONFIGS.write_all()
    if 'https' in CONFIGS.complete_contexts():
        cmd = ['a2ensite', 'openstack_https_frontend']
        check_call(cmd)
    else:
        cmd = ['a2dissite', 'openstack_https_frontend']
        check_call(cmd)

    for r_id in relation_ids('identity-service'):
        keystone_joined(relation_id=r_id)
    for r_id in relation_ids('image-service'):
        image_service_joined(relation_id=r_id)


@hooks.hook('amqp-relation-joined')
def amqp_joined():
    conf = config()
    relation_set(username=conf['rabbit-user'], vhost=conf['rabbit-vhost'])


@hooks.hook('amqp-relation-changed')
@restart_on_change(restart_map())
def amqp_changed():
    if 'amqp' not in CONFIGS.complete_contexts():
        juju_log('amqp relation incomplete. Peer not ready?')
        return
    CONFIGS.write(GLANCE_API_CONF)

if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        juju_log('Unknown hook {} - skipping.'.format(e))
