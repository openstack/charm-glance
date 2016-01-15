# Copyright 2014-2015 Canonical Limited.
#
# This file is part of charm-helpers.
#
# charm-helpers is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3 as
# published by the Free Software Foundation.
#
# charm-helpers is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with charm-helpers.  If not, see <http://www.gnu.org/licenses/>.

# Common python helper functions used for OpenStack charms.
from collections import OrderedDict
from functools import wraps

import subprocess
import json
import os
import sys
import re

import six
import traceback
import uuid
import yaml

from charmhelpers.contrib.network import ip

from charmhelpers.core import (
    unitdata,
)

from charmhelpers.core.hookenv import (
    action_fail,
    action_set,
    config,
    log as juju_log,
    charm_dir,
    INFO,
    related_units,
    relation_ids,
    relation_set,
    status_set,
    hook_name
)

from charmhelpers.contrib.storage.linux.lvm import (
    deactivate_lvm_volume_group,
    is_lvm_physical_volume,
    remove_lvm_physical_volume,
)

from charmhelpers.contrib.network.ip import (
    get_ipv6_addr,
    is_ipv6,
)

from charmhelpers.contrib.python.packages import (
    pip_create_virtualenv,
    pip_install,
)

from charmhelpers.core.host import lsb_release, mounts, umount
from charmhelpers.fetch import apt_install, apt_cache, install_remote
from charmhelpers.contrib.storage.linux.utils import is_block_device, zap_disk
from charmhelpers.contrib.storage.linux.loopback import ensure_loopback_device

CLOUD_ARCHIVE_URL = "http://ubuntu-cloud.archive.canonical.com/ubuntu"
CLOUD_ARCHIVE_KEY_ID = '5EDB1B62EC4926EA'

DISTRO_PROPOSED = ('deb http://archive.ubuntu.com/ubuntu/ %s-proposed '
                   'restricted main multiverse universe')

UBUNTU_OPENSTACK_RELEASE = OrderedDict([
    ('oneiric', 'diablo'),
    ('precise', 'essex'),
    ('quantal', 'folsom'),
    ('raring', 'grizzly'),
    ('saucy', 'havana'),
    ('trusty', 'icehouse'),
    ('utopic', 'juno'),
    ('vivid', 'kilo'),
    ('wily', 'liberty'),
    ('xenial', 'mitaka'),
])


OPENSTACK_CODENAMES = OrderedDict([
    ('2011.2', 'diablo'),
    ('2012.1', 'essex'),
    ('2012.2', 'folsom'),
    ('2013.1', 'grizzly'),
    ('2013.2', 'havana'),
    ('2014.1', 'icehouse'),
    ('2014.2', 'juno'),
    ('2015.1', 'kilo'),
    ('2015.2', 'liberty'),
    ('2016.1', 'mitaka'),
])

# The ugly duckling
SWIFT_CODENAMES = OrderedDict([
    ('1.4.3', 'diablo'),
    ('1.4.8', 'essex'),
    ('1.7.4', 'folsom'),
    ('1.8.0', 'grizzly'),
    ('1.7.7', 'grizzly'),
    ('1.7.6', 'grizzly'),
    ('1.10.0', 'havana'),
    ('1.9.1', 'havana'),
    ('1.9.0', 'havana'),
    ('1.13.1', 'icehouse'),
    ('1.13.0', 'icehouse'),
    ('1.12.0', 'icehouse'),
    ('1.11.0', 'icehouse'),
    ('2.0.0', 'juno'),
    ('2.1.0', 'juno'),
    ('2.2.0', 'juno'),
    ('2.2.1', 'kilo'),
    ('2.2.2', 'kilo'),
    ('2.3.0', 'liberty'),
    ('2.4.0', 'liberty'),
    ('2.5.0', 'liberty'),
])

# >= Liberty version->codename mapping
PACKAGE_CODENAMES = {
    'nova-common': OrderedDict([
        ('12.0', 'liberty'),
        ('13.0', 'mitaka'),
    ]),
    'neutron-common': OrderedDict([
        ('7.0', 'liberty'),
        ('8.0', 'mitaka'),
    ]),
    'cinder-common': OrderedDict([
        ('7.0', 'liberty'),
        ('8.0', 'mitaka'),
    ]),
    'keystone': OrderedDict([
        ('8.0', 'liberty'),
        ('9.0', 'mitaka'),
    ]),
    'horizon-common': OrderedDict([
        ('8.0', 'liberty'),
        ('9.0', 'mitaka'),
    ]),
    'ceilometer-common': OrderedDict([
        ('5.0', 'liberty'),
        ('6.0', 'mitaka'),
    ]),
    'heat-common': OrderedDict([
        ('5.0', 'liberty'),
        ('6.0', 'mitaka'),
    ]),
    'glance-common': OrderedDict([
        ('11.0', 'liberty'),
        ('12.0', 'mitaka'),
    ]),
    'openstack-dashboard': OrderedDict([
        ('8.0', 'liberty'),
        ('9.0', 'mitaka'),
    ]),
}

DEFAULT_LOOPBACK_SIZE = '5G'


def error_out(msg):
    juju_log("FATAL ERROR: %s" % msg, level='ERROR')
    sys.exit(1)


def get_os_codename_install_source(src):
    '''Derive OpenStack release codename from a given installation source.'''
    ubuntu_rel = lsb_release()['DISTRIB_CODENAME']
    rel = ''
    if src is None:
        return rel
    if src in ['distro', 'distro-proposed']:
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
        for k, v in six.iteritems(OPENSTACK_CODENAMES):
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


def get_os_version_codename(codename, version_map=OPENSTACK_CODENAMES):
    '''Determine OpenStack version number from codename.'''
    for k, v in six.iteritems(version_map):
        if v == codename:
            return k
    e = 'Could not derive OpenStack version for '\
        'codename: %s' % codename
    error_out(e)


def get_os_codename_package(package, fatal=True):
    '''Derive OpenStack release codename from an installed package.'''
    import apt_pkg as apt

    cache = apt_cache()

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

    vers = apt.upstream_version(pkg.current_ver.ver_str)
    if 'swift' in pkg.name:
        # Fully x.y.z match for swift versions
        match = re.match('^(\d+)\.(\d+)\.(\d+)', vers)
    else:
        # x.y match only for 20XX.X
        # and ignore patch level for other packages
        match = re.match('^(\d+)\.(\d+)', vers)

    if match:
        vers = match.group(0)

    # >= Liberty independent project versions
    if (package in PACKAGE_CODENAMES and
            vers in PACKAGE_CODENAMES[package]):
        return PACKAGE_CODENAMES[package][vers]
    else:
        # < Liberty co-ordinated project versions
        try:
            if 'swift' in pkg.name:
                return SWIFT_CODENAMES[vers]
            else:
                return OPENSTACK_CODENAMES[vers]
        except KeyError:
            if not fatal:
                return None
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

    for version, cname in six.iteritems(vers_map):
        if cname == codename:
            return version
    # e = "Could not determine OpenStack version for package: %s" % pkg
    # error_out(e)


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
    cmd = "apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 " \
          "--recv-keys %s" % keyid
    try:
        subprocess.check_call(cmd.split(' '))
    except subprocess.CalledProcessError:
        error_out("Error importing repo key %s" % keyid)


def configure_installation_source(rel):
    '''Configure apt installation source.'''
    if rel == 'distro':
        return
    elif rel == 'distro-proposed':
        ubuntu_rel = lsb_release()['DISTRIB_CODENAME']
        with open('/etc/apt/sources.list.d/juju_deb.list', 'w') as f:
            f.write(DISTRO_PROPOSED % ubuntu_rel)
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
            'icehouse': 'precise-updates/icehouse',
            'icehouse/updates': 'precise-updates/icehouse',
            'icehouse/proposed': 'precise-proposed/icehouse',
            'juno': 'trusty-updates/juno',
            'juno/updates': 'trusty-updates/juno',
            'juno/proposed': 'trusty-proposed/juno',
            'kilo': 'trusty-updates/kilo',
            'kilo/updates': 'trusty-updates/kilo',
            'kilo/proposed': 'trusty-proposed/kilo',
            'liberty': 'trusty-updates/liberty',
            'liberty/updates': 'trusty-updates/liberty',
            'liberty/proposed': 'trusty-proposed/liberty',
            'mitaka': 'trusty-updates/mitaka',
            'mitaka/updates': 'trusty-updates/mitaka',
            'mitaka/proposed': 'trusty-proposed/mitaka',
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


def config_value_changed(option):
    """
    Determine if config value changed since last call to this function.
    """
    hook_data = unitdata.HookData()
    with hook_data():
        db = unitdata.kv()
        current = config(option)
        saved = db.get(option)
        db.set(option, current)
        if saved is None:
            return False
        return current != saved


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
         for u, p in six.iteritems(env_vars) if u != "script_path"]


def openstack_upgrade_available(package):
    """
    Determines if an OpenStack upgrade is available from installation
    source, based on version of installed package.

    :param package: str: Name of installed package.

    :returns: bool:    : Returns True if configured installation source offers
                         a newer version of package.

    """

    import apt_pkg as apt
    src = config('openstack-origin')
    cur_vers = get_os_version_package(package)
    if "swift" in package:
        codename = get_os_codename_install_source(src)
        available_vers = get_os_version_codename(codename, SWIFT_CODENAMES)
    else:
        available_vers = get_os_version_install_source(src)
    apt.init()
    return apt.version_compare(available_vers, cur_vers) == 1


def ensure_block_device(block_device):
    '''
    Confirm block_device, create as loopback if necessary.

    :param block_device: str: Full path of block device to ensure.

    :returns: str: Full path of ensured block device.
    '''
    _none = ['None', 'none', None]
    if (block_device in _none):
        error_out('prepare_storage(): Missing required input: block_device=%s.'
                  % block_device)

    if block_device.startswith('/dev/'):
        bdev = block_device
    elif block_device.startswith('/'):
        _bd = block_device.split('|')
        if len(_bd) == 2:
            bdev, size = _bd
        else:
            bdev = block_device
            size = DEFAULT_LOOPBACK_SIZE
        bdev = ensure_loopback_device(bdev, size)
    else:
        bdev = '/dev/%s' % block_device

    if not is_block_device(bdev):
        error_out('Failed to locate valid block device at %s' % bdev)

    return bdev


def clean_storage(block_device):
    '''
    Ensures a block device is clean.  That is:
        - unmounted
        - any lvm volume groups are deactivated
        - any lvm physical device signatures removed
        - partition table wiped

    :param block_device: str: Full path to block device to clean.
    '''
    for mp, d in mounts():
        if d == block_device:
            juju_log('clean_storage(): %s is mounted @ %s, unmounting.' %
                     (d, mp), level=INFO)
            umount(mp, persist=True)

    if is_lvm_physical_volume(block_device):
        deactivate_lvm_volume_group(block_device)
        remove_lvm_physical_volume(block_device)
    else:
        zap_disk(block_device)

is_ip = ip.is_ip
ns_query = ip.ns_query
get_host_ip = ip.get_host_ip
get_hostname = ip.get_hostname


def get_matchmaker_map(mm_file='/etc/oslo/matchmaker_ring.json'):
    mm_map = {}
    if os.path.isfile(mm_file):
        with open(mm_file, 'r') as f:
            mm_map = json.load(f)
    return mm_map


def sync_db_with_multi_ipv6_addresses(database, database_user,
                                      relation_prefix=None):
    hosts = get_ipv6_addr(dynamic_only=False)

    if config('vip'):
        vips = config('vip').split()
        for vip in vips:
            if vip and is_ipv6(vip):
                hosts.append(vip)

    kwargs = {'database': database,
              'username': database_user,
              'hostname': json.dumps(hosts)}

    if relation_prefix:
        for key in list(kwargs.keys()):
            kwargs["%s_%s" % (relation_prefix, key)] = kwargs[key]
            del kwargs[key]

    for rid in relation_ids('shared-db'):
        relation_set(relation_id=rid, **kwargs)


def os_requires_version(ostack_release, pkg):
    """
    Decorator for hook to specify minimum supported release
    """
    def wrap(f):
        @wraps(f)
        def wrapped_f(*args):
            if os_release(pkg) < ostack_release:
                raise Exception("This hook is not supported on releases"
                                " before %s" % ostack_release)
            f(*args)
        return wrapped_f
    return wrap


def git_install_requested():
    """
    Returns true if openstack-origin-git is specified.
    """
    return config('openstack-origin-git') is not None


requirements_dir = None


def _git_yaml_load(projects_yaml):
    """
    Load the specified yaml into a dictionary.
    """
    if not projects_yaml:
        return None

    return yaml.load(projects_yaml)


def git_clone_and_install(projects_yaml, core_project):
    """
    Clone/install all specified OpenStack repositories.

    The expected format of projects_yaml is:

        repositories:
          - {name: keystone,
             repository: 'git://git.openstack.org/openstack/keystone.git',
             branch: 'stable/icehouse'}
          - {name: requirements,
             repository: 'git://git.openstack.org/openstack/requirements.git',
             branch: 'stable/icehouse'}

        directory: /mnt/openstack-git
        http_proxy: squid-proxy-url
        https_proxy: squid-proxy-url

    The directory, http_proxy, and https_proxy keys are optional.

    """
    global requirements_dir
    parent_dir = '/mnt/openstack-git'
    http_proxy = None

    projects = _git_yaml_load(projects_yaml)
    _git_validate_projects_yaml(projects, core_project)

    old_environ = dict(os.environ)

    if 'http_proxy' in projects.keys():
        http_proxy = projects['http_proxy']
        os.environ['http_proxy'] = projects['http_proxy']
    if 'https_proxy' in projects.keys():
        os.environ['https_proxy'] = projects['https_proxy']

    if 'directory' in projects.keys():
        parent_dir = projects['directory']

    pip_create_virtualenv(os.path.join(parent_dir, 'venv'))

    # Upgrade setuptools and pip from default virtualenv versions. The default
    # versions in trusty break master OpenStack branch deployments.
    for p in ['pip', 'setuptools']:
        pip_install(p, upgrade=True, proxy=http_proxy,
                    venv=os.path.join(parent_dir, 'venv'))

    for p in projects['repositories']:
        repo = p['repository']
        branch = p['branch']
        depth = '1'
        if 'depth' in p.keys():
            depth = p['depth']
        if p['name'] == 'requirements':
            repo_dir = _git_clone_and_install_single(repo, branch, depth,
                                                     parent_dir, http_proxy,
                                                     update_requirements=False)
            requirements_dir = repo_dir
        else:
            repo_dir = _git_clone_and_install_single(repo, branch, depth,
                                                     parent_dir, http_proxy,
                                                     update_requirements=True)

    os.environ = old_environ


def _git_validate_projects_yaml(projects, core_project):
    """
    Validate the projects yaml.
    """
    _git_ensure_key_exists('repositories', projects)

    for project in projects['repositories']:
        _git_ensure_key_exists('name', project.keys())
        _git_ensure_key_exists('repository', project.keys())
        _git_ensure_key_exists('branch', project.keys())

    if projects['repositories'][0]['name'] != 'requirements':
        error_out('{} git repo must be specified first'.format('requirements'))

    if projects['repositories'][-1]['name'] != core_project:
        error_out('{} git repo must be specified last'.format(core_project))


def _git_ensure_key_exists(key, keys):
    """
    Ensure that key exists in keys.
    """
    if key not in keys:
        error_out('openstack-origin-git key \'{}\' is missing'.format(key))


def _git_clone_and_install_single(repo, branch, depth, parent_dir, http_proxy,
                                  update_requirements):
    """
    Clone and install a single git repository.
    """
    if not os.path.exists(parent_dir):
        juju_log('Directory already exists at {}. '
                 'No need to create directory.'.format(parent_dir))
        os.mkdir(parent_dir)

    juju_log('Cloning git repo: {}, branch: {}'.format(repo, branch))
    repo_dir = install_remote(repo, dest=parent_dir, branch=branch, depth=depth)

    venv = os.path.join(parent_dir, 'venv')

    if update_requirements:
        if not requirements_dir:
            error_out('requirements repo must be cloned before '
                      'updating from global requirements.')
        _git_update_requirements(venv, repo_dir, requirements_dir)

    juju_log('Installing git repo from dir: {}'.format(repo_dir))
    if http_proxy:
        pip_install(repo_dir, proxy=http_proxy, venv=venv)
    else:
        pip_install(repo_dir, venv=venv)

    return repo_dir


def _git_update_requirements(venv, package_dir, reqs_dir):
    """
    Update from global requirements.

    Update an OpenStack git directory's requirements.txt and
    test-requirements.txt from global-requirements.txt.
    """
    orig_dir = os.getcwd()
    os.chdir(reqs_dir)
    python = os.path.join(venv, 'bin/python')
    cmd = [python, 'update.py', package_dir]
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError:
        package = os.path.basename(package_dir)
        error_out("Error updating {} from "
                  "global-requirements.txt".format(package))
    os.chdir(orig_dir)


def git_pip_venv_dir(projects_yaml):
    """
    Return the pip virtualenv path.
    """
    parent_dir = '/mnt/openstack-git'

    projects = _git_yaml_load(projects_yaml)

    if 'directory' in projects.keys():
        parent_dir = projects['directory']

    return os.path.join(parent_dir, 'venv')


def git_src_dir(projects_yaml, project):
    """
    Return the directory where the specified project's source is located.
    """
    parent_dir = '/mnt/openstack-git'

    projects = _git_yaml_load(projects_yaml)

    if 'directory' in projects.keys():
        parent_dir = projects['directory']

    for p in projects['repositories']:
        if p['name'] == project:
            return os.path.join(parent_dir, os.path.basename(p['repository']))

    return None


def git_yaml_value(projects_yaml, key):
    """
    Return the value in projects_yaml for the specified key.
    """
    projects = _git_yaml_load(projects_yaml)

    if key in projects.keys():
        return projects[key]

    return None


def os_workload_status(configs, required_interfaces, charm_func=None):
    """
    Decorator to set workload status based on complete contexts
    """
    def wrap(f):
        @wraps(f)
        def wrapped_f(*args, **kwargs):
            # Run the original function first
            f(*args, **kwargs)
            # Set workload status now that contexts have been
            # acted on
            set_os_workload_status(configs, required_interfaces, charm_func)
        return wrapped_f
    return wrap


def set_os_workload_status(configs, required_interfaces, charm_func=None):
    """
    Set workload status based on complete contexts.
    status-set missing or incomplete contexts
    and juju-log details of missing required data.
    charm_func is a charm specific function to run checking
    for charm specific requirements such as a VIP setting.
    """
    incomplete_rel_data = incomplete_relation_data(configs, required_interfaces)
    state = 'active'
    missing_relations = []
    incomplete_relations = []
    message = None
    charm_state = None
    charm_message = None

    for generic_interface in incomplete_rel_data.keys():
        related_interface = None
        missing_data = {}
        # Related or not?
        for interface in incomplete_rel_data[generic_interface]:
            if incomplete_rel_data[generic_interface][interface].get('related'):
                related_interface = interface
                missing_data = incomplete_rel_data[generic_interface][interface].get('missing_data')
        # No relation ID for the generic_interface
        if not related_interface:
            juju_log("{} relation is missing and must be related for "
                     "functionality. ".format(generic_interface), 'WARN')
            state = 'blocked'
            if generic_interface not in missing_relations:
                missing_relations.append(generic_interface)
        else:
            # Relation ID exists but no related unit
            if not missing_data:
                # Edge case relation ID exists but departing
                if ('departed' in hook_name() or 'broken' in hook_name()) \
                        and related_interface in hook_name():
                    state = 'blocked'
                    if generic_interface not in missing_relations:
                        missing_relations.append(generic_interface)
                    juju_log("{} relation's interface, {}, "
                             "relationship is departed or broken "
                             "and is required for functionality."
                             "".format(generic_interface, related_interface), "WARN")
                # Normal case relation ID exists but no related unit
                # (joining)
                else:
                    juju_log("{} relations's interface, {}, is related but has "
                             "no units in the relation."
                             "".format(generic_interface, related_interface), "INFO")
            # Related unit exists and data missing on the relation
            else:
                juju_log("{} relation's interface, {}, is related awaiting "
                         "the following data from the relationship: {}. "
                         "".format(generic_interface, related_interface,
                                   ", ".join(missing_data)), "INFO")
            if state != 'blocked':
                state = 'waiting'
            if generic_interface not in incomplete_relations \
                    and generic_interface not in missing_relations:
                incomplete_relations.append(generic_interface)

    if missing_relations:
        message = "Missing relations: {}".format(", ".join(missing_relations))
        if incomplete_relations:
            message += "; incomplete relations: {}" \
                       "".format(", ".join(incomplete_relations))
        state = 'blocked'
    elif incomplete_relations:
        message = "Incomplete relations: {}" \
                  "".format(", ".join(incomplete_relations))
        state = 'waiting'

    # Run charm specific checks
    if charm_func:
        charm_state, charm_message = charm_func(configs)
        if charm_state != 'active' and charm_state != 'unknown':
            state = workload_state_compare(state, charm_state)
            if message:
                charm_message = charm_message.replace("Incomplete relations: ",
                                                      "")
                message = "{}, {}".format(message, charm_message)
            else:
                message = charm_message

    # Set to active if all requirements have been met
    if state == 'active':
        message = "Unit is ready"
        juju_log(message, "INFO")

    status_set(state, message)


def workload_state_compare(current_workload_state, workload_state):
    """ Return highest priority of two states"""
    hierarchy = {'unknown': -1,
                 'active': 0,
                 'maintenance': 1,
                 'waiting': 2,
                 'blocked': 3,
                 }

    if hierarchy.get(workload_state) is None:
        workload_state = 'unknown'
    if hierarchy.get(current_workload_state) is None:
        current_workload_state = 'unknown'

    # Set workload_state based on hierarchy of statuses
    if hierarchy.get(current_workload_state) > hierarchy.get(workload_state):
        return current_workload_state
    else:
        return workload_state


def incomplete_relation_data(configs, required_interfaces):
    """
    Check complete contexts against required_interfaces
    Return dictionary of incomplete relation data.

    configs is an OSConfigRenderer object with configs registered

    required_interfaces is a dictionary of required general interfaces
    with dictionary values of possible specific interfaces.
    Example:
    required_interfaces = {'database': ['shared-db', 'pgsql-db']}

    The interface is said to be satisfied if anyone of the interfaces in the
    list has a complete context.

    Return dictionary of incomplete or missing required contexts with relation
    status of interfaces and any missing data points. Example:
        {'message':
             {'amqp': {'missing_data': ['rabbitmq_password'], 'related': True},
              'zeromq-configuration': {'related': False}},
         'identity':
             {'identity-service': {'related': False}},
         'database':
             {'pgsql-db': {'related': False},
              'shared-db': {'related': True}}}
    """
    complete_ctxts = configs.complete_contexts()
    incomplete_relations = []
    for svc_type in required_interfaces.keys():
        # Avoid duplicates
        found_ctxt = False
        for interface in required_interfaces[svc_type]:
            if interface in complete_ctxts:
                found_ctxt = True
        if not found_ctxt:
            incomplete_relations.append(svc_type)
    incomplete_context_data = {}
    for i in incomplete_relations:
        incomplete_context_data[i] = configs.get_incomplete_context_data(required_interfaces[i])
    return incomplete_context_data


def do_action_openstack_upgrade(package, upgrade_callback, configs):
    """Perform action-managed OpenStack upgrade.

    Upgrades packages to the configured openstack-origin version and sets
    the corresponding action status as a result.

    If the charm was installed from source we cannot upgrade it.
    For backwards compatibility a config flag (action-managed-upgrade) must
    be set for this code to run, otherwise a full service level upgrade will
    fire on config-changed.

    @param package: package name for determining if upgrade available
    @param upgrade_callback: function callback to charm's upgrade function
    @param configs: templating object derived from OSConfigRenderer class

    @return: True if upgrade successful; False if upgrade failed or skipped
    """
    ret = False

    if git_install_requested():
        action_set({'outcome': 'installed from source, skipped upgrade.'})
    else:
        if openstack_upgrade_available(package):
            if config('action-managed-upgrade'):
                juju_log('Upgrading OpenStack release')

                try:
                    upgrade_callback(configs=configs)
                    action_set({'outcome': 'success, upgrade completed.'})
                    ret = True
                except:
                    action_set({'outcome': 'upgrade failed, see traceback.'})
                    action_set({'traceback': traceback.format_exc()})
                    action_fail('do_openstack_upgrade resulted in an '
                                'unexpected error')
            else:
                action_set({'outcome': 'action-managed-upgrade config is '
                                       'False, skipped upgrade.'})
        else:
            action_set({'outcome': 'no upgrade available.'})

    return ret


def remote_restart(rel_name, remote_service=None):
    trigger = {
        'restart-trigger': str(uuid.uuid4()),
    }
    if remote_service:
        trigger['remote-service'] = remote_service
    for rid in relation_ids(rel_name):
        # This subordinate can be related to two seperate services using
        # different subordinate relations so only issue the restart if
        # the principle is conencted down the relation we think it is
        if related_units(relid=rid):
            relation_set(relation_id=rid,
                         relation_settings=trigger,
                         )
