#!/usr/bin/python

import os
import shutil
import subprocess
from itertools import chain

import glance_contexts

from collections import OrderedDict

from charmhelpers.fetch import (
    apt_upgrade,
    apt_update,
    apt_install,
    add_source)

from charmhelpers.contrib.python.packages import (
    pip_install,
)

from charmhelpers.core.hookenv import (
    charm_dir,
    config,
    log,
    relation_ids,
    service_name,
    status_get,
)


from charmhelpers.core.host import (
    adduser,
    add_group,
    add_user_to_group,
    mkdir,
    service_stop,
    service_start,
    service_restart,
    lsb_release,
    write_file,
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
    get_os_codename_install_source,
    git_install_requested,
    git_clone_and_install,
    git_src_dir,
    git_yaml_value,
    git_pip_venv_dir,
    configure_installation_source,
    os_release,
    set_os_workload_status,
)

from charmhelpers.core.templating import render

from charmhelpers.core.decorators import (
    retry_on_exception,
)


CLUSTER_RES = "grp_glance_vips"

PACKAGES = [
    "apache2", "glance", "python-mysqldb", "python-swiftclient",
    "python-psycopg2", "python-keystone", "python-six", "uuid", "haproxy", ]

BASE_GIT_PACKAGES = [
    'libffi-dev',
    'libmysqlclient-dev',
    'libxml2-dev',
    'libxslt1-dev',
    'libssl-dev',
    'libyaml-dev',
    'python-dev',
    'python-pip',
    'python-setuptools',
    'zlib1g-dev',
]

SERVICES = [
    "glance-api",
    "glance-registry",
]

# ubuntu packages that should not be installed when deploying from git
GIT_PACKAGE_BLACKLIST = [
    'glance',
    'python-swiftclient',
    'python-keystone',
]


CHARM = "glance"

GLANCE_CONF_DIR = "/etc/glance"
GLANCE_REGISTRY_CONF = "%s/glance-registry.conf" % GLANCE_CONF_DIR
GLANCE_REGISTRY_PASTE_INI = "%s/glance-registry-paste.ini" % GLANCE_CONF_DIR
GLANCE_API_CONF = "%s/glance-api.conf" % GLANCE_CONF_DIR
GLANCE_API_PASTE_INI = "%s/glance-api-paste.ini" % GLANCE_CONF_DIR
CEPH_CONF = "/etc/ceph/ceph.conf"
CHARM_CEPH_CONF = '/var/lib/charm/{}/ceph.conf'

HAPROXY_CONF = "/etc/haproxy/haproxy.cfg"
HTTPS_APACHE_CONF = "/etc/apache2/sites-available/openstack_https_frontend"
HTTPS_APACHE_24_CONF = "/etc/apache2/sites-available/" \
    "openstack_https_frontend.conf"

CONF_DIR = "/etc/glance"

TEMPLATES = 'templates/'

# The interface is said to be satisfied if anyone of the interfaces in the
# list has a complete context.
REQUIRED_INTERFACES = {
    'database': ['shared-db', 'pgsql-db'],
    'identity': ['identity-service'],
}


def ceph_config_file():
    return CHARM_CEPH_CONF.format(service_name())

CONFIG_FILES = OrderedDict([
    (GLANCE_REGISTRY_CONF, {
        'hook_contexts': [context.SharedDBContext(ssl_dir=GLANCE_CONF_DIR),
                          context.PostgresqlDBContext(),
                          context.IdentityServiceContext(
                              service='glance',
                              service_user='glance'),
                          context.SyslogContext(),
                          glance_contexts.LoggingConfigContext(),
                          glance_contexts.GlanceIPv6Context(),
                          context.WorkerConfigContext(),
                          context.OSConfigFlagContext(
                              charm_flag='registry-config-flags',
                              template_flag='registry_config_flags')],
        'services': ['glance-registry']
    }),
    (GLANCE_API_CONF, {
        'hook_contexts': [context.SharedDBContext(ssl_dir=GLANCE_CONF_DIR),
                          context.AMQPContext(ssl_dir=GLANCE_CONF_DIR),
                          context.PostgresqlDBContext(),
                          context.IdentityServiceContext(
                              service='glance',
                              service_user='glance'),
                          glance_contexts.CephGlanceContext(),
                          glance_contexts.ObjectStoreContext(),
                          glance_contexts.HAProxyContext(),
                          context.SyslogContext(),
                          glance_contexts.LoggingConfigContext(),
                          glance_contexts.GlanceIPv6Context(),
                          context.WorkerConfigContext(),
                          glance_contexts.MultiStoreContext(),
                          context.OSConfigFlagContext(
                              charm_flag='api-config-flags',
                              template_flag='api_config_flags')],
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
             GLANCE_API_PASTE_INI,
             GLANCE_REGISTRY_PASTE_INI,
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

    return configs


# NOTE(jamespage): Retry deals with sync issues during one-shot HA deploys.
#                  mysql might be restarting or suchlike.
@retry_on_exception(5, base_delay=3, exc_type=subprocess.CalledProcessError)
def determine_packages():
    packages = set(PACKAGES)

    if git_install_requested():
        packages |= set(BASE_GIT_PACKAGES)
        packages -= set(GIT_PACKAGE_BLACKLIST)

    return sorted(packages)


def migrate_database():
    '''Runs glance-manage to initialize a new database
    or migrate existing
    '''
    cmd = ['glance-manage', 'db_sync']
    subprocess.check_call(cmd)


def do_openstack_upgrade(configs):
    """Perform an uprade of cinder.  Takes care of upgrading
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
    apt_install(determine_packages(), fatal=True)

    # set CONFIGS to load templates from new release and regenerate config
    configs.set_release(openstack_release=new_os_rel)
    configs.write_all()

    [service_stop(s) for s in services()]
    if is_elected_leader(CLUSTER_RES):
        migrate_database()
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
    return OrderedDict(_map)


def services():
    ''' Returns a list of (unique) services associate with this charm '''
    return list(set(chain(*restart_map().values())))


def setup_ipv6():
    ubuntu_rel = lsb_release()['DISTRIB_CODENAME'].lower()
    if ubuntu_rel < "trusty":
        raise Exception("IPv6 is not supported in the charms for Ubuntu "
                        "versions less than Trusty 14.04")

    # Need haproxy >= 1.5.3 for ipv6 so for Trusty if we are <= Kilo we need to
    # use trusty-backports otherwise we can use the UCA.
    if ubuntu_rel == 'trusty' and os_release('glance') < 'liberty':
        add_source('deb http://archive.ubuntu.com/ubuntu trusty-backports '
                   'main')
        apt_update()
        apt_install('haproxy/trusty-backports', fatal=True)


def git_install(projects_yaml):
    """Perform setup, and install git repos specified in yaml parameter."""
    if git_install_requested():
        git_pre_install()
        git_clone_and_install(projects_yaml, core_project='glance')
        git_post_install(projects_yaml)


def git_pre_install():
    """Perform glance pre-install setup."""
    dirs = [
        '/var/lib/glance',
        '/var/lib/glance/images',
        '/var/lib/glance/image-cache',
        '/var/lib/glance/image-cache/incomplete',
        '/var/lib/glance/image-cache/invalid',
        '/var/lib/glance/image-cache/queue',
        '/var/log/glance',
    ]

    logs = [
        '/var/log/glance/glance-api.log',
        '/var/log/glance/glance-registry.log',
    ]

    adduser('glance', shell='/bin/bash', system_user=True)
    add_group('glance', system_group=True)
    add_user_to_group('glance', 'glance')

    for d in dirs:
        mkdir(d, owner='glance', group='glance', perms=0755, force=False)

    for l in logs:
        write_file(l, '', owner='glance', group='glance', perms=0600)


def git_post_install(projects_yaml):
    """Perform glance post-install setup."""
    http_proxy = git_yaml_value(projects_yaml, 'http_proxy')
    if http_proxy:
        pip_install('mysql-python', proxy=http_proxy,
                    venv=git_pip_venv_dir(projects_yaml))
    else:
        pip_install('mysql-python',
                    venv=git_pip_venv_dir(projects_yaml))

    src_etc = os.path.join(git_src_dir(projects_yaml, 'glance'), 'etc')
    configs = {
        'src': src_etc,
        'dest': '/etc/glance',
    }

    if os.path.exists(configs['dest']):
        shutil.rmtree(configs['dest'])
    shutil.copytree(configs['src'], configs['dest'])

    symlinks = [
        # NOTE(coreycb): Need to find better solution than bin symlinks.
        {'src': os.path.join(git_pip_venv_dir(projects_yaml),
                             'bin/glance-manage'),
         'link': '/usr/local/bin/glance-manage'},
        # NOTE(coreycb): This is ugly but couldn't find pypi package that
        #                installs rbd.py and rados.py.
        {'src': '/usr/lib/python2.7/dist-packages/rbd.py',
         'link': os.path.join(git_pip_venv_dir(projects_yaml),
                              'lib/python2.7/site-packages/rbd.py')},
        {'src': '/usr/lib/python2.7/dist-packages/rados.py',
         'link': os.path.join(git_pip_venv_dir(projects_yaml),
                              'lib/python2.7/site-packages/rados.py')},
    ]

    for s in symlinks:
        if os.path.lexists(s['link']):
            os.remove(s['link'])
        os.symlink(s['src'], s['link'])

    bin_dir = os.path.join(git_pip_venv_dir(projects_yaml), 'bin')
    glance_api_context = {
        'service_description': 'Glance API server',
        'service_name': 'Glance',
        'user_name': 'glance',
        'start_dir': '/var/lib/glance',
        'process_name': 'glance-api',
        'executable_name': os.path.join(bin_dir, 'glance-api'),
        'config_files': ['/etc/glance/glance-api.conf'],
        'log_file': '/var/log/glance/api.log',
    }

    glance_registry_context = {
        'service_description': 'Glance registry server',
        'service_name': 'Glance',
        'user_name': 'glance',
        'start_dir': '/var/lib/glance',
        'process_name': 'glance-registry',
        'executable_name': os.path.join(bin_dir, 'glance-registry'),
        'config_files': ['/etc/glance/glance-registry.conf'],
        'log_file': '/var/log/glance/registry.log',
    }

    # NOTE(coreycb): Needs systemd support
    templates_dir = 'hooks/charmhelpers/contrib/openstack/templates'
    templates_dir = os.path.join(charm_dir(), templates_dir)
    render('git.upstart', '/etc/init/glance-api.conf',
           glance_api_context, perms=0o644, templates_dir=templates_dir)
    render('git.upstart', '/etc/init/glance-registry.conf',
           glance_registry_context, perms=0o644, templates_dir=templates_dir)

    service_restart('glance-api')
    service_restart('glance-registry')


def check_optional_relations(configs):
    required_interfaces = {}
    if relation_ids('ha'):
        required_interfaces['ha'] = ['cluster']
        try:
            get_hacluster_config()
        except:
            return ('blocked',
                    'hacluster missing configuration: '
                    'vip, vip_iface, vip_cidr')

    if relation_ids('ceph') or relation_ids('object-store'):
        required_interfaces['storage-backend'] = ['ceph', 'object-store']

    if relation_ids('amqp'):
        required_interfaces['messaging'] = ['amqp']

    if required_interfaces:
        set_os_workload_status(configs, required_interfaces)
        return status_get()
    else:
        return 'unknown', 'No optional relations'
