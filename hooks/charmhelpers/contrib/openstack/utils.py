#!/usr/bin/python

# Common python helper functions used for OpenStack charms.

from collections import OrderedDict

import apt_pkg as apt
import subprocess
import os
import sys

from charmhelpers.core.hookenv import (
    config,
    log as juju_log,
    charm_dir,
)

from charmhelpers.core.host import (
    lsb_release,
    apt_install,
)

CLOUD_ARCHIVE_URL = "http://ubuntu-cloud.archive.canonical.com/ubuntu"
CLOUD_ARCHIVE_KEY_ID = '5EDB1B62EC4926EA'

UBUNTU_OPENSTACK_RELEASE = OrderedDict([
    ('oneiric', 'diablo'),
    ('precise', 'essex'),
    ('quantal', 'folsom'),
    ('raring', 'grizzly'),
    ('saucy', 'havana'),
])


OPENSTACK_CODENAMES = OrderedDict([
    ('2011.2', 'diablo'),
    ('2012.1', 'essex'),
    ('2012.2', 'folsom'),
    ('2013.1', 'grizzly'),
    ('2013.2', 'havana'),
    ('2014.1', 'icehouse'),
])

# The ugly duckling
SWIFT_CODENAMES = {
    '1.4.3': 'diablo',
    '1.4.8': 'essex',
    '1.7.4': 'folsom',
    '1.7.6': 'grizzly',
    '1.7.7': 'grizzly',
    '1.8.0': 'grizzly',
    '1.9.0': 'havana',
    '1.9.1': 'havana',
}


def error_out(msg):
    juju_log("FATAL ERROR: %s" % msg, level='ERROR')
    sys.exit(1)


def get_os_codename_install_source(src):
    '''Derive OpenStack release codename from a given installation source.'''
    ubuntu_rel = lsb_release()['DISTRIB_CODENAME']
    rel = ''
    if src == 'distro':
        try:
            rel = UBUNTU_OPENSTACK_RELEASE[ubuntu_rel]
        except KeyError:
            e = 'Could not derive openstack release for '\
                'this Ubuntu release: %s' % ubuntu_rel
            error_out(e)
        return rel

    if src.startswith('cloud:'):
        ca_rel = src.split(':')[1]
        ca_rel = ca_rel.split('%s-' % ubuntu_rel)[1].split('/')[0]
        return ca_rel

    # Best guess match based on deb string provided
    if src.startswith('deb') or src.startswith('ppa'):
        for k, v in OPENSTACK_CODENAMES.iteritems():
            if v in src:
                return v


def get_os_version_install_source(src):
    codename = get_os_codename_install_source(src)
    return get_os_version_codename(codename)


def get_os_codename_version(vers):
    '''Determine OpenStack codename from version number.'''
    try:
        return OPENSTACK_CODENAMES[vers]
    except KeyError:
        e = 'Could not determine OpenStack codename for version %s' % vers
        error_out(e)


def get_os_version_codename(codename):
    '''Determine OpenStack version number from codename.'''
    for k, v in OPENSTACK_CODENAMES.iteritems():
        if v == codename:
            return k
    e = 'Could not derive OpenStack version for '\
        'codename: %s' % codename
    error_out(e)


def get_os_codename_package(package, fatal=True):
    '''Derive OpenStack release codename from an installed package.'''
    apt.init()
    cache = apt.Cache()

    try:
        pkg = cache[package]
    except:
        if not fatal:
            return None
        # the package is unknown to the current apt cache.
        e = 'Could not determine version of package with no installation '\
            'candidate: %s' % package
        error_out(e)

    if not pkg.current_ver:
        if not fatal:
            return None
        # package is known, but no version is currently installed.
        e = 'Could not determine version of uninstalled package: %s' % package
        error_out(e)

    vers = apt.UpstreamVersion(pkg.current_ver.ver_str)

    try:
        if 'swift' in pkg.name:
            vers = vers[:5]
            return SWIFT_CODENAMES[vers]
        else:
            vers = vers[:6]
            return OPENSTACK_CODENAMES[vers]
    except KeyError:
        e = 'Could not determine OpenStack codename for version %s' % vers
        error_out(e)


def get_os_version_package(pkg, fatal=True):
    '''Derive OpenStack version number from an installed package.'''
    codename = get_os_codename_package(pkg, fatal=fatal)

    if not codename:
        return None

    if 'swift' in pkg:
        vers_map = SWIFT_CODENAMES
    else:
        vers_map = OPENSTACK_CODENAMES

    for version, cname in vers_map.iteritems():
        if cname == codename:
            return version
    #e = "Could not determine OpenStack version for package: %s" % pkg
    #error_out(e)


os_rel = None


def os_release(package, base='essex'):
    '''
    Returns OpenStack release codename from a cached global.
    If the codename can not be determined from either an installed package or
    the installation source, the earliest release supported by the charm should
    be returned.
    '''
    global os_rel
    if os_rel:
        return os_rel
    os_rel = (get_os_codename_package(package, fatal=False) or
              get_os_codename_install_source(config('openstack-origin')) or
              base)
    return os_rel


def import_key(keyid):
    cmd = "apt-key adv --keyserver keyserver.ubuntu.com " \
          "--recv-keys %s" % keyid
    try:
        subprocess.check_call(cmd.split(' '))
    except subprocess.CalledProcessError:
        error_out("Error importing repo key %s" % keyid)


def configure_installation_source(rel):
    '''Configure apt installation source.'''
    if rel == 'distro':
        return
    elif rel[:4] == "ppa:":
        src = rel
        subprocess.check_call(["add-apt-repository", "-y", src])
    elif rel[:3] == "deb":
        l = len(rel.split('|'))
        if l == 2:
            src, key = rel.split('|')
            juju_log("Importing PPA key from keyserver for %s" % src)
            import_key(key)
        elif l == 1:
            src = rel
        with open('/etc/apt/sources.list.d/juju_deb.list', 'w') as f:
            f.write(src)
    elif rel[:6] == 'cloud:':
        ubuntu_rel = lsb_release()['DISTRIB_CODENAME']
        rel = rel.split(':')[1]
        u_rel = rel.split('-')[0]
        ca_rel = rel.split('-')[1]

        if u_rel != ubuntu_rel:
            e = 'Cannot install from Cloud Archive pocket %s on this Ubuntu '\
                'version (%s)' % (ca_rel, ubuntu_rel)
            error_out(e)

        if 'staging' in ca_rel:
            # staging is just a regular PPA.
            os_rel = ca_rel.split('/')[0]
            ppa = 'ppa:ubuntu-cloud-archive/%s-staging' % os_rel
            cmd = 'add-apt-repository -y %s' % ppa
            subprocess.check_call(cmd.split(' '))
            return

        # map charm config options to actual archive pockets.
        pockets = {
            'folsom': 'precise-updates/folsom',
            'folsom/updates': 'precise-updates/folsom',
            'folsom/proposed': 'precise-proposed/folsom',
            'grizzly': 'precise-updates/grizzly',
            'grizzly/updates': 'precise-updates/grizzly',
            'grizzly/proposed': 'precise-proposed/grizzly',
            'havana': 'precise-updates/havana',
            'havana/updates': 'precise-updates/havana',
            'havana/proposed': 'precise-proposed/havana',
        }

        try:
            pocket = pockets[ca_rel]
        except KeyError:
            e = 'Invalid Cloud Archive release specified: %s' % rel
            error_out(e)

        src = "deb %s %s main" % (CLOUD_ARCHIVE_URL, pocket)
        apt_install('ubuntu-cloud-keyring', fatal=True)

        with open('/etc/apt/sources.list.d/cloud-archive.list', 'w') as f:
            f.write(src)
    else:
        error_out("Invalid openstack-release specified: %s" % rel)


def save_script_rc(script_path="scripts/scriptrc", **env_vars):
    """
    Write an rc file in the charm-delivered directory containing
    exported environment variables provided by env_vars. Any charm scripts run
    outside the juju hook environment can source this scriptrc to obtain
    updated config information necessary to perform health checks or
    service changes.
    """
    juju_rc_path = "%s/%s" % (charm_dir(), script_path)
    if not os.path.exists(os.path.dirname(juju_rc_path)):
        os.mkdir(os.path.dirname(juju_rc_path))
    with open(juju_rc_path, 'wb') as rc_script:
        rc_script.write(
            "#!/bin/bash\n")
        [rc_script.write('export %s=%s\n' % (u, p))
         for u, p in env_vars.iteritems() if u != "script_path"]


def openstack_upgrade_available(package):
    """
    Determines if an OpenStack upgrade is available from installation
    source, based on version of installed package.

    :param package: str: Name of installed package.

    :returns: bool:    : Returns True if configured installation source offers
                         a newer version of package.

    """

    src = config('openstack-origin')
    cur_vers = get_os_version_package(package)
    available_vers = get_os_version_install_source(src)
    apt.init()
    return apt.version_compare(available_vers, cur_vers) == 1
