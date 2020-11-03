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

import json
import os
import subprocess
from itertools import chain

import glance_contexts

from collections import OrderedDict

from charmhelpers.fetch import (
    apt_upgrade,
    apt_update,
    apt_install,
    add_source,
    apt_autoremove,
    apt_purge,
    filter_missing_packages)

from charmhelpers.core.hookenv import (
    config,
    log,
    INFO,
    WARNING,
    relation_ids,
    service_name,
)


from charmhelpers.core.host import (
    CompareHostReleases,
    lsb_release,
    mkdir,
    service_stop,
    service_start,
)

from charmhelpers.contrib.openstack import (
    templating,
    context,)

from charmhelpers.contrib.hahelpers.cluster import (
    is_elected_leader,
    get_hacluster_config,
    get_managed_services_and_ports,
)

from charmhelpers.contrib.openstack.alternatives import install_alternative
from charmhelpers.contrib.openstack.utils import (
    CompareOpenStackReleases,
    configure_installation_source,
    enable_memcache,
    incomplete_relation_data,
    is_unit_paused_set,
    get_os_codename_install_source,
    make_assess_status_func,
    os_application_version_set,
    os_release,
    reset_os_release,
    pause_unit,
    resume_unit,
    token_cache_pkgs,
    update_json_file,
    set_db_initialised,
)

from charmhelpers.core.decorators import (
    retry_on_exception,
)
from charmhelpers.contrib.storage.linux.ceph import (
    CephBrokerRq,
    is_request_complete,
)
from charmhelpers.contrib.openstack.context import (
    CephBlueStoreCompressionContext,
)

from charmhelpers.core.unitdata import kv


CLUSTER_RES = "grp_glance_vips"

PACKAGES = [
    "apache2", "glance", "python-mysqldb", "python-swiftclient",
    "python-psycopg2", "python-keystone", "uuid", "haproxy", ]

PY3_PACKAGES = [
    "python3-glance",
    "python3-rados",
    "python3-rbd",
    "python3-swiftclient",
    "python3-cinderclient",
    "python3-os-brick",
    "python3-oslo.rootwrap",
]

VERSION_PACKAGE = 'glance-common'

SERVICES = [
    "glance-api",
    "glance-registry",
]

CHARM = "glance"

GLANCE_CONF_DIR = "/etc/glance"
GLANCE_REGISTRY_CONF = "%s/glance-registry.conf" % GLANCE_CONF_DIR
GLANCE_API_CONF = "%s/glance-api.conf" % GLANCE_CONF_DIR
GLANCE_SWIFT_CONF = "%s/glance-swift.conf" % GLANCE_CONF_DIR
GLANCE_REGISTRY_PASTE = os.path.join(GLANCE_CONF_DIR,
                                     'glance-registry-paste.ini')
GLANCE_API_PASTE = os.path.join(GLANCE_CONF_DIR,
                                'glance-api-paste.ini')
GLANCE_POLICY_FILE = os.path.join(GLANCE_CONF_DIR, "policy.json")
# NOTE(ajkavanagh): from Ussuri, glance switched to policy-in-code; this is the
# policy.yaml file (as there is not packaged policy.json or .yaml) that is used
# to provide the image_location override config value:
# 'restrict-image-location-operations'
GLANCE_POLICY_YAML = os.path.join(GLANCE_CONF_DIR, "policy.yaml")
CEPH_CONF = "/etc/ceph/ceph.conf"
CHARM_CEPH_CONF = '/var/lib/charm/{}/ceph.conf'

HAPROXY_CONF = "/etc/haproxy/haproxy.cfg"
APACHE_PORTS_CONF = '/etc/apache2/ports.conf'
HTTPS_APACHE_CONF = "/etc/apache2/sites-available/openstack_https_frontend"
HTTPS_APACHE_24_CONF = "/etc/apache2/sites-available/" \
    "openstack_https_frontend.conf"
APACHE_SSL_DIR = '/etc/apache2/ssl/glance'

MEMCACHED_CONF = '/etc/memcached.conf'

TEMPLATES = 'templates/'

# The interface is said to be satisfied if anyone of the interfaces in the
# list has a complete context.
REQUIRED_INTERFACES = {
    'database': ['shared-db'],
    'identity': ['identity-service'],
}


def ceph_config_file():
    return CHARM_CEPH_CONF.format(service_name())


CONFIG_FILES = OrderedDict([
    (GLANCE_REGISTRY_CONF, {
        'hook_contexts': [context.SharedDBContext(ssl_dir=GLANCE_CONF_DIR),
                          context.IdentityServiceContext(
                              service='glance',
                              service_user='glance'),
                          context.SyslogContext(),
                          glance_contexts.LoggingConfigContext(),
                          glance_contexts.GlanceIPv6Context(),
                          context.WorkerConfigContext(),
                          context.OSConfigFlagContext(
                              charm_flag='registry-config-flags',
                              template_flag='registry_config_flags'),
                          context.MemcacheContext()],
        'services': ['glance-registry']
    }),
    (GLANCE_API_CONF, {
        'hook_contexts': [context.SharedDBContext(ssl_dir=GLANCE_CONF_DIR),
                          context.AMQPContext(ssl_dir=GLANCE_CONF_DIR),
                          context.IdentityServiceContext(
                              service='glance',
                              service_user='glance'),
                          glance_contexts.GlanceContext(),
                          glance_contexts.CephGlanceContext(),
                          glance_contexts.ObjectStoreContext(),
                          glance_contexts.CinderStoreContext(),
                          glance_contexts.HAProxyContext(),
                          context.SyslogContext(),
                          glance_contexts.LoggingConfigContext(),
                          glance_contexts.GlanceIPv6Context(),
                          context.WorkerConfigContext(),
                          glance_contexts.MultiStoreContext(),
                          glance_contexts.MultiBackendContext(),
                          context.OSConfigFlagContext(
                              charm_flag='api-config-flags',
                              template_flag='api_config_flags'),
                          context.InternalEndpointContext(),
                          context.VolumeAPIContext('glance-common'),
                          context.SubordinateConfigContext(
                              interface=['storage-backend'],
                              service=['glance-api'],
                              config_file=GLANCE_API_CONF),
                          context.MemcacheContext()],
        'services': ['glance-api']
    }),
    (GLANCE_SWIFT_CONF, {
        'hook_contexts': [glance_contexts.ObjectStoreContext(),
                          context.IdentityServiceContext(
                              service='glance',
                              service_user='glance')],
        'services': ['glance-api']
    }),
    (GLANCE_POLICY_FILE, {
        'hook_contexts': [],
        'services': ['glance-api', 'glance-registry']
    }),
    (ceph_config_file(), {
        'hook_contexts': [context.CephContext()],
        'services': ['glance-api', 'glance-registry']
    }),
    (HAPROXY_CONF, {
        'hook_contexts': [context.HAProxyContext(singlenode_mode=True),
                          glance_contexts.HAProxyContext()],
        'services': ['haproxy'],
    }),
    (HTTPS_APACHE_CONF, {
        'hook_contexts': [glance_contexts.ApacheSSLContext()],
        'services': ['apache2'],
    }),
    (HTTPS_APACHE_24_CONF, {
        'hook_contexts': [glance_contexts.ApacheSSLContext()],
        'services': ['apache2'],
    }),
    (APACHE_PORTS_CONF, {
        'contexts': [],
        'services': ['apache2'],
    }),
    (GLANCE_POLICY_YAML, {
        'hook_contexts': [glance_contexts.GlancePolicyContext()],
        'services': [],
    }),
])


def register_configs():
    # Register config files with their respective contexts.
    # Regstration of some configs may not be required depending on
    # existing of certain relations.
    release = os_release('glance-common')
    cmp_release = CompareOpenStackReleases(release)
    configs = templating.OSConfigRenderer(templates_dir=TEMPLATES,
                                          openstack_release=release)

    confs = [GLANCE_REGISTRY_CONF,
             GLANCE_API_CONF,
             HAPROXY_CONF]

    if relation_ids('ceph'):
        mkdir(os.path.dirname(ceph_config_file()))
        mkdir(os.path.dirname(CEPH_CONF))

        # Install ceph config as an alternative for co-location with
        # ceph and ceph-osd charms - glance ceph.conf will be
        # lower priority that both of these but thats OK
        if not os.path.exists(ceph_config_file()):
            # touch file for pre-templated generation
            open(ceph_config_file(), 'w').close()
        install_alternative(os.path.basename(CEPH_CONF),
                            CEPH_CONF, ceph_config_file())
        confs.append(ceph_config_file())

    for conf in confs:
        if cmp_release >= 'stein' and conf == GLANCE_REGISTRY_CONF:
            continue
        configs.register(conf, CONFIG_FILES[conf]['hook_contexts'])

    if os.path.exists('/etc/apache2/conf-available'):
        configs.register(HTTPS_APACHE_24_CONF,
                         CONFIG_FILES[HTTPS_APACHE_24_CONF]['hook_contexts'])
    else:
        configs.register(HTTPS_APACHE_CONF,
                         CONFIG_FILES[HTTPS_APACHE_CONF]['hook_contexts'])

    if enable_memcache(release=release):
        configs.register(MEMCACHED_CONF, [context.MemcacheContext()])

    if cmp_release >= 'mitaka':
        configs.register(GLANCE_SWIFT_CONF,
                         CONFIG_FILES[GLANCE_SWIFT_CONF]['hook_contexts'])

    if cmp_release >= 'ussuri':
        configs.register(GLANCE_POLICY_YAML,
                         CONFIG_FILES[GLANCE_POLICY_YAML]['hook_contexts'])

    return configs


def determine_packages():
    packages = set(PACKAGES)
    packages |= set(token_cache_pkgs(source=config('openstack-origin')))
    if CompareOpenStackReleases(os_release(VERSION_PACKAGE)) >= 'rocky':
        packages = [p for p in packages if not p.startswith('python-')]
        packages.extend(PY3_PACKAGES)
    return sorted(packages)


def determine_purge_packages():
    '''
    Determine list of packages that where previously installed which are no
    longer needed.

    :returns: list of package names
    '''
    if CompareOpenStackReleases(os_release('glance')) >= 'rocky':
        pkgs = [p for p in PACKAGES if p.startswith('python-')]
        pkgs.append('python-glance')
        pkgs.append('python-memcache')
        pkgs.extend(["python-cinderclient",
                     "python-os-brick",
                     "python-oslo.rootwrap"])
        if CompareOpenStackReleases(os_release('glance')) >= 'stein':
            pkgs.append('glance-registry')
        return pkgs
    return []


# NOTE(jamespage): Retry deals with sync issues during one-shot HA deploys.
#                  mysql might be restarting or suchlike.
@retry_on_exception(5, base_delay=3, exc_type=subprocess.CalledProcessError)
def migrate_database():
    '''Runs glance-manage to initialize a new database
    or migrate existing
    '''
    cmd = ['glance-manage', 'db_sync']
    subprocess.check_call(cmd)
    set_db_initialised()


def remove_old_packages():
    '''Purge any packages that need ot be removed.

    :returns: bool Whether packages were removed.
    '''
    installed_packages = filter_missing_packages(determine_purge_packages())
    if installed_packages:
        apt_purge(installed_packages, fatal=True)
        apt_autoremove(purge=True, fatal=True)
    return bool(installed_packages)


def do_openstack_upgrade(configs):
    """Perform an upgrade of glance.  Takes care of upgrading
    packages, rewriting configs + database migration and potentially
    any other post-upgrade actions.

    :param configs: The charms main OSConfigRenderer object.

    """
    new_src = config('openstack-origin')
    new_os_rel = get_os_codename_install_source(new_src)

    log('Performing OpenStack upgrade to %s.' % (new_os_rel))

    configure_installation_source(new_src)
    dpkg_opts = [
        '--option', 'Dpkg::Options::=--force-confnew',
        '--option', 'Dpkg::Options::=--force-confdef',
    ]
    apt_update()
    apt_upgrade(options=dpkg_opts, fatal=True, dist=True)
    reset_os_release()
    apt_install(determine_packages(), fatal=True)

    remove_old_packages()

    # set CONFIGS to load templates from new release and regenerate config
    configs.set_release(openstack_release=new_os_rel)
    configs.write_all()

    [service_stop(s) for s in services()]
    if is_elected_leader(CLUSTER_RES):
        migrate_database()
    # Don't start services if the unit is supposed to be paused.
    if not is_unit_paused_set():
        [service_start(s) for s in services()]


def restart_map():
    '''Determine the correct resource map to be passed to
    charmhelpers.core.restart_on_change() based on the services configured.

    :returns: dict: A dictionary mapping config file to lists of services
                    that should be restarted when file changes.
    '''
    _map = []
    cmp_release = CompareOpenStackReleases(os_release('glance-common'))

    for f, ctxt in CONFIG_FILES.items():
        svcs = []
        for svc in ctxt['services']:
            if cmp_release >= 'stein' and svc == 'glance-registry':
                continue
            svcs.append(svc)
        if svcs:
            _map.append((f, svcs))

    if enable_memcache(source=config('openstack-origin')):
        _map.append((MEMCACHED_CONF, ['memcached']))

    if cmp_release >= 'stein':
        glance_svcs = ['glance-api']
    else:
        glance_svcs = ['glance-api', 'glance-registry']

    if os.path.isdir(APACHE_SSL_DIR):
        _map.append(('{}/*'.format(APACHE_SSL_DIR), glance_svcs + ['apache2']))

    return OrderedDict(_map)


def services():
    ''' Returns a list of (unique) services associate with this charm '''
    return list(set(chain(*restart_map().values())))


def deprecated_services():
    ''' Returns a list of deprecated services with this charm '''
    cmp_release = CompareOpenStackReleases(os_release('glance-common'))
    if cmp_release >= 'stein':
        return ['glance-registry']

    return []


def setup_ipv6():
    ubuntu_rel = lsb_release()['DISTRIB_CODENAME'].lower()
    if CompareHostReleases(ubuntu_rel) < "trusty":
        raise Exception("IPv6 is not supported in the charms for Ubuntu "
                        "versions less than Trusty 14.04")

    # Need haproxy >= 1.5.3 for ipv6 so for Trusty if we are <= Kilo we need to
    # use trusty-backports otherwise we can use the UCA.
    if (ubuntu_rel == 'trusty' and
            CompareOpenStackReleases(os_release('glance')) < 'liberty'):
        add_source('deb http://archive.ubuntu.com/ubuntu trusty-backports '
                   'main')
        apt_update()
        apt_install('haproxy/trusty-backports', fatal=True)


def get_optional_interfaces():
    """Return the optional interfaces that should be checked if the relavent
    relations have appeared.

    :returns: {general_interface: [specific_int1, specific_int2, ...], ...}
    """
    optional_interfaces = {}
    if relation_ids('ha'):
        optional_interfaces['ha'] = ['cluster']

    if (relation_ids('ceph') or relation_ids('object-store') or
            relation_ids('cinder-volume-service') or
            relation_ids('storage-backend')):
        optional_interfaces['storage-backend'] = ['ceph', 'object-store',
                                                  'cinder-volume-service',
                                                  'storage-backend']

    if relation_ids('amqp'):
        optional_interfaces['messaging'] = ['amqp']
    return optional_interfaces


def check_optional_config_and_relations(configs):
    """Validate optional configuration and relations when present.

    This function is called from assess_status/set_os_workload_status as the
    charm_func and needs to return either None, None if there is no problem or
    the status, message if there is a problem.

    :param configs: an OSConfigRender() instance.
    :return 2-tuple: (string, string) = (status, message)
    """
    # Check that if we have a relation_id for high availability that we can
    # get the hacluster config.  If we can't then we are blocked.
    if relation_ids('ha'):
        try:
            get_hacluster_config()
        except Exception:
            return ('blocked',
                    'hacluster missing configuration: '
                    'vip, vip_iface, vip_cidr')

    if relation_ids('ceph'):
        # Check that provided Ceph BlueStoe configuration is valid.
        try:
            bluestore_compression = context.CephBlueStoreCompressionContext()
            bluestore_compression.validate()
        except AttributeError:
            # The charm does late installation of the `ceph-common` package and
            # the class initializer above will throw an exception until it is.
            pass
        except ValueError as e:
            return ('blocked', 'Invalid configuration: {}'.format(str(e)))
        # ceph pkgs are only installed after the ceph relation is etablished
        # so gate checking broker requests on ceph relation being completed.
        if ('ceph' in configs.complete_contexts()
                and not is_request_complete(get_ceph_request())):
            return ('waiting', 'Ceph broker request incomplete')
    # return 'unknown' as the lowest priority to not clobber an existing
    # status.
    return "unknown", ""


def assess_status(configs):
    """Assess status of current unit
    Decides what the state of the unit should be based on the current
    configuration.
    SIDE EFFECT: calls set_os_workload_status(...) which sets the workload
    status of the unit.
    Also calls status_set(...) directly if paused state isn't complete.
    @param configs: a templating.OSConfigRenderer() object
    @returns None - this function is executed for its side-effect
    """
    assess_status_func(configs)()
    os_application_version_set(VERSION_PACKAGE)


def assess_status_func(configs):
    """Helper function to create the function that will assess_status() for
    the unit.
    Uses charmhelpers.contrib.openstack.utils.make_assess_status_func() to
    create the appropriate status function and then returns it.
    Used directly by assess_status() and also for pausing and resuming
    the unit.

    NOTE: REQUIRED_INTERFACES is augmented with the optional interfaces
    depending on the current config before being passed to the
    make_assess_status_func() function.

    NOTE(ajkavanagh) ports are not checked due to race hazards with services
    that don't behave sychronously w.r.t their service scripts.  e.g.
    apache2.
    @param configs: a templating.OSConfigRenderer() object
    @return f() -> None : a function that assesses the unit's workload status
    """
    required_interfaces = REQUIRED_INTERFACES.copy()
    required_interfaces.update(get_optional_interfaces())
    _services, _ = get_managed_services_and_ports(services(), [])
    return make_assess_status_func(
        configs, required_interfaces,
        charm_func=check_optional_config_and_relations,
        services=_services, ports=None)


def pause_unit_helper(configs):
    """Helper function to pause a unit, and then call assess_status(...) in
    effect, so that the status is correctly updated.
    Uses charmhelpers.contrib.openstack.utils.pause_unit() to do the work.
    @param configs: a templating.OSConfigRenderer() object
    @returns None - this function is executed for its side-effect
    """
    _pause_resume_helper(pause_unit, configs)


def resume_unit_helper(configs):
    """Helper function to resume a unit, and then call assess_status(...) in
    effect, so that the status is correctly updated.
    Uses charmhelpers.contrib.openstack.utils.resume_unit() to do the work.
    @param configs: a templating.OSConfigRenderer() object
    @returns None - this function is executed for its side-effect
    """
    _pause_resume_helper(resume_unit, configs)


def _pause_resume_helper(f, configs):
    """Helper function that uses the make_assess_status_func(...) from
    charmhelpers.contrib.openstack.utils to create an assess_status(...)
    function that can be used with the pause/resume of the unit
    @param f: the function to be used with the assess_status(...) function
    @returns None - this function is executed for its side-effect
    """
    # TODO(ajkavanagh) - ports= has been left off because of the race hazard
    # that exists due to service_start()
    _services, _ = get_managed_services_and_ports(services(), [])
    f(assess_status_func(configs),
      services=_services,
      ports=None)


PASTE_INI_MARKER = 'paste-ini-marker'
REINSTALL_OPTIONS = [
    '--reinstall',
    '--option=Dpkg::Options::=--force-confmiss'
]


def reinstall_paste_ini(force_reinstall=False):
    '''
    Re-install glance-{api,registry}-paste.ini file from packages

    Existing glance-{api,registry}-paste.ini file will be removed
    and the original files provided by the packages will be
    re-installed.

    This will only be performed once per unit unless force_reinstall
    is set to True.
    '''
    db = kv()
    reinstall = not db.get(PASTE_INI_MARKER) or force_reinstall
    cmp_release = CompareOpenStackReleases(os_release('glance-common'))

    if not os.path.exists(GLANCE_REGISTRY_PASTE) and cmp_release < 'rocky':
        # See LP: #1812972
        reinstall = True

    if reinstall:
        for paste_file in [GLANCE_REGISTRY_PASTE,
                           GLANCE_API_PASTE]:
            if os.path.exists(paste_file):
                os.remove(paste_file)
        # glance-registry is deprecated at queens but still
        # installed.
        if cmp_release < 'rocky':
            pkg_list = ['glance-api', 'glance-registry']
        # File is in glance-common for py3 packages.
        else:
            pkg_list = ['glance-common']
        apt_install(packages=pkg_list,
                    options=REINSTALL_OPTIONS,
                    fatal=True)
        db.set(PASTE_INI_MARKER, True)
        db.flush()


def is_api_ready(configs):
    return (not incomplete_relation_data(configs, REQUIRED_INTERFACES))


def update_image_location_policy(configs=None):
    """Update *_image_location policy to restrict to admin role.

    We do this unconditonally and keep a record of the original as installed by
    the package.

    For ussuri, the charm updates/writes the policy.yaml file.  The configs
    param is optional as the caller may already be writing all the configs.
    From ussuri onwards glance is policy-in-code (rather than using a
    policy.json) and, therefore, policy files are essentially all overrides.

    From ussuri, this function deletes the policy.json file and alternatively
    writes the GLANCE_POLICY_YAML file via the configs object.

    :param configs: The configs for the charm
    :type configs: Optional[:class:templating.OSConfigRenderer()]
    """
    _res = os_release('glance-common')
    cmp = CompareOpenStackReleases(_res)
    if cmp < 'kilo':
        # NOTE(hopem): at the time of writing we are unable to do this for
        # earlier than Kilo due to LP: #1502136
        return
    if cmp >= 'ussuri':
        # If the policy.json exists, then remove it as it's the packaged
        # version from a previous version of OpenStack, and thus not used.
        if os.path.isfile(GLANCE_POLICY_FILE):
            try:
                os.remove(GLANCE_POLICY_FILE)
            except Exception as e:
                log("Problem removing file: {}: {}"
                    .format(GLANCE_POLICY_FILE, str(e)))
        # if the caller supplied a configs param then update the
        # GLANCE_POLICY_FILE using its context.
        if configs is not None:
            configs.write(GLANCE_POLICY_YAML)
        return

    # otherwise the OpenStack release after kilo and before ussuri, so continue
    # modifying the existing policy.json file.
    db = kv()
    policies = ["get_image_location", "set_image_location",
                "delete_image_location"]

    try:
        with open(GLANCE_POLICY_FILE) as f:
            pmap = json.load(f)
    except IOError as e:
        log("Problem opening glance policy file: {}.  Error was:{}"
            .format(GLANCE_POLICY_FILE, str(e)),
            level=WARNING)
        return

    for policy_key in policies:
        # Save original value at time of first install in case we ever need to
        # revert.
        db_key = "policy_{}".format(policy_key)
        if db.get(db_key) is None:
            if policy_key in pmap:
                db.set(db_key, pmap[policy_key])
                db.flush()
            else:
                log("key '{}' not found in policy file".format(policy_key),
                    level=INFO)

    if config('restrict-image-location-operations'):
        policy_value = 'role:admin'
    else:
        policy_value = ''

    new_policies = {k: policy_value for k in policies}
    for policy_key, policy_value in new_policies.items():
        log("Updating Glance policy file setting policy "
            "'{}': '{}'".format(policy_key, policy_value), level=INFO)

    update_json_file(GLANCE_POLICY_FILE, new_policies)


def get_ceph_request():
    service = service_name()
    if config('rbd-pool-name'):
        pool_name = config('rbd-pool-name')
    else:
        pool_name = service

    rq = CephBrokerRq()
    weight = config('ceph-pool-weight')
    replicas = config('ceph-osd-replication-count')
    bluestore_compression = CephBlueStoreCompressionContext()

    if config('pool-type') == 'erasure-coded':
        # General EC plugin config
        plugin = config('ec-profile-plugin')
        technique = config('ec-profile-technique')
        device_class = config('ec-profile-device-class')
        metadata_pool_name = (
            config('ec-rbd-metadata-pool') or
            "{}-metadata".format(service)
        )
        bdm_k = config('ec-profile-k')
        bdm_m = config('ec-profile-m')
        # LRC plugin config
        bdm_l = config('ec-profile-locality')
        crush_locality = config('ec-profile-crush-locality')
        # SHEC plugin config
        bdm_c = config('ec-profile-durability-estimator')
        # CLAY plugin config
        bdm_d = config('ec-profile-helper-chunks')
        scalar_mds = config('ec-profile-scalar-mds')
        # Profile name
        profile_name = (
            config('ec-profile-name') or "{}-profile".format(service)
        )
        # Metadata sizing is approximately 1% of overall data weight
        # but is in effect driven by the number of rbd's rather than
        # their size - so it can be very lightweight.
        metadata_weight = weight * 0.01
        # Resize data pool weight to accomodate metadata weight
        weight = weight - metadata_weight
        # Create metadata pool
        rq.add_op_create_pool(
            name=metadata_pool_name, replica_count=replicas,
            weight=metadata_weight, group='images', app_name='rbd'
        )

        # Create erasure profile
        rq.add_op_create_erasure_profile(
            name=profile_name,
            k=bdm_k, m=bdm_m,
            lrc_locality=bdm_l,
            lrc_crush_locality=crush_locality,
            shec_durability_estimator=bdm_c,
            clay_helper_chunks=bdm_d,
            clay_scalar_mds=scalar_mds,
            device_class=device_class,
            erasure_type=plugin,
            erasure_technique=technique
        )

        # Create EC data pool

        # NOTE(fnordahl): once we deprecate Python 3.5 support we can do
        # the unpacking of the BlueStore compression arguments as part of
        # the function arguments. Until then we need to build the dict
        # prior to the function call.
        kwargs = {
            'name': pool_name,
            'erasure_profile': profile_name,
            'weight': weight,
            'group': "images",
            'app_name': "rbd",
            'allow_ec_overwrites': True,
        }
        kwargs.update(bluestore_compression.get_kwargs())
        rq.add_op_create_erasure_pool(**kwargs)
    else:
        # NOTE(fnordahl): once we deprecate Python 3.5 support we can do
        # the unpacking of the BlueStore compression arguments as part of
        # the function arguments. Until then we need to build the dict
        # prior to the function call.
        kwargs = {
            'name': pool_name,
            'replica_count': replicas,
            'weight': weight,
            'group': 'images',
            'app_name': 'rbd',
        }
        kwargs.update(bluestore_compression.get_kwargs())
        rq.add_op_create_replicated_pool(**kwargs)

    if config('restrict-ceph-pools'):
        rq.add_op_request_access_to_group(
            name="images",
            object_prefix_permissions={'class-read': ['rbd_children']},
            permission='rwx')
    return rq
