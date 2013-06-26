#!/usr/bin/python

from charmhelpers.core.hookenv import (
    config,
    relation_get,
    relation_ids,
    related_units,
    log,
    )

from charmhelpers.contrib.openstack import (
    templating,
    context,
    )

from charmhelpers.contrib.hahelpers.ceph_utils import (
    create_keyring as ceph_create_keyring,
    create_pool as ceph_create_pool,
    keyring_path as ceph_keyring_path,
    pool_exists as ceph_pool_exists,
    )

from collections import OrderedDict

import subprocess

import glance_contexts

CHARM = "glance"

SERVICES = "glance-api glance-registry"
PACKAGES = "glance python-mysqldb python-swift python-keystone uuid haproxy"

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
                          glance_contexts.CephContext()],
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
             '/etc/glance/glance-registry-paste.ini',]

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
