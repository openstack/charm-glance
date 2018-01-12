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
    add_source)

from charmhelpers.core.hookenv import (
    config,
    log,
    INFO,
    relation_ids,
    service_name,
)


from charmhelpers.core.host import (
    CompareHostReleases,
    lsb_release,
    mkdir,
    pwgen,
    service_stop,
    service_start,
)

from charmhelpers.contrib.openstack import (
    templating,
    context,)

from charmhelpers.contrib.hahelpers.cluster import (
    is_elected_leader,
    get_hacluster_config,
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
)

from charmhelpers.core.decorators import (
    retry_on_exception,
)

from charmhelpers.core.unitdata import kv


CLUSTER_RES = "grp_glance_vips"

PACKAGES = [
    "apache2", "glance", "python-mysqldb", "python-swiftclient",
    "python-psycopg2", "python-keystone", "python-six", "uuid", "haproxy", ]

VERSION_PACKAGE = 'glance-common'

SERVICES = [
    "glance-api",
    "glance-registry",
]

CHARM = "glance"

GLANCE_CONF_DIR = "/etc/glance"
GLANCE_REGISTRY_CONF = "%s/glance-registry.conf" % GLANCE_CONF_DIR
GLANCE_API_CONF = "%s/glance-api.conf" % GLANCE_CONF_DIR
GLANCE_REGISTRY_PASTE = os.path.join(GLANCE_CONF_DIR,
                                     'glance-registry-paste.ini')
GLANCE_API_PASTE = os.path.join(GLANCE_CONF_DIR,
                                'glance-api-paste.ini')
GLANCE_POLICY_FILE = os.path.join(GLANCE_CONF_DIR, "policy.json")
CEPH_CONF = "/etc/ceph/ceph.conf"
CHARM_CEPH_CONF = '/var/lib/charm/{}/ceph.conf'

HAPROXY_CONF = "/etc/haproxy/haproxy.cfg"
HTTPS_APACHE_CONF = "/etc/apache2/sites-available/openstack_https_frontend"
HTTPS_APACHE_24_CONF = "/etc/apache2/sites-available/" \
    "openstack_https_frontend.conf"
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
                          context.OSConfigFlagContext(
                              charm_flag='api-config-flags',
                              template_flag='api_config_flags'),
                          context.InternalEndpointContext('glance-common'),
                          context.SubordinateConfigContext(
                              interface=['storage-backend'],
                              service=['glance-api'],
                              config_file=GLANCE_API_CONF),
                          context.MemcacheContext()],
        'services': ['glance-api']
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
    })
])


def register_configs():
    # Register config files with their respective contexts.
    # Regstration of some configs may not be required depending on
    # existing of certain relations.
    release = os_release('glance-common')
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
        configs.register(conf, CONFIG_FILES[conf]['hook_contexts'])

    if os.path.exists('/etc/apache2/conf-available'):
        configs.register(HTTPS_APACHE_24_CONF,
                         CONFIG_FILES[HTTPS_APACHE_24_CONF]['hook_contexts'])
    else:
        configs.register(HTTPS_APACHE_CONF,
                         CONFIG_FILES[HTTPS_APACHE_CONF]['hook_contexts'])

    if enable_memcache(release=release):
        configs.register(MEMCACHED_CONF, [context.MemcacheContext()])
    return configs


def determine_packages():
    packages = set(PACKAGES)
    packages |= set(token_cache_pkgs(source=config('openstack-origin')))
    return sorted(packages)


# NOTE(jamespage): Retry deals with sync issues during one-shot HA deploys.
#                  mysql might be restarting or suchlike.
@retry_on_exception(5, base_delay=3, exc_type=subprocess.CalledProcessError)
def migrate_database():
    '''Runs glance-manage to initialize a new database
    or migrate existing
    '''
    cmd = ['glance-manage', 'db_sync']
    subprocess.check_call(cmd)


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
    for f, ctxt in CONFIG_FILES.iteritems():
        svcs = []
        for svc in ctxt['services']:
            svcs.append(svc)
        if svcs:
            _map.append((f, svcs))

    if enable_memcache(source=config('openstack-origin')):
        _map.append((MEMCACHED_CONF, ['memcached']))

    _map.append((GLANCE_POLICY_FILE, ['glance-api', 'glance-registry']))

    return OrderedDict(_map)


def services():
    ''' Returns a list of (unique) services associate with this charm '''
    return list(set(chain(*restart_map().values())))


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


def check_optional_relations(configs):
    """Check that if we have a relation_id for high availability that we can
    get the hacluster config.  If we can't then we are blocked.

    This function is called from assess_status/set_os_workload_status as the
    charm_func and needs to return either None, None if there is no problem or
    the status, message if there is a problem.

    :param configs: an OSConfigRender() instance.
    :return 2-tuple: (string, string) = (status, message)
    """
    if relation_ids('ha'):
        try:
            get_hacluster_config()
        except:
            return ('blocked',
                    'hacluster missing configuration: '
                    'vip, vip_iface, vip_cidr')
    # return 'unknown' as the lowest priority to not clobber an existing
    # status.
    return "unknown", ""


def swift_temp_url_key():
    """Generate a temp URL key, post it to Swift and return its value.
       If it is already posted, the current value of the key will be returned.
    """
    import requests
    keystone_ctxt = context.IdentityServiceContext(service='glance',
                                                   service_user='glance')()
    if not keystone_ctxt:
        log('Missing identity-service relation. Skipping generation of '
            'swift temporary url key.')
        return

    auth_url = '%s://%s:%s/v2.0/' % (keystone_ctxt['service_protocol'],
                                     keystone_ctxt['service_host'],
                                     keystone_ctxt['service_port'])
    from swiftclient import client
    from swiftclient import exceptions

    @retry_on_exception(15, base_delay=10,
                        exc_type=(exceptions.ClientException,
                                  requests.exceptions.ConnectionError))
    def connect_and_post():
        log('Connecting swift client...')
        swift_connection = client.Connection(
            authurl=auth_url, user='glance',
            key=keystone_ctxt['admin_password'],
            tenant_name=keystone_ctxt['admin_tenant_name'],
            auth_version='2.0')

        account_stats = swift_connection.head_account()
        if 'x-account-meta-temp-url-key' in account_stats:
            log("Temp URL key was already posted.")
            return account_stats['x-account-meta-temp-url-key']

        temp_url_key = pwgen(length=64)
        swift_connection.post_account(headers={'x-account-meta-temp-url-key':
                                               temp_url_key})
        return temp_url_key

    return connect_and_post()


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
    return make_assess_status_func(
        configs, required_interfaces,
        charm_func=check_optional_relations,
        services=services(), ports=None)


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
    f(assess_status_func(configs),
      services=services(),
      ports=None)


PASTE_INI_MARKER = 'paste-ini-marker'
REINSTALL_OPTIONS = [
    '--reinstall',
    '--option=Dpkg::Options::=--force-confmiss'
]


def reinstall_paste_ini():
    '''
    Re-install glance-{api,registry}-paste.ini file from packages

    Existing glance-{api,registry}-paste.ini file will be removed
    and the original files provided by the packages will be
    re-installed.

    This will only ever be performed once per unit.
    '''
    db = kv()
    if not db.get(PASTE_INI_MARKER):
        for paste_file in [GLANCE_REGISTRY_PASTE,
                           GLANCE_API_PASTE]:
            if os.path.exists(paste_file):
                os.remove(paste_file)
        apt_install(packages=['glance-api', 'glance-registry'],
                    options=REINSTALL_OPTIONS,
                    fatal=True)
        db.set(PASTE_INI_MARKER, True)
        db.flush()


def is_api_ready(configs):
    return (not incomplete_relation_data(configs, REQUIRED_INTERFACES))


def update_image_location_policy():
    """Update *_image_location policy to restrict to admin role.

    We do this unconditonally and keep a record of the original as installed by
    the package.
    """
    if CompareOpenStackReleases(os_release('glance-common')) < 'kilo':
        # NOTE(hopem): at the time of writing we are unable to do this for
        # earlier than Kilo due to LP: #1502136
        return

    db = kv()
    policies = ["get_image_location", "set_image_location",
                "delete_image_location"]
    for policy_key in policies:
        # Save original value at time of first install in case we ever need to
        # revert.
        db_key = "policy_{}".format(policy_key)
        if db.get(db_key) is None:
            p = json.loads(open(GLANCE_POLICY_FILE).read())
            if policy_key in p:
                db.set(db_key, p[policy_key])
                db.flush()
            else:
                log("key '{}' not found in policy file".format(policy_key),
                    level=INFO)

        policy_value = 'role:admin'
        log("Updating Glance policy file setting policy "
            "'{}':'{}'".format(policy_key, policy_value), level=INFO)
        update_json_file(GLANCE_POLICY_FILE, {policy_key: policy_value})
