#!/usr/bin/python

# Common python helper functions used for OpenStack charms.

import apt_pkg as apt
import subprocess
import os
import sys

CLOUD_ARCHIVE_URL = "http://ubuntu-cloud.archive.canonical.com/ubuntu"
CLOUD_ARCHIVE_KEY_ID = '5EDB1B62EC4926EA'

ubuntu_openstack_release = {
    'oneiric': 'diablo',
    'precise': 'essex',
    'quantal': 'folsom',
    'raring': 'grizzly',
}


openstack_codenames = {
    '2011.2': 'diablo',
    '2012.1': 'essex',
    '2012.2': 'folsom',
    '2013.1': 'grizzly',
    '2013.2': 'havana',
}

# The ugly duckling
swift_codenames = {
    '1.4.3': 'diablo',
    '1.4.8': 'essex',
    '1.7.4': 'folsom',
    '1.7.6': 'grizzly',
    '1.7.7': 'grizzly',
    '1.8.0': 'grizzly',
}


def juju_log(msg):
    subprocess.check_call(['juju-log', msg])


def error_out(msg):
    juju_log("FATAL ERROR: %s" % msg)
    sys.exit(1)


def lsb_release():
    '''Return /etc/lsb-release in a dict'''
    lsb = open('/etc/lsb-release', 'r')
    d = {}
    for l in lsb:
        k, v = l.split('=')
        d[k.strip()] = v.strip()
    return d


def get_os_codename_install_source(src):
    '''Derive OpenStack release codename from a given installation source.'''
    ubuntu_rel = lsb_release()['DISTRIB_CODENAME']

    rel = ''
    if src == 'distro':
        try:
            rel = ubuntu_openstack_release[ubuntu_rel]
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
        for k, v in openstack_codenames.iteritems():
            if v in src:
                return v


def get_os_codename_version(vers):
    '''Determine OpenStack codename from version number.'''
    try:
        return openstack_codenames[vers]
    except KeyError:
        e = 'Could not determine OpenStack codename for version %s' % vers
        error_out(e)


def get_os_version_codename(codename):
    '''Determine OpenStack version number from codename.'''
    for k, v in openstack_codenames.iteritems():
        if v == codename:
            return k
    e = 'Could not derive OpenStack version for '\
        'codename: %s' % codename
    error_out(e)


def get_os_codename_package(pkg):
    '''Derive OpenStack release codename from an installed package.'''
    apt.init()
    cache = apt.Cache()

    try:
        pkg = cache[pkg]
    except:
        e = 'Could not determine version of installed package: %s' % pkg
        error_out(e)

    vers = apt.UpstreamVersion(pkg.current_ver.ver_str)

    try:
        if 'swift' in pkg.name:
            vers = vers[:5]
            return swift_codenames[vers]
        else:
            vers = vers[:6]
            return openstack_codenames[vers]
    except KeyError:
        e = 'Could not determine OpenStack codename for version %s' % vers
        error_out(e)


def get_os_version_package(pkg):
    '''Derive OpenStack version number from an installed package.'''
    codename = get_os_codename_package(pkg)

    if 'swift' in pkg:
        vers_map = swift_codenames
    else:
        vers_map = openstack_codenames

    for version, cname in vers_map.iteritems():
        if cname == codename:
            return version
    #e = "Could not determine OpenStack version for package: %s" % pkg
    #error_out(e)

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
            'grizzly/proposed': 'precise-proposed/grizzly'
        }

        try:
            pocket = pockets[ca_rel]
        except KeyError:
            e = 'Invalid Cloud Archive release specified: %s' % rel
            error_out(e)

        src = "deb %s %s main" % (CLOUD_ARCHIVE_URL, pocket)
        # TODO: Replace key import with cloud archive keyring pkg.
        import_key(CLOUD_ARCHIVE_KEY_ID)

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
    unit_name = os.getenv('JUJU_UNIT_NAME').replace('/', '-')
    juju_rc_path = "/var/lib/juju/units/%s/charm/%s" % (unit_name, script_path)
    with open(juju_rc_path, 'wb') as rc_script:
        rc_script.write(
            "#!/bin/bash\n")
        [rc_script.write('export %s=%s\n' % (u, p))
         for u, p in env_vars.iteritems() if u != "script_path"]
