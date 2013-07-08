#!/usr/bin/python

import os
import time
import sys
import subprocess

import glance_contexts

from collections import OrderedDict

from charmhelpers.core.hookenv import (
    relation_get,
    relation_ids,
    related_units,
    )

from charmhelpers.contrib.openstack import (
    templating,
    context,
    )

from charmhelpers.contrib.hahelpers.utils import (
    juju_log,
    )

from charmhelpers.contrib.hahelpers.ceph_utils import (
    create_keyring as ceph_create_keyring,
    create_pool as ceph_create_pool,
    keyring_path as ceph_keyring_path,
    pool_exists as ceph_pool_exists,
    )

from charmhelpers.contrib.openstack.openstack_utils import (
    get_os_codename_install_source,
    get_os_codename_package,
    configure_installation_source,
    )

CHARM = "glance"

SERVICES = "glance-api glance-registry"
PACKAGES = "apache2 glance python-mysqldb python-swift python-keystone uuid haproxy"

GLANCE_REGISTRY_CONF = "/etc/glance/glance-registry.conf"
GLANCE_REGISTRY_PASTE_INI = "/etc/glance/glance-registry-paste.ini"
GLANCE_API_CONF = "/etc/glance/glance-api.conf"
GLANCE_API_PASTE_INI = "/etc/glance/glance-api-paste.ini"
CONF_DIR = "/etc/glance"

# Flag used to track config changes.
CONFIG_CHANGED =  False

TEMPLATES = 'templates/'

CONFIG_FILES = OrderedDict([
    ('/etc/glance/glance-registry.conf', {
        'hook_contexts': [context.SharedDBContext(),
                          context.IdentityServiceContext()],
        'services': ['glance-registry']
    }),
    ('/etc/glance/glance-api.conf', {
        'hook_contexts': [context.SharedDBContext(),
                          context.IdentityServiceContext(),
                          glance_contexts.CephContext(),
                          glance_contexts.ObjectStoreContext(),
                          glance_contexts.HAProxyContext()],
        'services': ['glance-api']
    }),
    ('/etc/glance/glance-api-paste.ini', {
        'hook_contexts': [context.IdentityServiceContext()],
        'services': ['glance-api']
    }),
    ('/etc/glance/glance-registry-paste.ini', {
        'hook_contexts': [context.IdentityServiceContext()],
        'services': ['glance-registry']
    }),
    ('/etc/ceph/ceph.conf', {
        'hook_contexts': [context.CephContext()],
        'services': []
    }),
    ('/etc/haproxy/haproxy.cfg', {
        'hook_contexts': [context.HAProxyContext(),
                          glance_contexts.HAProxyContext()],
        'services': ['haproxy'],
    }),
    ('/etc/apache2/sites-available/openstack_https_frontend', {
        'hook_contexts': [glance_contexts.ApacheSSLContext()],
        'services': ['apache2'],
    })
])

def register_configs():
    # Register config files with their respective contexts.
    # Regstration of some configs may not be required depending on
    # existing of certain relations.
    configs = templating.OSConfigRenderer(templates_dir=TEMPLATES,
                                          openstack_release='grizzly')

    confs = ['/etc/glance/glance-registry.conf',
             '/etc/glance/glance-api.conf',
             '/etc/glance/glance-api-paste.ini',
             '/etc/glance/glance-registry-paste.ini',
             '/etc/haproxy/haproxy.cfg',
             '/etc/apache2/sites-available/openstack_https_frontend',]

    if relation_ids('ceph'):
        confs.append('/etc/ceph/ceph.conf')

    for conf in confs:
        configs.register(conf, CONFIG_FILES[conf]['hook_contexts'])

    return configs


def migrate_database():
    '''Runs glance-manage to initialize a new database or migrate existing'''
    cmd = ['glance-manage', 'db_sync']
    subprocess.check_call(cmd)


def ensure_ceph_keyring(service):
    '''Ensures a ceph keyring exists.  Returns True if so, False otherwise'''
    # TODO: This can be shared between cinder + glance, find a home for it.
    key = None
    for rid in relation_ids('ceph'):
        for unit in related_units(rid):
            key = relation_get('key', rid=rid, unit=unit)
            if key:
                break
    if not key:
        return False
    ceph_create_keyring(service=service, key=key)
    keyring = ceph_keyring_path(service)
    subprocess.check_call(['chown', 'glance.glance', keyring])
    return True


def ensure_ceph_pool(service):
    '''Creates a ceph pool for service if one does not exist'''
    # TODO: Ditto about moving somewhere sharable.
    if not ceph_pool_exists(service=service, name=service):
        ceph_create_pool(service=service, name=service)


def set_ceph_env_variables(service):
    # XXX: Horrid kludge to make cinder-volume use
    # a different ceph username than admin
    env = open('/etc/environment', 'r').read()
    if 'CEPH_ARGS' not in env:
        with open('/etc/environment', 'a') as out:
            out.write('CEPH_ARGS="--id %s"\n' % service)
    with open('/etc/init/glance.override', 'w') as out:
        out.write('env CEPH_ARGS="--id %s"\n' % service)


def execute(cmd, die=False, echo=False):
    """ Executes a command

    if die=True, script will exit(1) if command does not return 0
    if echo=True, output of command will be printed to stdout

    returns a tuple: (stdout, stderr, return code)
    """
    p = subprocess.Popen(cmd.split(" "),
                         stdout=subprocess.PIPE, 
                         stdin=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    stdout = ""
    stderr = ""

    def print_line(l):
        if echo:
            print l.strip('\n')
            sys.stdout.flush()

    for l in iter(p.stdout.readline, ''):
        print_line(l)
        stdout += l
    for l in iter(p.stderr.readline, ''):
        print_line(l)
        stderr += l

    p.communicate()
    rc = p.returncode

    if die and rc != 0:
        juju_log('ERROR', 'command %s return non-zero.' % cmd)
    return (stdout, stderr, rc)


def do_openstack_upgrade(install_src, packages):
    # update openstack components to those provided by a new installation source
    # it is assumed the calling hook has confirmed that the upgrade is sane.
    #old_rel = get_os_codename_package('keystone')
    new_rel = get_os_codename_install_source(install_src)

    # Backup previous config.
    juju_log('INFO', "Backing up contents of /etc/glance.")
    stamp = time.strftime('%Y%m%d%H%M')
    cmd = 'tar -pcf /var/lib/juju/keystone-backup-%s.tar /etc/glance' % stamp
    execute(cmd, die=True, echo=True)

    # Setup apt repository access and kick off the actual package upgrade.
    configure_installation_source(install_src)
    execute('apt-get update', die=True, echo=True)
    os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
    cmd = 'apt-get --option Dpkg::Options::=--force-confnew -y '\
          'install %s --no-install-recommends' % packages
    execute(cmd, echo=True, die=True)
