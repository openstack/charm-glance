"""Tools for working with the host system"""
# Copyright 2012 Canonical Ltd.
#
# Authors:
#  Nick Moffitt <nick.moffitt@canonical.com>
#  Matthew Wedgwood <matthew.wedgwood@canonical.com>

import os
import pwd
import grp
import subprocess

from hookenv import log, execution_environment


def service_start(service_name):
    service('start', service_name)


def service_stop(service_name):
    service('stop', service_name)


def service(action, service_name):
    cmd = None
    if os.path.exists(os.path.join('/etc/init', '%s.conf' % service_name)):
        cmd = ['initctl', action, service_name]
    elif os.path.exists(os.path.join('/etc/init.d', service_name)):
        cmd = [os.path.join('/etc/init.d', service_name), action]
    if cmd:
        return_value = subprocess.call(cmd)
        return return_value == 0
    return False


def adduser(username, password, shell='/bin/bash'):
    """Add a user"""
    # TODO: generate a password if none is given
    try:
        user_info = pwd.getpwnam(username)
        log('user {0} already exists!'.format(username))
    except KeyError:
        log('creating user {0}'.format(username))
        cmd = [
            'useradd',
            '--create-home',
            '--shell', shell,
            '--password', password,
            username
        ]
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
    context = execution_environment()
    options = options or ['--delete', '--executability']
    cmd = ['/usr/bin/rsync', flags]
    cmd.extend(options)
    cmd.append(from_path.format(**context))
    cmd.append(to_path.format(**context))
    log(" ".join(cmd))
    return subprocess.check_output(cmd).strip()


def symlink(source, destination):
    """Create a symbolic link"""
    context = execution_environment()
    log("Symlinking {} as {}".format(source, destination))
    cmd = [
        'ln',
        '-sf',
        source.format(**context),
        destination.format(**context)
    ]
    subprocess.check_call(cmd)


def mkdir(path, owner='root', group='root', perms=0555, force=False):
    """Create a directory"""
    context = execution_environment()
    log("Making dir {} {}:{} {:o}".format(path, owner, group,
                                          perms))
    uid = pwd.getpwnam(owner.format(**context)).pw_uid
    gid = grp.getgrnam(group.format(**context)).gr_gid
    realpath = os.path.abspath(path)
    if os.path.exists(realpath):
        if force and not os.path.isdir(realpath):
            log("Removing non-directory file {} prior to mkdir()".format(path))
            os.unlink(realpath)
    else:
        os.makedirs(realpath, perms)
    os.chown(realpath, uid, gid)


def write_file(path, fmtstr, owner='root', group='root', perms=0444, **kwargs):
    """Create or overwrite a file with the contents of a string"""
    context = execution_environment()
    context.update(kwargs)
    log("Writing file {} {}:{} {:o}".format(path, owner, group,
        perms))
    uid = pwd.getpwnam(owner.format(**context)).pw_uid
    gid = grp.getgrnam(group.format(**context)).gr_gid
    with open(path.format(**context), 'w') as target:
        os.fchown(target.fileno(), uid, gid)
        os.fchmod(target.fileno(), perms)
        target.write(fmtstr.format(**context))


def render_template_file(source, destination, **kwargs):
    """Create or overwrite a file using a template"""
    log("Rendering template {} for {}".format(source,
        destination))
    context = execution_environment()
    with open(source.format(**context), 'r') as template:
        write_file(destination.format(**context), template.read(),
                   **kwargs)


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
