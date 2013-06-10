#!/bin/bash

import os
import time
import sys
import subprocess

from lib.openstack_common import (
    get_os_codename_install_source,
    get_os_codename_package,
    configure_installation_source,
    )

from lib.utils import (
    relation_ids,
    relation_list,
    install,
    stop,
    juju_log,
    start,
    )

from lib.cluster_utils import (
    is_clustered,
    determine_haproxy_port,
    determine_api_port,
    peer_units,
    )

from lib.haproxy_utils import (
    configure_haproxy,
    )

from helpers.contrib.hahelpers.apache_utils import (
    get_cert,
    get_ca_cert,
    generate_cert,
    setup_https,
    )

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


# TODO: This is a temporary function.
def set_or_update(key=None, value=None, file=None, section=None):
    if not key:
        juju_log('ERROR', 'set_or_update(): value %s missing key' % value)
        sys.exit(1)
    if not value:
        juju_log('ERROR', 'set_or_update(): key %s missing value' % key)
        sys.exit(1)

    if file == "api":
        conf = GLANCE_API_CONF
    elif file == "api-paste":
        conf = GLANCE_API_PASTE_INI
    elif file == "registry":
        conf = GLANCE_REGISTRY_CONF
    elif file == "registry-paste":
        conf = GLANCE_REGISTRY_PASTE_INI
    else:
        juju_log('ERROR', 'set_or_update(): Invalid or no config file specified')
        sys.exit(1)

    if not os.path.exists(conf):
        juju_log('ERROR', 'set_or_update(): File not found %s' % conf)
        sys.exit(1)

    if local_config_get(conf=conf, option=key, section=section) == value:
        juju_log('INFO', '%s: set_or_update(): %s=%s already set in %s' % (CHARM, key, value, conf))
        return

    cfg_set_or_update(key, value, conf, section)
    CONFIG_CHANGED = True


def cfg_set_or_update(key=None, value=None, conf=None, section=None):
    if not section:
        section = "DEFAULT"

    import ConfigParser
    config = ConfigParser.RawConfigParser()
    config.read(conf)
    if section != "DEFAULT" and not config.has_section(section):
        config.add_section(section)
    config.set(section, key, value)
    with open(conf, 'wb') as conf_out:
        config.write(conf_out)

def local_config_get(conf=None, option=None, section=None):
    if not section:
        section = "DEFAULT"

    import ConfigParser
    config = ConfigParser.RawConfigParser()
    config.read(conf)
    try:
        value = config.get(section, option)
    except:
        return
    if value.startswith('%'):
        return
    return value


def do_openstack_upgrade(install_src, packages):
    # update openstack components to those provided by a new installation source
    # it is assumed the calling hook has confirmed that the upgrade is sane.
    old_rel = get_os_codename_package('keystone')
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


def configure_https():
    # request openstack-common setup reverse proxy mapping for API and registry
    # servers
    stop('glance-api')

    if len(peer_units()) > 0 or is_clustered():
        # haproxy may already be configured. need to push it back in the request
        # pipeline in preparation for a change from:
        #  from:  haproxy (9292) -> glance_api (9282)
        #  to:    ssl (9292) -> haproxy (9291) -> glance_api (9272)
        next_server = determine_haproxy_port('9292')
        api_port = determine_api_port('9292')
        service_ports = {
            "glance_api": [
                next_server,
                api_port
                ]
            }
        configure_haproxy(service_ports)
    else:
        # if not clustered, the glance-api is next in the pipeline.
        api_port = determine_api_port('9292')
        next_server = api_port

    cert, key = get_cert()
    if None in (cert, key):
        cert, key = generate_cert()
    ca_cert = get_ca_cert()
    # setup https to point to either haproxy or directly to api server, depending.
    setup_https(namespace="glance", port_maps={api_port: next_server},
                cert=cert, key=key, ca_cert=ca_cert)

    # configure servers to listen on new ports accordingly.
    set_or_update(key='bind_port', value=api_port, file='api')
    start(SERVICES)
