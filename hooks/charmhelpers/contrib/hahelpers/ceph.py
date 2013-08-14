#
# Copyright 2012 Canonical Ltd.
#
# This file is sourced from lp:openstack-charm-helpers
#
# Authors:
#  James Page <james.page@ubuntu.com>
#  Adam Gandelman <adamg@ubuntu.com>
#

import commands
import os
import shutil
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
    ERROR
)

from charmhelpers.core.host import (
    apt_install,
    mount,
    mounts,
    service_start,
    service_stop,
    umount,
)

KEYRING = '/etc/ceph/ceph.client.%s.keyring'
KEYFILE = '/etc/ceph/ceph.client.%s.key'

CEPH_CONF = """[global]
 auth supported = %(auth)s
 keyring = %(keyring)s
 mon host = %(mon_hosts)s
"""


def running(service):
    # this local util can be dropped as soon the following branch lands
    # in lp:charm-helpers
    # https://code.launchpad.net/~gandelman-a/charm-helpers/service_running/
    try:
        output = check_output(['service', service, 'status'])
    except CalledProcessError:
        return False
    else:
        if ("start/running" in output or "is running" in output):
            return True
        else:
            return False


def install():
    ceph_dir = "/etc/ceph"
    if not os.path.isdir(ceph_dir):
        os.mkdir(ceph_dir)
    apt_install('ceph-common', fatal=True)


def rbd_exists(service, pool, rbd_img):
    (rc, out) = commands.getstatusoutput('rbd list --id %s --pool %s' %
                                         (service, pool))
    return rbd_img in out


def create_rbd_image(service, pool, image, sizemb):
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
    (rc, out) = commands.getstatusoutput("rados --id %s lspools" % service)
    return name in out


def create_pool(service, name):
    cmd = [
        'rados',
        '--id',
        service,
        'mkpool',
        name
    ]
    check_call(cmd)


def keyfile_path(service):
    return KEYFILE % service


def keyring_path(service):
    return KEYRING % service


def create_keyring(service, key):
    keyring = keyring_path(service)
    if os.path.exists(keyring):
        log('ceph: Keyring exists at %s.' % keyring, level=INFO)
    cmd = [
        'ceph-authtool',
        keyring,
        '--create-keyring',
        '--name=client.%s' % service,
        '--add-key=%s' % key
    ]
    check_call(cmd)
    log('ceph: Created new ring at %s.' % keyring, level=INFO)


def create_key_file(service, key):
    # create a file containing the key
    keyfile = keyfile_path(service)
    if os.path.exists(keyfile):
        log('ceph: Keyfile exists at %s.' % keyfile, level=INFO)
    fd = open(keyfile, 'w')
    fd.write(key)
    fd.close()
    log('ceph: Created new keyfile at %s.' % keyfile, level=INFO)


def get_ceph_nodes():
    hosts = []
    for r_id in relation_ids('ceph'):
        for unit in related_units(r_id):
            hosts.append(relation_get('private-address', unit=unit, rid=r_id))
    return hosts


def configure(service, key, auth):
    create_keyring(service, key)
    create_key_file(service, key)
    hosts = get_ceph_nodes()
    mon_hosts = ",".join(map(str, hosts))
    keyring = keyring_path(service)
    with open('/etc/ceph/ceph.conf', 'w') as ceph_conf:
        ceph_conf.write(CEPH_CONF % locals())
    modprobe_kernel_module('rbd')


def image_mapped(image_name):
    (rc, out) = commands.getstatusoutput('rbd showmapped')
    return image_name in out


def map_block_storage(service, pool, image):
    cmd = [
        'rbd',
        'map',
        '%s/%s' % (pool, image),
        '--user',
        service,
        '--secret',
        keyfile_path(service),
    ]
    check_call(cmd)


def filesystem_mounted(fs):
    return fs in [f for m, f in mounts()]


def make_filesystem(blk_device, fstype='ext4', timeout=10):
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


def place_data_on_ceph(service, blk_device, data_src_dst, fstype='ext4'):
    # mount block device into /mnt
    mount(blk_device, '/mnt')

    # copy data to /mnt
    try:
        copy_files(data_src_dst, '/mnt')
    except:
        pass

    # umount block device
    umount('/mnt')

    _dir = os.stat(data_src_dst)
    uid = _dir.st_uid
    gid = _dir.st_gid

    # re-mount where the data should originally be
    mount(blk_device, data_src_dst, persist=True)

    # ensure original ownership of new mount.
    cmd = ['chown', '-R', '%s:%s' % (uid, gid), data_src_dst]
    check_call(cmd)


# TODO: re-use
def modprobe_kernel_module(module):
    log('ceph: Loading kernel module', level=INFO)
    cmd = ['modprobe', module]
    check_call(cmd)
    cmd = 'echo %s >> /etc/modules' % module
    check_call(cmd, shell=True)


def copy_files(src, dst, symlinks=False, ignore=None):
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
    To be called from the current cluster leader.
    Ensures given pool and RBD image exists, is mapped to a block device,
    and the device is formatted and mounted at the given mount_point.

    If formatting a device for the first time, data existing at mount_point
    will be migrated to the RBD device before being remounted.

    All services listed in system_services will be stopped prior to data
    migration and restarted when complete.
    """
    # Ensure pool, RBD image, RBD mappings are in place.
    if not pool_exists(service, pool):
        log('ceph: Creating new pool %s.' % pool, level=INFO)
        create_pool(service, pool)

    if not rbd_exists(service, pool, rbd_img):
        log('ceph: Creating RBD image (%s).' % rbd_img, level=INFO)
        create_rbd_image(service, pool, rbd_img, sizemb)

    if not image_mapped(rbd_img):
        log('ceph: Mapping RBD Image as a Block Device.', level=INFO)
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
            if running(svc):
                log('Stopping services %s prior to migrating data.' % svc,
                    level=INFO)
                service_stop(svc)

        place_data_on_ceph(service, blk_device, mount_point, fstype)

        for svc in system_services:
            service_start(svc)
