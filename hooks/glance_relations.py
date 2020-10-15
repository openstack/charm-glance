#!/usr/bin/env python3
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

import os
import sys

_path = os.path.dirname(os.path.realpath(__file__))
_parent = os.path.abspath(os.path.join(_path, ".."))


def _add_path(path):
    if path not in sys.path:
        sys.path.insert(1, path)


_add_path(_parent)


from subprocess import (
    call,
    check_call,
)

from glance_utils import (
    do_openstack_upgrade,
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
    assess_status,
    reinstall_paste_ini,
    is_api_ready,
    update_image_location_policy,
    pause_unit_helper,
    resume_unit_helper,
    remove_old_packages,
    deprecated_services,
    get_ceph_request,
)
from charmhelpers.core.hookenv import (
    charm_dir,
    config,
    Hooks,
    log as juju_log,
    DEBUG,
    open_port,
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
    is_clustered,
    is_elected_leader,
)
from charmhelpers.contrib.openstack.ha.utils import (
    generate_ha_relation_data,
)
from charmhelpers.contrib.openstack.utils import (
    configure_installation_source,
    lsb_release,
    openstack_upgrade_available,
    os_release,
    sync_db_with_multi_ipv6_addresses,
    pausable_restart_on_change as restart_on_change,
    is_unit_paused_set,
    os_requires_version,
    series_upgrade_prepare,
    series_upgrade_complete,
    CompareOpenStackReleases,
    is_db_initialised,
    is_db_maintenance_mode,
)
from charmhelpers.contrib.storage.linux.ceph import (
    send_application_name,
    send_request_if_needed,
    is_request_complete,
    ensure_ceph_keyring,
    delete_keyring,
)
from charmhelpers.payload.execd import (
    execd_preinstall
)
from charmhelpers.contrib.network.ip import (
    get_relation_ip,
)
from charmhelpers.contrib.openstack.ip import (
    canonical_url,
    PUBLIC, INTERNAL, ADMIN
)
from charmhelpers.contrib.openstack.context import (
    ADDRESS_TYPES,
)
from charmhelpers.contrib.charmsupport import nrpe
from charmhelpers.contrib.hardening.harden import harden

from charmhelpers.contrib.openstack.cert_utils import (
    get_certificate_request,
    process_certificates,
)
from charmhelpers.contrib.openstack.policyd import (
    maybe_do_policyd_overrides,
    maybe_do_policyd_overrides_on_config_changed,
)


hooks = Hooks()
# Note that CONFIGS is now set up via resolve_CONFIGS so that it is not a
# module load time constraint.
CONFIGS = None


def resolve_CONFIGS(force_update=False):
    """lazy function to resolve the CONFIGS so that it doesn't have to evaluate
    at module load time.  Note that it also returns the CONFIGS so that it can
    be used in other, module loadtime, functions.

    :param force_update: Force a refresh of CONFIGS
    :type force_update: bool
    :returns: CONFIGS variable
    :rtype: `:class:templating.OSConfigRenderer`
    """
    global CONFIGS
    if CONFIGS is None or force_update:
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

    for service in SERVICES:
        service_stop(service)
    # call the policy overrides handler which will install any policy overrides
    maybe_do_policyd_overrides(
        os_release('glance-common'),
        'glance',
        restart_handler=lambda: service_restart('glance-api'))


@hooks.hook('shared-db-relation-joined')
def db_joined():
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


@hooks.hook('shared-db-relation-changed')
@restart_on_change(restart_map())
def db_changed():
    resolve_CONFIGS()
    if is_db_maintenance_mode():
        juju_log('Database maintenance mode, aborting hook.')
        return
    release = os_release('glance-common')
    cmp_release = CompareOpenStackReleases(release)

    if 'shared-db' not in CONFIGS.complete_contexts():
        juju_log('shared-db relation incomplete. Peer not ready?')
        return

    # https://blueprints.launchpad.net/glance/+spec/deprecate-registry
    # Based on Glance registry deprecation and removal on Stein release,
    # its configuration is written only if OpenStack version is previous
    # than Stein.
    if cmp_release < 'stein':
        CONFIGS.write(GLANCE_REGISTRY_CONF)

    # since folsom, a db connection setting in glance-api.conf is required.
    if cmp_release != "essex":
        CONFIGS.write(GLANCE_API_CONF)

    if is_elected_leader(CLUSTER_RES):
        # Bugs 1353135 & 1187508. Dbs can appear to be ready before the units
        # acl entry has been added. So, if the db supports passing a list of
        # permitted units then check if we're in the list.
        allowed_units = relation_get('allowed_units')
        if allowed_units and local_unit() in allowed_units.split():
            if cmp_release == "essex":
                status = call(['glance-manage', 'db_version'])
                if status != 0:
                    juju_log('Setting version_control to 0')
                    cmd = ["glance-manage", "version_control", "0"]
                    check_call(cmd)

            if is_db_initialised():
                juju_log('Skipping DB sync, database already initialised')
            else:
                juju_log('Cluster leader, performing db sync')
                migrate_database()
        else:
            juju_log('allowed_units either not presented, or local unit '
                     'not in acl list: {}'.format(allowed_units))

    for rid in relation_ids('image-service'):
        image_service_joined(rid)


@hooks.hook('image-service-relation-joined')
def image_service_joined(relation_id=None):
    resolve_CONFIGS()
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

    relation_set(relation_id=relation_id, **relation_data)


@hooks.hook('object-store-relation-joined')
@restart_on_change(restart_map())
def object_store_joined():
    resolve_CONFIGS()
    if 'identity-service' not in CONFIGS.complete_contexts():
        juju_log('Deferring swift storage configuration until '
                 'an identity-service relation exists')
        return

    if 'object-store' not in CONFIGS.complete_contexts():
        juju_log('swift relation incomplete')
        return

    [image_service_joined(rid) for rid in relation_ids('image-service')]
    update_image_location_policy(CONFIGS)
    CONFIGS.write(GLANCE_API_CONF)


@hooks.hook('ceph-relation-joined')
def ceph_joined():
    apt_install(['ceph-common'])
    send_application_name()


@hooks.hook('ceph-relation-changed')
@restart_on_change(restart_map())
def ceph_changed():
    resolve_CONFIGS()
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


@hooks.hook('ceph-relation-departed')
@restart_on_change(restart_map())
def ceph_departed():
    resolve_CONFIGS()
    CONFIGS.write_all()


@hooks.hook('ceph-relation-broken')
@restart_on_change(restart_map())
def ceph_broken():
    resolve_CONFIGS()
    service = service_name()
    delete_keyring(service=service)
    CONFIGS.write_all()


@hooks.hook('identity-service-relation-joined')
def keystone_joined(relation_id=None):
    resolve_CONFIGS()
    if config('vip') and not is_clustered():
        juju_log('Defering registration until clustered', level=DEBUG)
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
    resolve_CONFIGS()
    if 'identity-service' not in CONFIGS.complete_contexts():
        juju_log('identity-service relation incomplete. Peer not ready?')
        return

    CONFIGS.write_all()

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
    resolve_CONFIGS()
    if config('prefer-ipv6'):
        setup_ipv6()
        status_set('maintenance', 'Sync DB')
        sync_db_with_multi_ipv6_addresses(config('database'),
                                          config('database-user'))

    if not config('action-managed-upgrade'):
        if openstack_upgrade_available('glance-common'):
            status_set('maintenance', 'Upgrading OpenStack release')
            do_openstack_upgrade(CONFIGS)
            resolve_CONFIGS(force_update=True)

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
    try:
        ceph_changed()
        update_image_location_policy(CONFIGS)
    except ValueError as e:
        # The end user has most likely provided a invalid value for a
        # configuration option. Just log the traceback here, the end user will
        # be notified by assess_status() called at the end of the hook
        # execution.
        juju_log(
            'Caught ValueError, invalid value provided for configuration?: '
            '"{}"'.format(str(e)),
            level=DEBUG)

    # call the policy overrides handler which will install any policy overrides
    maybe_do_policyd_overrides_on_config_changed(
        os_release('glance-common'),
        'glance',
        restart_handler=lambda: service_restart('glance-api'))


@hooks.hook('cluster-relation-joined')
def cluster_joined(relation_id=None):
    settings = {}

    for addr_type in ADDRESS_TYPES:
        address = get_relation_ip(
            addr_type,
            cidr_network=config('os-{}-network'.format(addr_type)))
        if address:
            settings['{}-address'.format(addr_type)] = address

    settings['private-address'] = get_relation_ip('cluster')

    relation_set(relation_id=relation_id, relation_settings=settings)


@hooks.hook('cluster-relation-changed')
@hooks.hook('cluster-relation-departed')
@restart_on_change(restart_map(), stopstart=True)
def cluster_changed():
    resolve_CONFIGS()
    configure_https()
    CONFIGS.write(GLANCE_API_CONF)
    CONFIGS.write(HAPROXY_CONF)


@hooks.hook('upgrade-charm')
@restart_on_change(restart_map(), stopstart=True)
@harden()
def upgrade_charm():
    resolve_CONFIGS()
    apt_install(filter_installed_packages(determine_packages()), fatal=True)
    packages_removed = remove_old_packages()
    reinstall_paste_ini(force_reinstall=packages_removed)
    configure_https()
    update_nrpe_config()
    # NOTE(ajkavanagh) the update_image_location_policy() call below isn't
    # called with CONFIGS as the config files all get re-written after the
    # call.
    update_image_location_policy()
    CONFIGS.write_all()
    if packages_removed:
        juju_log("Package purge detected, restarting services", "INFO")
        for s in services():
            service_restart(s)
    # call the policy overrides handler which will install any policy overrides
    maybe_do_policyd_overrides(
        os_release('glance-common'),
        'glance',
        restart_handler=lambda: service_restart('glance-api'))


@hooks.hook('ha-relation-joined')
def ha_relation_joined(relation_id=None):
    settings = generate_ha_relation_data('glance')
    relation_set(relation_id=relation_id, **settings)


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
            'cinder-volume-service-relation-broken',
            'storage-backend-relation-broken')
def relation_broken():
    resolve_CONFIGS()
    CONFIGS.write_all()


def configure_https():
    '''Enables SSL API Apache config if appropriate and kicks
    identity-service and image-service with any required
    updates
    '''
    resolve_CONFIGS()
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
    resolve_CONFIGS()
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
    nrpe_files_dir = os.path.join(
        charm_dir(), 'charmhelpers', 'contrib', 'openstack', 'files')
    nrpe.copy_nrpe_checks(nrpe_files_dir=nrpe_files_dir)
    nrpe.remove_deprecated_check(nrpe_setup, deprecated_services())
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
    release = os_release('glance-common')
    cmp_release = CompareOpenStackReleases(release)
    if cmp_release < 'rocky':
        apt_install(filter_installed_packages(optional_packages), fatal=True)


@hooks.hook('cinder-volume-service-relation-joined')
@os_requires_version('mitaka', 'glance-common')
@restart_on_change(restart_map(), stopstart=True)
def cinder_volume_service_relation_joined(relid=None):
    resolve_CONFIGS()
    install_packages_for_cinder_store()
    CONFIGS.write_all()


@hooks.hook('storage-backend-relation-changed')
@os_requires_version('mitaka', 'glance-common')
@restart_on_change(restart_map(), stopstart=True)
def storage_backend_hook():
    resolve_CONFIGS()
    if 'storage-backend' not in CONFIGS.complete_contexts():
        juju_log('storage-backend relation incomplete. Peer not ready?')
        return
    install_packages_for_cinder_store()
    CONFIGS.write(GLANCE_API_CONF)


@hooks.hook('certificates-relation-joined')
def certs_joined(relation_id=None):
    relation_set(
        relation_id=relation_id,
        relation_settings=get_certificate_request())


@hooks.hook('certificates-relation-changed')
@restart_on_change(restart_map(), stopstart=True)
def certs_changed(relation_id=None, unit=None):
    process_certificates('glance', relation_id, unit)
    configure_https()


@hooks.hook('pre-series-upgrade')
def pre_series_upgrade():
    resolve_CONFIGS()
    juju_log("Running prepare series upgrade hook", "INFO")
    series_upgrade_prepare(
        pause_unit_helper, CONFIGS)


@hooks.hook('post-series-upgrade')
def post_series_upgrade():
    resolve_CONFIGS()
    juju_log("Running complete series upgrade hook", "INFO")
    series_upgrade_complete(
        resume_unit_helper, CONFIGS)


if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        juju_log('Unknown hook {} - skipping.'.format(e))
    resolve_CONFIGS()
    assess_status(CONFIGS)
