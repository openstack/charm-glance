import importlib
from yaml import safe_load
from charmhelpers.core.host import (
    lsb_release
)
from urlparse import (
    urlparse,
    urlunparse,
)
import subprocess
from charmhelpers.core.hookenv import (
    config,
    log,
)
import apt_pkg
import os

CLOUD_ARCHIVE = """# Ubuntu Cloud Archive
deb http://ubuntu-cloud.archive.canonical.com/ubuntu {} main
"""
PROPOSED_POCKET = """# Proposed
deb http://archive.ubuntu.com/ubuntu {}-proposed main universe multiverse restricted
"""
CLOUD_ARCHIVE_POCKETS = {
    # Folsom
    'folsom': 'precise-updates/folsom',
    'precise-folsom': 'precise-updates/folsom',
    'precise-folsom/updates': 'precise-updates/folsom',
    'precise-updates/folsom': 'precise-updates/folsom',
    'folsom/proposed': 'precise-proposed/folsom',
    'precise-folsom/proposed': 'precise-proposed/folsom',
    'precise-proposed/folsom': 'precise-proposed/folsom',
    # Grizzly
    'grizzly': 'precise-updates/grizzly',
    'precise-grizzly': 'precise-updates/grizzly',
    'precise-grizzly/updates': 'precise-updates/grizzly',
    'precise-updates/grizzly': 'precise-updates/grizzly',
    'grizzly/proposed': 'precise-proposed/grizzly',
    'precise-grizzly/proposed': 'precise-proposed/grizzly',
    'precise-proposed/grizzly': 'precise-proposed/grizzly',
    # Havana
    'havana': 'precise-updates/havana',
    'precise-havana': 'precise-updates/havana',
    'precise-havana/updates': 'precise-updates/havana',
    'precise-updates/havana': 'precise-updates/havana',
    'havana/proposed': 'precise-proposed/havana',
    'precise-havana/proposed': 'precise-proposed/havana',
    'precise-proposed/havana': 'precise-proposed/havana',
    # Icehouse
    'icehouse': 'precise-updates/icehouse',
    'precise-icehouse': 'precise-updates/icehouse',
    'precise-icehouse/updates': 'precise-updates/icehouse',
    'precise-updates/icehouse': 'precise-updates/icehouse',
    'icehouse/proposed': 'precise-proposed/icehouse',
    'precise-icehouse/proposed': 'precise-proposed/icehouse',
    'precise-proposed/icehouse': 'precise-proposed/icehouse',
}


def filter_installed_packages(packages):
    """Returns a list of packages that require installation"""
    apt_pkg.init()
    cache = apt_pkg.Cache()
    _pkgs = []
    for package in packages:
        try:
            p = cache[package]
            p.current_ver or _pkgs.append(package)
        except KeyError:
            log('Package {} has no installation candidate.'.format(package),
                level='WARNING')
            _pkgs.append(package)
    return _pkgs


def apt_install(packages, options=None, fatal=False):
    """Install one or more packages"""
    if options is None:
        options = ['--option=Dpkg::Options::=--force-confold']

    cmd = ['apt-get', '--assume-yes']
    cmd.extend(options)
    cmd.append('install')
    if isinstance(packages, basestring):
        cmd.append(packages)
    else:
        cmd.extend(packages)
    log("Installing {} with options: {}".format(packages,
                                                options))
    env = os.environ.copy()
    if 'DEBIAN_FRONTEND' not in env:
        env['DEBIAN_FRONTEND'] = 'noninteractive'

    if fatal:
        subprocess.check_call(cmd, env=env)
    else:
        subprocess.call(cmd, env=env)


def apt_upgrade(options=None, fatal=False, dist=False):
    """Upgrade all packages"""
    if options is None:
        options = ['--option=Dpkg::Options::=--force-confold']

    cmd = ['apt-get', '--assume-yes']
    cmd.extend(options)
    if dist:
        cmd.append('dist-upgrade')
    else:
        cmd.append('upgrade')
    log("Upgrading with options: {}".format(options))

    env = os.environ.copy()
    if 'DEBIAN_FRONTEND' not in env:
        env['DEBIAN_FRONTEND'] = 'noninteractive'

    if fatal:
        subprocess.check_call(cmd, env=env)
    else:
        subprocess.call(cmd, env=env)


def apt_update(fatal=False):
    """Update local apt cache"""
    cmd = ['apt-get', 'update']
    if fatal:
        subprocess.check_call(cmd)
    else:
        subprocess.call(cmd)


def apt_purge(packages, fatal=False):
    """Purge one or more packages"""
    cmd = ['apt-get', '--assume-yes', 'purge']
    if isinstance(packages, basestring):
        cmd.append(packages)
    else:
        cmd.extend(packages)
    log("Purging {}".format(packages))
    if fatal:
        subprocess.check_call(cmd)
    else:
        subprocess.call(cmd)


def apt_hold(packages, fatal=False):
    """Hold one or more packages"""
    cmd = ['apt-mark', 'hold']
    if isinstance(packages, basestring):
        cmd.append(packages)
    else:
        cmd.extend(packages)
    log("Holding {}".format(packages))
    if fatal:
        subprocess.check_call(cmd)
    else:
        subprocess.call(cmd)


def add_source(source, key=None):
    if source is None:
        log('Source is not present. Skipping')
        return

    if (source.startswith('ppa:') or
        source.startswith('http') or
        source.startswith('deb ') or
            source.startswith('cloud-archive:')):
        subprocess.check_call(['add-apt-repository', '--yes', source])
    elif source.startswith('cloud:'):
        apt_install(filter_installed_packages(['ubuntu-cloud-keyring']),
                    fatal=True)
        pocket = source.split(':')[-1]
        if pocket not in CLOUD_ARCHIVE_POCKETS:
            raise SourceConfigError(
                'Unsupported cloud: source option %s' %
                pocket)
        actual_pocket = CLOUD_ARCHIVE_POCKETS[pocket]
        with open('/etc/apt/sources.list.d/cloud-archive.list', 'w') as apt:
            apt.write(CLOUD_ARCHIVE.format(actual_pocket))
    elif source == 'proposed':
        release = lsb_release()['DISTRIB_CODENAME']
        with open('/etc/apt/sources.list.d/proposed.list', 'w') as apt:
            apt.write(PROPOSED_POCKET.format(release))
    if key:
        subprocess.check_call(['apt-key', 'adv', '--keyserver',
                               'hkp://keyserver.ubuntu.com:80', '--recv',
                               key])


class SourceConfigError(Exception):
    pass


def configure_sources(update=False,
                      sources_var='install_sources',
                      keys_var='install_keys'):
    """
    Configure multiple sources from charm configuration

    Example config:
        install_sources:
          - "ppa:foo"
          - "http://example.com/repo precise main"
        install_keys:
          - null
          - "a1b2c3d4"

    Note that 'null' (a.k.a. None) should not be quoted.
    """
    sources = safe_load(config(sources_var))
    keys = config(keys_var)
    if keys is not None:
        keys = safe_load(keys)
    if isinstance(sources, basestring) and (
            keys is None or isinstance(keys, basestring)):
        add_source(sources, keys)
    else:
        if not len(sources) == len(keys):
            msg = 'Install sources and keys lists are different lengths'
            raise SourceConfigError(msg)
        for src_num in range(len(sources)):
            add_source(sources[src_num], keys[src_num])
    if update:
        apt_update(fatal=True)

# The order of this list is very important. Handlers should be listed in from
# least- to most-specific URL matching.
FETCH_HANDLERS = (
    'charmhelpers.fetch.archiveurl.ArchiveUrlFetchHandler',
    'charmhelpers.fetch.bzrurl.BzrUrlFetchHandler',
)


class UnhandledSource(Exception):
    pass


def install_remote(source):
    """
    Install a file tree from a remote source

    The specified source should be a url of the form:
        scheme://[host]/path[#[option=value][&...]]

    Schemes supported are based on this modules submodules
    Options supported are submodule-specific"""
    # We ONLY check for True here because can_handle may return a string
    # explaining why it can't handle a given source.
    handlers = [h for h in plugins() if h.can_handle(source) is True]
    installed_to = None
    for handler in handlers:
        try:
            installed_to = handler.install(source)
        except UnhandledSource:
            pass
    if not installed_to:
        raise UnhandledSource("No handler found for source {}".format(source))
    return installed_to


def install_from_config(config_var_name):
    charm_config = config()
    source = charm_config[config_var_name]
    return install_remote(source)


class BaseFetchHandler(object):

    """Base class for FetchHandler implementations in fetch plugins"""

    def can_handle(self, source):
        """Returns True if the source can be handled. Otherwise returns
        a string explaining why it cannot"""
        return "Wrong source type"

    def install(self, source):
        """Try to download and unpack the source. Return the path to the
        unpacked files or raise UnhandledSource."""
        raise UnhandledSource("Wrong source type {}".format(source))

    def parse_url(self, url):
        return urlparse(url)

    def base_url(self, url):
        """Return url without querystring or fragment"""
        parts = list(self.parse_url(url))
        parts[4:] = ['' for i in parts[4:]]
        return urlunparse(parts)


def plugins(fetch_handlers=None):
    if not fetch_handlers:
        fetch_handlers = FETCH_HANDLERS
    plugin_list = []
    for handler_name in fetch_handlers:
        package, classname = handler_name.rsplit('.', 1)
        try:
            handler_class = getattr(
                importlib.import_module(package),
                classname)
            plugin_list.append(handler_class())
        except (ImportError, AttributeError):
            # Skip missing plugins so that they can be ommitted from
            # installation if desired
            log("FetchHandler {} not found, skipping plugin".format(
                handler_name))
    return plugin_list
