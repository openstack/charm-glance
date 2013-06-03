#!/usr/bin/python
import shutil
import sys
import time
import os

from lib.cluster_utils import (
    https,
    peer_units,
    determine_haproxy_port,
    determine_api_port,
    eligible_leader,
    )

from lib.utils import (
    juju_log,
    start,
    stop,
    restart,
    unit_get,
    relation_set,
    relation_ids,
    relation_list,
    install,
    )

from lib.haproxy_utils import (
    configure_haproxy,
    )

#TODO: Port glance-common to Python
from lib.glance_common import (
    set_or_update,
    configure_https,
    )

from lib.openstack_common import (
    get_os_codename_package,
    get_os_codename_install_source,
    get_os_version_codename,
    save_script_rc,
    )

packages = [
    "glance", "python-mysqldb", "python-swift",
    " python-keystone", "uuid", "haproxy",
    ]

services = [
    "glance-api", "glance-registry",
    ]

charm = "glance"
SERVICE_NAME = os.getenv('JUJU_UNIT_NAME').split('/')[0]

config=json.loads(subprocess.check_output(['config-get','--format=json']))


def install_hook():
    juju_log("Installing glance packages")
    configure_source()

    install(*packages)

    stop(*services)

    # TODO:
    # set_or_update verbose True api
    # set_or_update debug True api
    # set_or_update verbose True registry
    # set_or_update debug True registry
    # set_or_update()

    configure_https()


def db_joined():
    relation_data = {
        'database': config["glance-db"],
        'username': config["db-user"],
        'hostname': unit_get('private-address')
        }

    #juju-log "$CHARM - db_joined: requesting database access to $glance_db for "\
    #       "$db_user@$hostname"
    relation_set(**relation_data)


def db_changed(rid=None):
    relation_data = relation_get_dict(relation_id=rid)
    if ('password' not in relation_data or
        'db_host' not in relation_data):
        juju_log('INFO',
                 'db_host or password not set. Peer not ready, exit 0')
        sys.exit(0)

    db_user = relation_data["glance-db"]
    db_user = relation_data["db-user"]
    rel = get_os_codename_package("glance-common")

    # TODO:
    # set_or_update sql_connection "mysql://$db_user:$db_password@$db_host/$glance_db" registry

    if rel != "essex":
        # TODO:
        # set_or_update sql_connection "mysql://$db_user:$db_password@$db_host/$glance_db" api

    if eligible_leader("res_glance_vip"):
        if rel == "essex":
            if not check_output(['glance-manage', 'db_version']):
                juju_log("INFO", "Setting flance database version to 0")
                check_call(["glance-manage", "version_control", "0"])

        juju_log("INFO", "%s - db_changed: Running database migrations for $rel." % (charm, rel))
        check_call(["glance-manage", "db_sync"])

    restart(services)


def image-service_joined(relation_id=None):

    if not eligible_leader("res_glance_vip"):
        return
    scheme="http"
    if https():
        scheme="https"
    host = unit_get('private-address')
    if is_clustered():
        host = config["vip"]

    relation_data = {
        'glance-api-server': "%s://%s:9292" % (scheme, host),
        }

    if relation_id:
        relation_data['rid'] = relation_id

    juju_log("%s: image-service_joined: To peer glance-api-server=%s" % (charm, relation_data['glance-api-server']))

    relation_set(**relation_data)


def object-store_joined():
    relids = relation_ids('identity-service')

    if not relids:
        juju_log('INFO', 'Deferring swift stora configuration until ' \
                         'an identity-service relation exists')
        return

    #TODO:
    # set_or_update default_store swift api
    # set_or_update swift_store_create_container_on_put true api
    set_or_update()

    for rid in relids:
        for unit in relation_list(rid=rid):
            svc_tenant = relation_get(attribute='service_tenant', rid=rid, unit=unit)
            svc_username = relation_get(attribute='service_username', rid=rid, unit=unit)
            svc_password = relation_get(attribute='service_passwod', rid=rid, unit=unit)
            auth_host = relation_get(attribute='private-address', rid=rid, unit=unit)
            port = relation_get(attribute='service_port', rid=rid, unit=unit)

            if auth_host and port:
                auth_url = "http://%s:%s/v2.0" % (auth_host, port)
            if svc_tenant and svc_username:
                #TODO
                # set_or_update swift_store_user "$svc_tenant:$svc_username" api
            if svc_password:
                # TODO:
                # set_or_update swift_store_key "$svc_password" api
            if auth_url:
                # TODO:
                # set_or_update swift_store_auth_address "$auth_url" api

    restart(['glance-api'])


def object-store_changed():
    pass


def ceph_joined():
    os.mkdir('/etc/ceph')
    install(['ceph-common', 'python-ceph'])


def ceph_changed(rid=None, unit=None):
    key = relation_get(attribute='key', rid=rid, unit=unit)
    auth = relation_get(attribute='auth', rid=rid, unit=unit)

    if None in [auth, key]:
        utils.juju_log('INFO', 'Missing key or auth in relation')
        return

    ceph.configure(service=SERVICE_NAME, key=key, auth=auth)

    # Configure glance for ceph storage options
    # TODO:
    # set_or_update default_store rbd api
    # set_or_update rbd_store_ceph_conf /etc/ceph/ceph.conf api
    # set_or_update rbd_store_user $SERVICE_NAME api
    # set_or_update rbd_store_pool images api
    # set_or_update rbd_store_chunk_size 8 api
    restart('glance-api')


def keystone_joined(relation_id=None):
    if not eligible_leader('res_glance_vip'):
        juju_log('INFO',
                 'Deferring keystone_joined() to service leader.')
        return

    scheme = "http"
    if https():
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
        'internal_url': url,
        }

    if relation_id:
        relation_data['rid'] = relation_id

    relation_set(**relation_data)


def keystone_changed(rid=None):
    relation_data = relation_get_dict(relation_id=rid)

    token = relation_data["admin_token"]
    service_port = relation_data["service_port"]
    auth_port = relation_data["auth_port"]
    service_username = relation_data["service_username"]
    service_password = relation_data["service_password"]
    service_tenant = relation_data["service_tenant"]

    if not token or not service_port or not auth_port or \
        not service_username or not service_password or not service_tenant:
        juju_log('INFO', 'keystone_changed: Peer not ready')
        sys.exit(0)

    if token == "-1":
        juju_log('ERROR', 'keystone_changed: admin token error')
        sys.exit(1)
    juju_log('INFO', 'keystone_changed: Acquired admin token')

    # TODO:
    # set_or_update "flavor" "keystone" "api" "paste_deploy"
    # set_or_update "flavor" "keystone" "registry" "paste_deploy"

    # TODO:
    # local sect="filter:authtoken"
    # for i in api-paste registry-paste ; do
    #    set_or_update "service_host" "$keystone_host" $i $sect
    #    set_or_update "service_port" "$service_port" $i $sect
    #    set_or_update "auth_host" "$keystone_host" $i $sect
    #    set_or_update "auth_port" "$auth_port" $i $sect
    #    set_or_update "auth_uri" "http://$keystone_host:$service_port/" $i $sect
    #    set_or_update "admin_token" "$token" $i $sect
    #    set_or_update "admin_tenant_name" "$service_tenant" $i $sect
    #    set_or_update "admin_user" "$service_username" $i $sect
    #    set_or_update "admin_password" "$service_password" $i $sect
    # done

    restart(services)

    # Configure any object-store / swift relations now that we have an
    # identity-service
    if relation_ids('object-store'):
        object-store_joined()

    # possibly configure HTTPS for API and registry
    configure_https()


def config_changed():
  # Determine whether or not we should do an upgrade, based on whether or not
  # the version offered in openstack-origin is greater than what is installed.
    cur = get_os_codename_package("glance-common")
    available = get_os_codename_install_source(config["openstack-origin"])

    if (available and
        get_os_version_codename(available) > \
            get_os_version_codename(installed)):
        juju_log('INFO', '%s: Upgrading OpenStack release: %s -> %s' % (charm, cur, available))
        # TODO: do_openstack_upgrade_function: where does it come from?
        do_openstack_upgrade(config["openstack-origin"], ' '.join(packages))

    configure_https()
    restart(services)

    env_vars = {'OPENSTACK_PORT_MCASTPORT': config["ha-mcastport"],
                'OPENSTACK_SERVICE_API': "glance-api"),
                'OPENSTACK_SERVICE_REGISTRY': "glance-registry"}
    save_script_rc(**env_vars)


def cluster_changed():
    if not peer_units():
        juju_log('INFO', '%s: cluster_change() with no peers.' % charm)
        sys.exit(0)
    haproxy_port = determine_haproxy_port('9292')
    backend_port = determine_api_port('9292')
    stop('glance-api')
    configure_haproxy("glance_api:%s:%s" % (haproxy_port, backend_port))
    # TODO: glance-common should be ported to python too to have this
    # function working
    # set_or_update bind_port "$backend_port" "api"
    set_or_update()
    start('glance-api')

def upgrade_charm():
    cluster_changed()

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
        'res_glance_haproxy': 'lsb:haproxy',
        }

    resource_params = {
        'res_glance_vip': 'params ip="%s" cidr_netmask="%s" nic="%s"' % \
                          (vip, vip_cidr, vip_iface),
        'res_glance_haproxy': 'op monitor interval="5s"',
        }

    init_services = {
        'res_glance_haproxy': 'haproxy',
        }

    clones = {
        'cl_glance_haproxy': 'res_glance_haproxy',
        }

    relation_set(init_services=init_services,
                 corosync_bindiface=corosync_bindiface,
                 corosync_mcastport=corosync_mcastport,
                 resources=resources,
                 resource_params=resource_params,
                 clones=clones)


def ha_relation_changed():
    relation_data = relation_get_dict()
    if ('clustered' in relation_data and
        is_leader()):
        host = config["vip"]
        if https():
            scheme = "https"
        else
            scheme = "http"
        url = "%s://%s:9292" % (scheme, host)
        juju_log('INFO', '%s: Cluster configured, notifying other services' % charm)
        # Tell all related services to start using
        # the VIP
        # TODO: recommendations by adam_g
        # TODO: could be further simpllfiied by letting keystone_joined()
        # and image-service_joined() take parameters of relation_id
        # then just call keystone_joined(r_id) + image-service_joined(r_d)
        for r_id in relation_ids('identity-service'):
            relation_set(rid=r_id,
                         service="glance",
                         region=config["region"],
                         public_url=url,
                         admin_url=url,
                         internal_url=url)

        for r_id in relation_ids('image-service'):
            relation_set(rid=r_id,
                         glance-api-server=url)

def exit():
    sys.exit(0)

hooks = {
  'start': start
  'stop': service_ctl all $ARG0 ;;
  'install': install_hook,
  'config-changed': config_changed,
  'shared-db-relation-joined': db_joined,
  'shared-db-relation-changed': db_changed,
  'image-service-relation-joined': image-service_joined,
  'image-service-relation-changed': exit, # do we need it?
  'object-store-relation-joined': object-store_joined,
  'object-store-relation-changed': object-store_changed,
  'identity-service-relation-joined': keystone_joined,
  'identity-service-relation-changed': keystone_changed,
  'ceph-relation-joined': ceph_joined,
  'ceph-relation-changed': ceph_changed,
  'cluster-relation-changed': cluster_changed,
  'cluster-relation-departed': cluster_changed,
  'ha-relation-joined': ha_relation_joined,
  'ha-relation-changed': ha_relation_changed,
  'upgrade-charm': upgrade_charm,
}

utils.do_hooks(hooks)
