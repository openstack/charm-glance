#!/usr/bin/python
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

import sys

from subprocess import (
    call,
    check_call,
)

from glance_utils import (
    do_openstack_upgrade,
    git_install,
    migrate_database,
    register_configs,
    restart_map,
    services,
    CLUSTER_RES,
    determine_packages,
    SERVICES,
    CHARM,
    GLANCE_REGISTRY_CONF,
    GLANCE_API_CONF,
    HAPROXY_CONF,
    ceph_config_file,
    setup_ipv6,
    swift_temp_url_key,
    assess_status,
    reinstall_paste_ini,
    is_api_ready,
)
from charmhelpers.core.hookenv import (
    config,
    Hooks,
    log as juju_log,
    ERROR,
    open_port,
    is_relation_made,
    local_unit,
    relation_get,
    relation_set,
    relation_ids,
    related_units,
    service_name,
    UnregisteredHookError,
    status_set,
)

from charmhelpers.core.host import (
    # restart_on_change,
    service_reload,
    service_restart,
    service_stop,
)
from charmhelpers.fetch import (
    apt_install,
    apt_update,
    filter_installed_packages
)
from charmhelpers.contrib.hahelpers.cluster import (
    is_elected_leader,
    get_hacluster_config
)
from charmhelpers.contrib.openstack.ha.utils import (
    update_dns_ha_resource_params,
)
from charmhelpers.contrib.openstack.utils import (
    config_value_changed,
    configure_installation_source,
    git_install_requested,
    lsb_release,
    openstack_upgrade_available,
    os_release,
    sync_db_with_multi_ipv6_addresses,
    pausable_restart_on_change as restart_on_change,
    is_unit_paused_set,
    os_requires_version,
)
from charmhelpers.contrib.storage.linux.ceph import (
    send_request_if_needed,
    is_request_complete,
    ensure_ceph_keyring,
    CephBrokerRq,
    delete_keyring,
)
from charmhelpers.payload.execd import (
    execd_preinstall
)
from charmhelpers.contrib.network.ip import (
    get_address_in_network,
    get_netmask_for_address,
    get_iface_for_address,
    get_ipv6_addr,
    is_ipv6,
    get_relation_ip,
)
from charmhelpers.contrib.openstack.ip import (
    canonical_url,
    PUBLIC, INTERNAL, ADMIN
)
from charmhelpers.contrib.openstack.context import (
    ADDRESS_TYPES
)
from charmhelpers.contrib.charmsupport import nrpe
from charmhelpers.contrib.hardening.harden import harden


hooks = Hooks()
CONFIGS = register_configs()


@hooks.hook('install.real')
@harden()
def install_hook():
    status_set('maintenance', 'Executing pre-install')
    execd_preinstall()
    src = config('openstack-origin')
    if (lsb_release()['DISTRIB_CODENAME'] == 'precise' and
            src == 'distro'):
        src = 'cloud:precise-folsom'

    configure_installation_source(src)

    status_set('maintenance', 'Installing apt packages')
    apt_update(fatal=True)
    apt_install(determine_packages(), fatal=True)

    status_set('maintenance', 'Git install')
    git_install(config('openstack-origin-git'))

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
        sync_db_with_multi_ipv6_addresses(config('database'),
                                          config('database-user'))
    else:
        # Avoid churn check for access-network early
        access_network = None
        for unit in related_units():
            access_network = relation_get(unit=unit,
                                          attribute='access-network')
            if access_network:
                break
        host = get_relation_ip('shared-db', cidr_network=access_network)

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
    rel = os_release('glance-common')

    if 'shared-db' not in CONFIGS.complete_contexts():
        juju_log('shared-db relation incomplete. Peer not ready?')
        return

    CONFIGS.write(GLANCE_REGISTRY_CONF)
    # since folsom, a db connection setting in glance-api.conf is required.
    if rel != "essex":
        CONFIGS.write(GLANCE_API_CONF)

    if is_elected_leader(CLUSTER_RES):
        # Bugs 1353135 & 1187508. Dbs can appear to be ready before the units
        # acl entry has been added. So, if the db supports passing a list of
        # permitted units then check if we're in the list.
        allowed_units = relation_get('allowed_units')
        if allowed_units and local_unit() in allowed_units.split():
            if rel == "essex":
                status = call(['glance-manage', 'db_version'])
                if status != 0:
                    juju_log('Setting version_control to 0')
                    cmd = ["glance-manage", "version_control", "0"]
                    check_call(cmd)

            juju_log('Cluster leader, performing db sync')
            migrate_database()
        else:
            juju_log('allowed_units either not presented, or local unit '
                     'not in acl list: %s' % allowed_units)

    for rid in relation_ids('image-service'):
        image_service_joined(rid)


@hooks.hook('pgsql-db-relation-changed')
@restart_on_change(restart_map())
def pgsql_db_changed():
    rel = os_release('glance-common')

    if 'pgsql-db' not in CONFIGS.complete_contexts():
        juju_log('pgsql-db relation incomplete. Peer not ready?')
        return

    CONFIGS.write(GLANCE_REGISTRY_CONF)
    # since folsom, a db connection setting in glance-api.conf is required.
    if rel != "essex":
        CONFIGS.write(GLANCE_API_CONF)

    if is_elected_leader(CLUSTER_RES):
        if rel == "essex":
            status = call(['glance-manage', 'db_version'])
            if status != 0:
                juju_log('Setting version_control to 0')
                cmd = ["glance-manage", "version_control", "0"]
                check_call(cmd)

        juju_log('Cluster leader, performing db sync')
        migrate_database()

    for rid in relation_ids('image-service'):
        image_service_joined(rid)


@hooks.hook('image-service-relation-joined')
def image_service_joined(relation_id=None):
    relation_data = {
        'glance-api-server':
        "{}:9292".format(canonical_url(CONFIGS, INTERNAL))
    }

    if is_api_ready(CONFIGS):
        relation_data['glance-api-ready'] = 'yes'
    else:
        relation_data['glance-api-ready'] = 'no'

    juju_log("%s: image-service_joined: To peer glance-api-server=%s" %
             (CHARM, relation_data['glance-api-server']))

    if ('object-store' in CONFIGS.complete_contexts() and
       'identity-service' in CONFIGS.complete_contexts()):
        relation_data.update({
            'swift-temp-url-key': swift_temp_url_key(),
            'swift-container': 'glance'
        })

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

    [image_service_joined(rid) for rid in relation_ids('image-service')]

    CONFIGS.write(GLANCE_API_CONF)


@hooks.hook('ceph-relation-joined')
def ceph_joined():
    apt_install(['ceph-common', 'python-ceph'])


def get_ceph_request():
    service = service_name()
    rq = CephBrokerRq()
    replicas = config('ceph-osd-replication-count')
    weight = config('ceph-pool-weight')
    rq.add_op_create_pool(name=service, replica_count=replicas,
                          weight=weight, group='images')
    if config('restrict-ceph-pools'):
        rq.add_op_request_access_to_group(name="images",
                                          permission='rwx')
    return rq


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

    if is_request_complete(get_ceph_request()):
        juju_log('Request complete')
        CONFIGS.write(GLANCE_API_CONF)
        CONFIGS.write(ceph_config_file())
        # Ensure that glance-api is restarted since only now can we
        # guarantee that ceph resources are ready.
        # Don't restart if the unit is in maintenance mode
        if not is_unit_paused_set():
            service_restart('glance-api')
    else:
        send_request_if_needed(get_ceph_request())


@hooks.hook('ceph-relation-broken')
def ceph_broken():
    service = service_name()
    delete_keyring(service=service)
    CONFIGS.write_all()


@hooks.hook('identity-service-relation-joined')
def keystone_joined(relation_id=None):
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

    # Configure any object-store / swift relations now that we have an
    # identity-service
    if relation_ids('object-store'):
        object_store_joined()

    # possibly configure HTTPS for API and registry
    configure_https()

    for rid in relation_ids('image-service'):
        image_service_joined(rid)


@hooks.hook('config-changed')
@restart_on_change(restart_map(), stopstart=True)
@harden()
def config_changed():
    if config('prefer-ipv6'):
        setup_ipv6()
        status_set('maintenance', 'Sync DB')
        sync_db_with_multi_ipv6_addresses(config('database'),
                                          config('database-user'))

    if git_install_requested():
        if config_value_changed('openstack-origin-git'):
            status_set('maintenance', 'Running Git install')
            git_install(config('openstack-origin-git'))
    elif not config('action-managed-upgrade'):
        if openstack_upgrade_available('glance-common'):
            status_set('maintenance', 'Upgrading OpenStack release')
            do_openstack_upgrade(CONFIGS)

    open_port(9292)
    configure_https()

    update_nrpe_config()

    # Pickup and changes due to network reference architecture
    # configuration
    [keystone_joined(rid) for rid in relation_ids('identity-service')]
    [image_service_joined(rid) for rid in relation_ids('image-service')]
    [cluster_joined(rid) for rid in relation_ids('cluster')]
    for r_id in relation_ids('ha'):
        ha_relation_joined(relation_id=r_id)

    # NOTE(jamespage): trigger any configuration related changes
    #                  for cephx permissions restrictions
    ceph_changed()


@hooks.hook('cluster-relation-joined')
def cluster_joined(relation_id=None):
    for addr_type in ADDRESS_TYPES:
        address = get_address_in_network(
            config('os-{}-network'.format(addr_type))
        )
        if address:
            relation_set(
                relation_id=relation_id,
                relation_settings={'{}-address'.format(addr_type): address}
            )
    if config('prefer-ipv6'):
        private_addr = get_ipv6_addr(exc_list=[config('vip')])[0]
        relation_set(relation_id=relation_id,
                     relation_settings={'private-address': private_addr})


@hooks.hook('cluster-relation-changed')
@hooks.hook('cluster-relation-departed')
@restart_on_change(restart_map(), stopstart=True)
def cluster_changed():
    configure_https()
    CONFIGS.write(GLANCE_API_CONF)
    CONFIGS.write(HAPROXY_CONF)


@hooks.hook('upgrade-charm')
@restart_on_change(restart_map(), stopstart=True)
@harden()
def upgrade_charm():
    apt_install(filter_installed_packages(determine_packages()), fatal=True)
    reinstall_paste_ini()
    configure_https()
    update_nrpe_config()
    CONFIGS.write_all()


@hooks.hook('ha-relation-joined')
def ha_relation_joined(relation_id=None):
    cluster_config = get_hacluster_config()

    resources = {
        'res_glance_haproxy': 'lsb:haproxy'
    }

    resource_params = {
        'res_glance_haproxy': 'op monitor interval="5s"'
    }

    if config('dns-ha'):
        update_dns_ha_resource_params(relation_id=relation_id,
                                      resources=resources,
                                      resource_params=resource_params)
    else:
        vip_group = []
        for vip in cluster_config['vip'].split():
            if is_ipv6(vip):
                res_ks_vip = 'ocf:heartbeat:IPv6addr'
                vip_params = 'ipv6addr'
            else:
                res_ks_vip = 'ocf:heartbeat:IPaddr2'
                vip_params = 'ip'

            iface = (get_iface_for_address(vip) or
                     config('vip_iface'))
            netmask = (get_netmask_for_address(vip) or
                       config('vip_cidr'))

            if iface is not None:
                vip_key = 'res_glance_{}_vip'.format(iface)
                resources[vip_key] = res_ks_vip
                resource_params[vip_key] = (
                    'params {ip}="{vip}" cidr_netmask="{netmask}"'
                    ' nic="{iface}"'.format(ip=vip_params,
                                            vip=vip,
                                            iface=iface,
                                            netmask=netmask)
                )
                vip_group.append(vip_key)

        if len(vip_group) >= 1:
            relation_set(relation_id=relation_id,
                         groups={'grp_glance_vips': ' '.join(vip_group)})

    init_services = {
        'res_glance_haproxy': 'haproxy',
    }

    clones = {
        'cl_glance_haproxy': 'res_glance_haproxy',
    }

    relation_set(relation_id=relation_id,
                 init_services=init_services,
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

    # reconfigure endpoint in keystone to point to clustered VIP.
    [keystone_joined(rid) for rid in relation_ids('identity-service')]

    # notify glance client services of reconfigured URL.
    [image_service_joined(rid) for rid in relation_ids('image-service')]


@hooks.hook('identity-service-relation-broken',
            'object-store-relation-broken',
            'shared-db-relation-broken',
            'pgsql-db-relation-broken',
            'cinder-volume-service-relation-broken',
            'storage-backend-relation-broken')
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

    # TODO: improve this by checking if local CN certs are available
    # first then checking reload status (see LP #1433114).
    if not is_unit_paused_set():
        service_reload('apache2', restart_on_failure=True)

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


@hooks.hook('nrpe-external-master-relation-joined',
            'nrpe-external-master-relation-changed')
def update_nrpe_config():
    # python-dbus is used by check_upstart_job
    apt_install('python-dbus')
    hostname = nrpe.get_nagios_hostname()
    current_unit = nrpe.get_nagios_unit_name()
    nrpe_setup = nrpe.NRPE(hostname=hostname)
    nrpe.copy_nrpe_checks()
    nrpe.add_init_service_checks(nrpe_setup, services(), current_unit)
    nrpe.add_haproxy_checks(nrpe_setup, current_unit)
    nrpe_setup.write()


@hooks.hook('update-status')
@harden()
def update_status():
    juju_log('Updating status.')


def install_packages_for_cinder_store():
    optional_packages = ["python-cinderclient",
                         "python-os-brick",
                         "python-oslo.rootwrap"]
    apt_install(filter_installed_packages(optional_packages), fatal=True)


@hooks.hook('cinder-volume-service-relation-joined')
@os_requires_version('mitaka', 'glance-common')
@restart_on_change(restart_map(), stopstart=True)
def cinder_volume_service_relation_joined(relid=None):
    install_packages_for_cinder_store()
    CONFIGS.write_all()


@hooks.hook('storage-backend-relation-changed')
@os_requires_version('mitaka', 'glance-common')
@restart_on_change(restart_map(), stopstart=True)
def storage_backend_hook():
    if 'storage-backend' not in CONFIGS.complete_contexts():
        juju_log('storage-backend relation incomplete. Peer not ready?')
        return
    install_packages_for_cinder_store()
    CONFIGS.write(GLANCE_API_CONF)


if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        juju_log('Unknown hook {} - skipping.'.format(e))
    assess_status(CONFIGS)
