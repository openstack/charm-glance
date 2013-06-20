#!/usr/bin/python

from charmhelpers.contrib.openstack import (
    templating,
    context,
    )

import subprocess

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

CONFIG_FILES = {
    '/etc/glance/glance-registry.conf': {
        'hook_contexts': [context.shared_db],
        'services': ['glance-registry']
    }
}

def register_configs():
    # Register config files with their respective contexts.
    # Regstration of some configs may not be required depending on
    # existing of certain relations.
    configs = templating.OSConfigRenderer(templates_dir=TEMPLATES,
                openstack_release='grizzly')

    confs = ['/etc/glance/glance-registry.conf']

    for conf in confs:
        configs.register(conf, CONFIG_FILES[conf]['hook_contexts'])

    return configs


def migrate_database():
    '''Runs glance-manage to initialize a new database or migrate existing'''
    cmd = ['glance-manage', 'db_sync']
    subprocess.check_call(cmd)
