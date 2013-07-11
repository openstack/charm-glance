#!/usr/bin/python
import os
import sys

from glance_utils import (
    do_openstack_upgrade,
    ensure_ceph_keyring,
    ensure_ceph_pool,
    migrate_database,
    register_configs,
    restart_map,
    CLUSTER_RES,
    PACKAGES,
    SERVICES,
    CHARM,
    SERVICE_NAME,
    GLANCE_REGISTRY_CONF,
    GLANCE_REGISTRY_PASTE_INI,
    GLANCE_API_CONF,
    GLANCE_API_PASTE_INI,
    HAPROXY_CONF,
    CEPH_CONF, )

from charmhelpers.core.hookenv import (
    config as charm_conf,
    Hooks,
    log as juju_log,
    relation_get,
    relation_set,
    relation_ids,
    unit_get,
    UnregisteredHookError, )

from charmhelpers.core.host import (
    restart_on_change,
    apt_install,
    apt_update,
    service_stop, )

from charmhelpers.contrib.hahelpers.cluster_utils import (
    eligible_leader,
    is_clustered, )

from charmhelpers.contrib.openstack.openstack_utils import (
    configure_installation_source,
    get_os_codename_package,
    get_os_codename_install_source,
    get_os_version_codename,
    save_script_rc,
    lsb_release, )

from subprocess import (
    check_call, )

from commands import getstatusoutput

hooks = Hooks()

CONFIGS = register_configs()

config = charm_conf()

@hooks.hook('install')
def install_hook():
    juju_log('Installing glance packages')

    src = config['openstack-origin']
    if (lsb_release()['DISTRIB_CODENAME'] == 'precise' and
       src == 'distro'):
        src = 'cloud:precise-folsom'

    configure_installation_source(src)

    apt_update()
    apt_install(PACKAGES)

    for service in SERVICES:
        service_stop(service)

    configure_https()


@hooks.hook('shared-db-relation-joined')
def db_joined():
    relation_set(database=config['database'], username=config['database-user'],
                 hostname=unit_get('private-address'))


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
            (status, output) = getstatusoutput('glance-manage db_version')
            if status != 0:
                juju_log('Setting version_control to 0')
                check_call(["glance-manage", "version_control", "0"])

        juju_log('Cluster leader, performing db sync')
        migrate_database()


@hooks.hook('image-service-relation-joined')
def image_service_joined(relation_id=None):

    if not eligible_leader(CLUSTER_RES):
        return

    scheme = "http"
    if 'https' in CONFIGS.complete_contexts():
        scheme = "https"

    host = unit_get('private-address')
    if is_clustered():
        host = config["vip"]

    relation_data = {
        'glance-api-server': "%s://%s:9292" % (scheme, host), }

    juju_log("%s: image-service_joined: To peer glance-api-server=%s" %
             (CHARM, relation_data['glance-api-server']))

    relation_set(relation_id=relation_id, **relation_data)


@hooks.hook('object-store-relation-joined')
@restart_on_change(restart_map())
def object_store_joined():

    if 'identity-service' not in CONFIGS.complete_contexts():
        juju_log('Deferring swift stora configuration until '
                 'an identity-service relation exists')
        return

    if 'object-store' not in CONFIGS.complete_contexts():
        juju_log('swift relation incomplete')
        return

    CONFIGS.write(GLANCE_API_CONF)


@hooks.hook('ceph-relation-joined')
def ceph_joined():
    if not os.path.isdir('/etc/ceph'):
        os.mkdir('/etc/ceph')
    apt_install(['ceph-common', 'python-ceph'])


@hooks.hook('ceph-relation-changed')
@restart_on_change(restart_map())
def ceph_changed():
    if 'ceph' not in CONFIGS.complete_contexts():
        juju_log('ceph relation incomplete. Peer not ready?')
        return

    if not ensure_ceph_keyring(service=SERVICE_NAME):
        juju_log('Could not create ceph keyring: peer not ready?')
        return

    CONFIGS.write(GLANCE_API_CONF)
    CONFIGS.write(CEPH_CONF)

    if eligible_leader(CLUSTER_RES):
        ensure_ceph_pool(service=SERVICE_NAME)


@hooks.hook('identity-service-relation-joined')
def keystone_joined(relation_id=None):
    if not eligible_leader(CLUSTER_RES):
        juju_log('Deferring keystone_joined() to service leader.')
        return

    scheme = "http"
    if 'https' in CONFIGS.complete_contexts():
        scheme = "https"

    host = unit_get('private-address')
    if is_clustered():
        host = config["vip"]

    url = "%s://%s:9292" % (scheme, host)

    relation_data = {
        'service': 'glance',
        'region': config['region'],
        'public_url': url,
        'admin_url': url,
        'internal_url': url, }

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
@restart_on_change(restart_map())
def config_changed():
    # Determine whether or not we should do an upgrade, based on whether or not
    # the version offered in openstack-origin is greater than what is installed
    install_src = config["openstack-origin"]
    available = get_os_codename_install_source(install_src)
    installed = get_os_codename_package("glance-common")

    if (available and
       get_os_version_codename(available) >
       get_os_version_codename(installed)):
        juju_log('%s: Upgrading OpenStack release: %s -> %s' %
                 (CHARM, installed, available))
        do_openstack_upgrade(CONFIGS)

    configure_https()

    env_vars = {'OPENSTACK_PORT_MCASTPORT': config["ha-mcastport"],
                'OPENSTACK_SERVICE_API': "glance-api",
                'OPENSTACK_SERVICE_REGISTRY': "glance-registry"}
    save_script_rc(**env_vars)


@hooks.hook('cluster-relation-changed')
@restart_on_change(restart_map())
def cluster_changed():
    CONFIGS.write(GLANCE_API_CONF)
    CONFIGS.write(HAPROXY_CONF)


@hooks.hook('upgrade-charm')
def upgrade_charm():
    cluster_changed()


@hooks.hook('ha-relation-joined')
def ha_relation_joined():
    corosync_bindiface = config["ha-bindiface"]
    corosync_mcastport = config["ha-mcastport"]
    vip = config["vip"]
    vip_iface = config["vip_iface"]
    vip_cidr = config["vip_cidr"]

    #if vip and vip_iface and vip_cidr and \
    #    corosync_bindiface and corosync_mcastport:

    resources = {
        'res_glance_vip': 'ocf:heartbeat:IPaddr2',
        'res_glance_haproxy': 'lsb:haproxy', }

    resource_params = {
        'res_glance_vip': 'params ip="%s" cidr_netmask="%s" nic="%s"' %
                          (vip, vip_cidr, vip_iface),
        'res_glance_haproxy': 'op monitor interval="5s"', }

    init_services = {
        'res_glance_haproxy': 'haproxy', }

    clones = {
        'cl_glance_haproxy': 'res_glance_haproxy', }

    relation_set(init_services=init_services,
                 corosync_bindiface=corosync_bindiface,
                 corosync_mcastport=corosync_mcastport,
                 resources=resources,
                 resource_params=resource_params,
                 clones=clones)


@hooks.hook('ha-relation-changed')
def ha_relation_changed():
    if not relation_get('clustered'):
        juju_log('glance subordinate is not fully clustered.')
        return
    if eligible_leader(CLUSTER_RES):
        host = config["vip"]
        scheme = "http"
        if 'https' in CONFIGS.complete_contexts():
            scheme = "https"
        url = "%s://%s:9292" % (scheme, host)
        juju_log('%s: Cluster configured, notifying other services' % CHARM)

        for r_id in relation_ids('identity-service'):
            relation_set(relation_id=r_id,
                         service="glance",
                         region=config["region"],
                         public_url=url,
                         admin_url=url,
                         internal_url=url)

        for r_id in relation_ids('image-service'):
            relation_data = {
                'glance-api-server': url, }
            relation_set(relation_id=r_id, **relation_data)


def configure_https():
    '''
    Enables SSL API Apache config if appropriate and kicks
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
        return

    for r_id in relation_ids('identity-service'):
        keystone_joined(relation_id=r_id)
    for r_id in relation_ids('image-service'):
        image_service_joined(relation_id=r_id)


if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        juju_log('Unknown hook {} - skiping.'.format(e))
