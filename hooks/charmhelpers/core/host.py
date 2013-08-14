"""Tools for working with the host system"""
# Copyright 2012 Canonical Ltd.
#
# Authors:
#  Nick Moffitt <nick.moffitt@canonical.com>
#  Matthew Wedgwood <matthew.wedgwood@canonical.com>

import apt_pkg
import os
import pwd
import grp
import random
import string
import subprocess
import hashlib

from collections import OrderedDict

from hookenv import log


def service_start(service_name):
    service('start', service_name)


def service_stop(service_name):
    service('stop', service_name)


def service_restart(service_name):
    service('restart', service_name)


def service_reload(service_name, restart_on_failure=False):
    if not service('reload', service_name) and restart_on_failure:
        service('restart', service_name)


def service(action, service_name):
    cmd = ['service', service_name, action]
    return subprocess.call(cmd) == 0


def service_running(service):
    try:
        output = subprocess.check_output(['service', service, 'status'])
    except subprocess.CalledProcessError:
        return False
    else:
        if ("start/running" in output or "is running" in output):
            return True
        else:
            return False


def adduser(username, password=None, shell='/bin/bash', system_user=False):
    """Add a user"""
    try:
        user_info = pwd.getpwnam(username)
        log('user {0} already exists!'.format(username))
    except KeyError:
        log('creating user {0}'.format(username))
        cmd = ['useradd']
        if system_user or password is None:
            cmd.append('--system')
        else:
            cmd.extend([
                '--create-home',
                '--shell', shell,
                '--password', password,
            ])
        cmd.append(username)
        subprocess.check_call(cmd)
        user_info = pwd.getpwnam(username)
    return user_info


def add_user_to_group(username, group):
    """Add a user to a group"""
    cmd = [
        'gpasswd', '-a',
        username,
        group
    ]
    log("Adding user {} to group {}".format(username, group))
    subprocess.check_call(cmd)


def rsync(from_path, to_path, flags='-r', options=None):
    """Replicate the contents of a path"""
    options = options or ['--delete', '--executability']
    cmd = ['/usr/bin/rsync', flags]
    cmd.extend(options)
    cmd.append(from_path)
    cmd.append(to_path)
    log(" ".join(cmd))
    return subprocess.check_output(cmd).strip()


def symlink(source, destination):
    """Create a symbolic link"""
    log("Symlinking {} as {}".format(source, destination))
    cmd = [
        'ln',
        '-sf',
        source,
        destination,
    ]
    subprocess.check_call(cmd)


def mkdir(path, owner='root', group='root', perms=0555, force=False):
    """Create a directory"""
    log("Making dir {} {}:{} {:o}".format(path, owner, group,
                                          perms))
    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid
    realpath = os.path.abspath(path)
    if os.path.exists(realpath):
        if force and not os.path.isdir(realpath):
            log("Removing non-directory file {} prior to mkdir()".format(path))
            os.unlink(realpath)
    else:
        os.makedirs(realpath, perms)
    os.chown(realpath, uid, gid)


def write_file(path, content, owner='root', group='root', perms=0444):
    """Create or overwrite a file with the contents of a string"""
    log("Writing file {} {}:{} {:o}".format(path, owner, group, perms))
    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid
    with open(path, 'w') as target:
        os.fchown(target.fileno(), uid, gid)
        os.fchmod(target.fileno(), perms)
        target.write(content)


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
    options = options or []
    cmd = ['apt-get', '-y']
    cmd.extend(options)
    cmd.append('install')
    if isinstance(packages, basestring):
        cmd.append(packages)
    else:
        cmd.extend(packages)
    log("Installing {} with options: {}".format(packages,
                                                options))
    if fatal:
        subprocess.check_call(cmd)
    else:
        subprocess.call(cmd)


def apt_update(fatal=False):
    """Update local apt cache"""
    cmd = ['apt-get', 'update']
    if fatal:
        subprocess.check_call(cmd)
    else:
        subprocess.call(cmd)


def mount(device, mountpoint, options=None, persist=False):
    '''Mount a filesystem'''
    cmd_args = ['mount']
    if options is not None:
        cmd_args.extend(['-o', options])
    cmd_args.extend([device, mountpoint])
    try:
        subprocess.check_output(cmd_args)
    except subprocess.CalledProcessError, e:
        log('Error mounting {} at {}\n{}'.format(device, mountpoint, e.output))
        return False
    if persist:
        # TODO: update fstab
        pass
    return True


def umount(mountpoint, persist=False):
    '''Unmount a filesystem'''
    cmd_args = ['umount', mountpoint]
    try:
        subprocess.check_output(cmd_args)
    except subprocess.CalledProcessError, e:
        log('Error unmounting {}\n{}'.format(mountpoint, e.output))
        return False
    if persist:
        # TODO: update fstab
        pass
    return True


def mounts():
    '''List of all mounted volumes as [[mountpoint,device],[...]]'''
    with open('/proc/mounts') as f:
        # [['/mount/point','/dev/path'],[...]]
        system_mounts = [m[1::-1] for m in [l.strip().split()
                                            for l in f.readlines()]]
    return system_mounts


def file_hash(path):
    ''' Generate a md5 hash of the contents of 'path' or None if not found '''
    if os.path.exists(path):
        h = hashlib.md5()
        with open(path, 'r') as source:
            h.update(source.read())  # IGNORE:E1101 - it does have update
        return h.hexdigest()
    else:
        return None


def restart_on_change(restart_map):
    ''' Restart services based on configuration files changing

    This function is used a decorator, for example

        @restart_on_change({
            '/etc/ceph/ceph.conf': [ 'cinder-api', 'cinder-volume' ]
            })
        def ceph_client_changed():
            ...

    In this example, the cinder-api and cinder-volume services
    would be restarted if /etc/ceph/ceph.conf is changed by the
    ceph_client_changed function.
    '''
    def wrap(f):
        def wrapped_f(*args):
            checksums = {}
            for path in restart_map:
                checksums[path] = file_hash(path)
            f(*args)
            restarts = []
            for path in restart_map:
                if checksums[path] != file_hash(path):
                    restarts += restart_map[path]
            for service_name in list(OrderedDict.fromkeys(restarts)):
                service('restart', service_name)
        return wrapped_f
    return wrap


def lsb_release():
    '''Return /etc/lsb-release in a dict'''
    d = {}
    with open('/etc/lsb-release', 'r') as lsb:
        for l in lsb:
            k, v = l.split('=')
            d[k.strip()] = v.strip()
    return d


def pwgen(length=None):
    '''Generate a random pasword.'''
    if length is None:
        length = random.choice(range(35, 45))
    alphanumeric_chars = [
        l for l in (string.letters + string.digits)
        if l not in 'l0QD1vAEIOUaeiou']
    random_chars = [
        random.choice(alphanumeric_chars) for _ in range(length)]
    return(''.join(random_chars))
