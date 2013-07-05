#!/usr/bin/python

import os
import time
import sys
import subprocess

from charmhelpers.contrib.openstack.openstack_utils import (
    get_os_codename_install_source,
    get_os_codename_package,
    configure_installation_source,
    )

from charmhelpers.contrib.hahelpers.utils import (
    juju_log,
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


