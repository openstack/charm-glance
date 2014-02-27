#!/usr/bin/python

import os
import subprocess

import glance_contexts

from collections import OrderedDict

from charmhelpers.fetch import (
    apt_install,
    apt_update, )

from charmhelpers.core.hookenv import (
    config,
    log,
    relation_ids)

from charmhelpers.core.host import mkdir

from charmhelpers.contrib.openstack import (
    templating,
    context, )

from charmhelpers.contrib.hahelpers.cluster import (
    eligible_leader,
)

from charmhelpers.contrib.storage.linux.ceph import (
    create_pool as ceph_create_pool,
    pool_exists as ceph_pool_exists)

from charmhelpers.contrib.openstack.utils import (
    get_os_codename_install_source,
    get_os_codename_package,
    configure_installation_source, )

CLUSTER_RES = "res_glance_vip"

PACKAGES = [
    "apache2", "glance", "python-mysqldb", "python-swift",
    "python-keystone", "uuid", "haproxy", ]

SERVICES = [
    "glance-api", "glance-registry", ]

CHARM = "glance"

GLANCE_REGISTRY_CONF = "/etc/glance/glance-registry.conf"
GLANCE_REGISTRY_PASTE_INI = "/etc/glance/glance-registry-paste.ini"
GLANCE_API_CONF = "/etc/glance/glance-api.conf"
GLANCE_API_PASTE_INI = "/etc/glance/glance-api-paste.ini"
CEPH_CONF = "/etc/ceph/ceph.conf"
HAPROXY_CONF = "/etc/haproxy/haproxy.cfg"
HTTPS_APACHE_CONF = "/etc/apache2/sites-available/openstack_https_frontend"
HTTPS_APACHE_24_CONF = "/etc/apache2/sites-available/" \
    "openstack_https_frontend.conf"

CONF_DIR = "/etc/glance"

TEMPLATES = 'templates/'

CONFIG_FILES = OrderedDict([
    (GLANCE_REGISTRY_CONF, {
        'hook_contexts': [context.SharedDBContext(ssl_dir=GLANCE_CONF_DIR),
                          context.IdentityServiceContext()],
        'services': ['glance-registry']
    }),
    (GLANCE_API_CONF, {
        'hook_contexts': [context.SharedDBContext(ssl_dir=GLANCE_CONF_DIR),
                          context.AMQPContext(ssl_dir=GLANCE_CONF_DIR),
                          context.IdentityServiceContext(),
                          glance_contexts.CephGlanceContext(),
                          glance_contexts.ObjectStoreContext(),
                          glance_contexts.HAProxyContext(),
                          context.SyslogContext()],
        'services': ['glance-api']
    }),
    (GLANCE_API_PASTE_INI, {
        'hook_contexts': [context.IdentityServiceContext()],
        'services': ['glance-api']
    }),
    (GLANCE_REGISTRY_PASTE_INI, {
        'hook_contexts': [context.IdentityServiceContext()],
        'services': ['glance-registry']
    }),
    (CEPH_CONF, {
        'hook_contexts': [context.CephContext()],
        'services': ['glance-api', 'glance-registry']
    }),
    (HAPROXY_CONF, {
        'hook_contexts': [context.HAProxyContext(),
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
    release = get_os_codename_package('glance-common', fatal=False) or 'essex'
    configs = templating.OSConfigRenderer(templates_dir=TEMPLATES,
                                          openstack_release=release)

    confs = [GLANCE_REGISTRY_CONF,
             GLANCE_API_CONF,
             GLANCE_API_PASTE_INI,
             GLANCE_REGISTRY_PASTE_INI,
             HAPROXY_CONF]

    if relation_ids('ceph'):
        mkdir('/etc/ceph')
        confs.append(CEPH_CONF)

    for conf in confs:
        configs.register(conf, CONFIG_FILES[conf]['hook_contexts'])

    if os.path.exists('/etc/apache2/conf-available'):
        configs.register(HTTPS_APACHE_24_CONF,
                         CONFIG_FILES[HTTPS_APACHE_24_CONF]['hook_contexts'])
    else:
        configs.register(HTTPS_APACHE_CONF,
                         CONFIG_FILES[HTTPS_APACHE_CONF]['hook_contexts'])

    return configs


def migrate_database():
    '''Runs glance-manage to initialize a new database or migrate existing'''
    cmd = ['glance-manage', 'db_sync']
    subprocess.check_call(cmd)


def ensure_ceph_pool(service, replicas):
    '''Creates a ceph pool for service if one does not exist'''
    # TODO: Ditto about moving somewhere sharable.
    if not ceph_pool_exists(service=service, name=service):
        ceph_create_pool(service=service, name=service, replicas=replicas)


def do_openstack_upgrade(configs):
    """
    Perform an uprade of cinder.  Takes care of upgrading packages, rewriting
    configs + database migration and potentially any other post-upgrade
    actions.

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
    apt_install(packages=PACKAGES, options=dpkg_opts, fatal=True)

    # set CONFIGS to load templates from new release and regenerate config
    configs.set_release(openstack_release=new_os_rel)
    configs.write_all()

    if eligible_leader(CLUSTER_RES):
        migrate_database()


def restart_map():
    '''
    Determine the correct resource map to be passed to
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
    return OrderedDict(_map)
