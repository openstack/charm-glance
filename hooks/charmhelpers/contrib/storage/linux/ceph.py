#
# Copyright 2012 Canonical Ltd.
#
# This file is sourced from lp:openstack-charm-helpers
#
# Authors:
#  James Page <james.page@ubuntu.com>
#  Adam Gandelman <adamg@ubuntu.com>
#

import os
import shutil
import json
import time

from subprocess import (
    check_call,
    check_output,
    CalledProcessError
)

from charmhelpers.core.hookenv import (
    relation_get,
    relation_ids,
    related_units,
    log,
    INFO,
    WARNING,
    ERROR
)

from charmhelpers.core.host import (
    mount,
    mounts,
    service_start,
    service_stop,
    service_running,
    umount,
)

from charmhelpers.fetch import (
    apt_install,
)

KEYRING = '/etc/ceph/ceph.client.{}.keyring'
KEYFILE = '/etc/ceph/ceph.client.{}.key'

CEPH_CONF = """[global]
 auth supported = {auth}
 keyring = {keyring}
 mon host = {mon_hosts}
"""


def install():
    ''' Basic Ceph client installation '''
    ceph_dir = "/etc/ceph"
    if not os.path.exists(ceph_dir):
        os.mkdir(ceph_dir)
    apt_install('ceph-common', fatal=True)


def rbd_exists(service, pool, rbd_img):
    ''' Check to see if a RADOS block device exists '''
    try:
        out = check_output(['rbd', 'list', '--id', service,
                            '--pool', pool])
    except CalledProcessError:
        return False
    else:
        return rbd_img in out


def create_rbd_image(service, pool, image, sizemb):
    ''' Create a new RADOS block device '''
    cmd = [
        'rbd',
        'create',
        image,
        '--size',
        str(sizemb),
        '--id',
        service,
        '--pool',
        pool
    ]
    check_call(cmd)


def pool_exists(service, name):
    ''' Check to see if a RADOS pool already exists '''
    try:
        out = check_output(['rados', '--id', service, 'lspools'])
    except CalledProcessError:
        return False
    else:
        return name in out


def get_osds():
    '''
    Return a list of all Ceph Object Storage Daemons
    currently in the cluster
    '''
    return json.loads(check_output(['ceph', 'osd', 'ls', '--format=json']))


def create_pool(service, name, replicas=2):
    ''' Create a new RADOS pool '''
    if pool_exists(service, name):
        log("Ceph pool {} already exists, skipping creation".format(name),
            level=WARNING)
        return
    # Calculate the number of placement groups based
    # on upstream recommended best practices.
    pgnum = (len(get_osds()) * 100 / replicas)
    cmd = [
        'ceph', '--id', service,
        'osd', 'pool', 'create',
        name, pgnum
    ]
    check_call(cmd)
    cmd = [
        'ceph', '--id', service,
        'osd', 'set', name,
        'size', replicas
    ]
    check_call(cmd)


def delete_pool(service, name):
    ''' Delete a RADOS pool from ceph '''
    cmd = [
        'ceph', '--id', service,
        'osd', 'pool', 'delete',
        name, '--yes-i-really-really-mean-it'
    ]
    check_call(cmd)


def _keyfile_path(service):
    return KEYFILE.format(service)


def _keyring_path(service):
    return KEYRING.format(service)


def create_keyring(service, key):
    ''' Create a new Ceph keyring containing key'''
    keyring = _keyring_path(service)
    if os.path.exists(keyring):
        log('ceph: Keyring exists at %s.' % keyring, level=WARNING)
        return
    cmd = [
        'ceph-authtool',
        keyring,
        '--create-keyring',
        '--name=client.{}'.format(service),
        '--add-key={}'.format(key)
    ]
    check_call(cmd)
    log('ceph: Created new ring at %s.' % keyring, level=INFO)


def create_key_file(service, key):
    ''' Create a file containing key '''
    keyfile = _keyfile_path(service)
    if os.path.exists(keyfile):
        log('ceph: Keyfile exists at %s.' % keyfile, level=WARNING)
        return
    with open(keyfile, 'w') as fd:
        fd.write(key)
    log('ceph: Created new keyfile at %s.' % keyfile, level=INFO)


def get_ceph_nodes():
    ''' Query named relation 'ceph' to detemine current nodes '''
    hosts = []
    for r_id in relation_ids('ceph'):
        for unit in related_units(r_id):
            hosts.append(relation_get('private-address', unit=unit, rid=r_id))
    return hosts


def configure(service, key, auth):
    ''' Perform basic configuration of Ceph '''
    create_keyring(service, key)
    create_key_file(service, key)
    hosts = get_ceph_nodes()
    with open('/etc/ceph/ceph.conf', 'w') as ceph_conf:
        ceph_conf.write(CEPH_CONF.format(auth=auth,
                                         keyring=_keyring_path(service),
                                         mon_hosts=",".join(map(str, hosts))))
    modprobe('rbd')


def image_mapped(name):
    ''' Determine whether a RADOS block device is mapped locally '''
    try:
        out = check_output(['rbd', 'showmapped'])
    except CalledProcessError:
        return False
    else:
        return name in out


def map_block_storage(service, pool, image):
    ''' Map a RADOS block device for local use '''
    cmd = [
        'rbd',
        'map',
        '{}/{}'.format(pool, image),
        '--user',
        service,
        '--secret',
        _keyfile_path(service),
    ]
    check_call(cmd)


def filesystem_mounted(fs):
    ''' Determine whether a filesytems is already mounted '''
    return fs in [f for f, m in mounts()]


def make_filesystem(blk_device, fstype='ext4', timeout=10):
    ''' Make a new filesystem on the specified block device '''
    count = 0
    e_noent = os.errno.ENOENT
    while not os.path.exists(blk_device):
        if count >= timeout:
            log('ceph: gave up waiting on block device %s' % blk_device,
                level=ERROR)
            raise IOError(e_noent, os.strerror(e_noent), blk_device)
        log('ceph: waiting for block device %s to appear' % blk_device,
            level=INFO)
        count += 1
        time.sleep(1)
    else:
        log('ceph: Formatting block device %s as filesystem %s.' %
            (blk_device, fstype), level=INFO)
        check_call(['mkfs', '-t', fstype, blk_device])


def place_data_on_block_device(blk_device, data_src_dst):
    ''' Migrate data in data_src_dst to blk_device and then remount '''
    # mount block device into /mnt
    mount(blk_device, '/mnt')
    # copy data to /mnt
    copy_files(data_src_dst, '/mnt')
    # umount block device
    umount('/mnt')
    # Grab user/group ID's from original source
    _dir = os.stat(data_src_dst)
    uid = _dir.st_uid
    gid = _dir.st_gid
    # re-mount where the data should originally be
    # TODO: persist is currently a NO-OP in core.host
    mount(blk_device, data_src_dst, persist=True)
    # ensure original ownership of new mount.
    os.chown(data_src_dst, uid, gid)


# TODO: re-use
def modprobe(module):
    ''' Load a kernel module and configure for auto-load on reboot '''
    log('ceph: Loading kernel module', level=INFO)
    cmd = ['modprobe', module]
    check_call(cmd)
    with open('/etc/modules', 'r+') as modules:
        if module not in modules.read():
            modules.write(module)


def copy_files(src, dst, symlinks=False, ignore=None):
    ''' Copy files from src to dst '''
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, symlinks, ignore)
        else:
            shutil.copy2(s, d)


def ensure_ceph_storage(service, pool, rbd_img, sizemb, mount_point,
                        blk_device, fstype, system_services=[]):
    """
    NOTE: This function must only be called from a single service unit for
          the same rbd_img otherwise data loss will occur.

    Ensures given pool and RBD image exists, is mapped to a block device,
    and the device is formatted and mounted at the given mount_point.

    If formatting a device for the first time, data existing at mount_point
    will be migrated to the RBD device before being re-mounted.

    All services listed in system_services will be stopped prior to data
    migration and restarted when complete.
    """
    # Ensure pool, RBD image, RBD mappings are in place.
    if not pool_exists(service, pool):
        log('ceph: Creating new pool {}.'.format(pool))
        create_pool(service, pool)

    if not rbd_exists(service, pool, rbd_img):
        log('ceph: Creating RBD image ({}).'.format(rbd_img))
        create_rbd_image(service, pool, rbd_img, sizemb)

    if not image_mapped(rbd_img):
        log('ceph: Mapping RBD Image {} as a Block Device.'.format(rbd_img))
        map_block_storage(service, pool, rbd_img)

    # make file system
    # TODO: What happens if for whatever reason this is run again and
    # the data is already in the rbd device and/or is mounted??
    # When it is mounted already, it will fail to make the fs
    # XXX: This is really sketchy!  Need to at least add an fstab entry
    #      otherwise this hook will blow away existing data if its executed
    #      after a reboot.
    if not filesystem_mounted(mount_point):
        make_filesystem(blk_device, fstype)

        for svc in system_services:
            if service_running(svc):
                log('ceph: Stopping services {} prior to migrating data.'
                    .format(svc))
                service_stop(svc)

        place_data_on_block_device(blk_device, mount_point)

        for svc in system_services:
            log('ceph: Starting service {} after migrating data.'
                .format(svc))
            service_start(svc)
