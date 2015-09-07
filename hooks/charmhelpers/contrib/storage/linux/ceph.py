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
import uuid

from subprocess import (
    check_call,
    check_output,
    CalledProcessError,
)
from charmhelpers.core.hookenv import (
    local_unit,
    relation_get,
    relation_ids,
    relation_set,
    related_units,
    log,
    DEBUG,
    INFO,
    WARNING,
    ERROR,
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
log to syslog = {use_syslog}
err to syslog = {use_syslog}
clog to syslog = {use_syslog}
"""


def install():
    """Basic Ceph client installation."""
    ceph_dir = "/etc/ceph"
    if not os.path.exists(ceph_dir):
        os.mkdir(ceph_dir)

    apt_install('ceph-common', fatal=True)


def rbd_exists(service, pool, rbd_img):
    """Check to see if a RADOS block device exists."""
    try:
        out = check_output(['rbd', 'list', '--id',
                            service, '--pool', pool]).decode('UTF-8')
    except CalledProcessError:
        return False

    return rbd_img in out


def create_rbd_image(service, pool, image, sizemb):
    """Create a new RADOS block device."""
    cmd = ['rbd', 'create', image, '--size', str(sizemb), '--id', service,
           '--pool', pool]
    check_call(cmd)


def pool_exists(service, name):
    """Check to see if a RADOS pool already exists."""
    try:
        out = check_output(['rados', '--id', service,
                            'lspools']).decode('UTF-8')
    except CalledProcessError:
        return False

    return name in out


def get_osds(service):
    """Return a list of all Ceph Object Storage Daemons currently in the
    cluster.
    """
    version = ceph_version()
    if version and version >= '0.56':
        return json.loads(check_output(['ceph', '--id', service,
                                        'osd', 'ls',
                                        '--format=json']).decode('UTF-8'))

    return None


def create_pool(service, name, replicas=3):
    """Create a new RADOS pool."""
    if pool_exists(service, name):
        log("Ceph pool {} already exists, skipping creation".format(name),
            level=WARNING)
        return

    # Calculate the number of placement groups based
    # on upstream recommended best practices.
    osds = get_osds(service)
    if osds:
        pgnum = (len(osds) * 100 // replicas)
    else:
        # NOTE(james-page): Default to 200 for older ceph versions
        # which don't support OSD query from cli
        pgnum = 200

    cmd = ['ceph', '--id', service, 'osd', 'pool', 'create', name, str(pgnum)]
    check_call(cmd)

    cmd = ['ceph', '--id', service, 'osd', 'pool', 'set', name, 'size',
           str(replicas)]
    check_call(cmd)


def delete_pool(service, name):
    """Delete a RADOS pool from ceph."""
    cmd = ['ceph', '--id', service, 'osd', 'pool', 'delete', name,
           '--yes-i-really-really-mean-it']
    check_call(cmd)


def _keyfile_path(service):
    return KEYFILE.format(service)


def _keyring_path(service):
    return KEYRING.format(service)


def create_keyring(service, key):
    """Create a new Ceph keyring containing key."""
    keyring = _keyring_path(service)
    if os.path.exists(keyring):
        log('Ceph keyring exists at %s.' % keyring, level=WARNING)
        return

    cmd = ['ceph-authtool', keyring, '--create-keyring',
           '--name=client.{}'.format(service), '--add-key={}'.format(key)]
    check_call(cmd)
    log('Created new ceph keyring at %s.' % keyring, level=DEBUG)


def delete_keyring(service):
    """Delete an existing Ceph keyring."""
    keyring = _keyring_path(service)
    if not os.path.exists(keyring):
        log('Keyring does not exist at %s' % keyring, level=WARNING)
        return

    os.remove(keyring)
    log('Deleted ring at %s.' % keyring, level=INFO)


def create_key_file(service, key):
    """Create a file containing key."""
    keyfile = _keyfile_path(service)
    if os.path.exists(keyfile):
        log('Keyfile exists at %s.' % keyfile, level=WARNING)
        return

    with open(keyfile, 'w') as fd:
        fd.write(key)

    log('Created new keyfile at %s.' % keyfile, level=INFO)


def get_ceph_nodes():
    """Query named relation 'ceph' to determine current nodes."""
    hosts = []
    for r_id in relation_ids('ceph'):
        for unit in related_units(r_id):
            hosts.append(relation_get('private-address', unit=unit, rid=r_id))

    return hosts


def configure(service, key, auth, use_syslog):
    """Perform basic configuration of Ceph."""
    create_keyring(service, key)
    create_key_file(service, key)
    hosts = get_ceph_nodes()
    with open('/etc/ceph/ceph.conf', 'w') as ceph_conf:
        ceph_conf.write(CEPH_CONF.format(auth=auth,
                                         keyring=_keyring_path(service),
                                         mon_hosts=",".join(map(str, hosts)),
                                         use_syslog=use_syslog))
    modprobe('rbd')


def image_mapped(name):
    """Determine whether a RADOS block device is mapped locally."""
    try:
        out = check_output(['rbd', 'showmapped']).decode('UTF-8')
    except CalledProcessError:
        return False

    return name in out


def map_block_storage(service, pool, image):
    """Map a RADOS block device for local use."""
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
    """Determine whether a filesytems is already mounted."""
    return fs in [f for f, m in mounts()]


def make_filesystem(blk_device, fstype='ext4', timeout=10):
    """Make a new filesystem on the specified block device."""
    count = 0
    e_noent = os.errno.ENOENT
    while not os.path.exists(blk_device):
        if count >= timeout:
            log('Gave up waiting on block device %s' % blk_device,
                level=ERROR)
            raise IOError(e_noent, os.strerror(e_noent), blk_device)

        log('Waiting for block device %s to appear' % blk_device,
            level=DEBUG)
        count += 1
        time.sleep(1)
    else:
        log('Formatting block device %s as filesystem %s.' %
            (blk_device, fstype), level=INFO)
        check_call(['mkfs', '-t', fstype, blk_device])


def place_data_on_block_device(blk_device, data_src_dst):
    """Migrate data in data_src_dst to blk_device and then remount."""
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
    """Load a kernel module and configure for auto-load on reboot."""
    log('Loading kernel module', level=INFO)
    cmd = ['modprobe', module]
    check_call(cmd)
    with open('/etc/modules', 'r+') as modules:
        if module not in modules.read():
            modules.write(module)


def copy_files(src, dst, symlinks=False, ignore=None):
    """Copy files from src to dst."""
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, symlinks, ignore)
        else:
            shutil.copy2(s, d)


def ensure_ceph_storage(service, pool, rbd_img, sizemb, mount_point,
                        blk_device, fstype, system_services=[],
                        replicas=3):
    """NOTE: This function must only be called from a single service unit for
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
        log('Creating new pool {}.'.format(pool), level=INFO)
        create_pool(service, pool, replicas=replicas)

    if not rbd_exists(service, pool, rbd_img):
        log('Creating RBD image ({}).'.format(rbd_img), level=INFO)
        create_rbd_image(service, pool, rbd_img, sizemb)

    if not image_mapped(rbd_img):
        log('Mapping RBD Image {} as a Block Device.'.format(rbd_img),
            level=INFO)
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
                log('Stopping services {} prior to migrating data.'
                    .format(svc), level=DEBUG)
                service_stop(svc)

        place_data_on_block_device(blk_device, mount_point)

        for svc in system_services:
            log('Starting service {} after migrating data.'
                .format(svc), level=DEBUG)
            service_start(svc)


def ensure_ceph_keyring(service, user=None, group=None):
    """Ensures a ceph keyring is created for a named service and optionally
    ensures user and group ownership.

    Returns False if no ceph key is available in relation state.
    """
    key = None
    for rid in relation_ids('ceph'):
        for unit in related_units(rid):
            key = relation_get('key', rid=rid, unit=unit)
            if key:
                break

    if not key:
        return False

    create_keyring(service=service, key=key)
    keyring = _keyring_path(service)
    if user and group:
        check_call(['chown', '%s.%s' % (user, group), keyring])

    return True


def ceph_version():
    """Retrieve the local version of ceph."""
    if os.path.exists('/usr/bin/ceph'):
        cmd = ['ceph', '-v']
        output = check_output(cmd).decode('US-ASCII')
        output = output.split()
        if len(output) > 3:
            return output[2]
        else:
            return None
    else:
        return None


class CephBrokerRq(object):
    """Ceph broker request.

    Multiple operations can be added to a request and sent to the Ceph broker
    to be executed.

    Request is json-encoded for sending over the wire.

    The API is versioned and defaults to version 1.
    """
    def __init__(self, api_version=1, request_id=None):
        self.api_version = api_version
        if request_id:
            self.request_id = request_id
        else:
            self.request_id = str(uuid.uuid1())
        self.ops = []

    def add_op_create_pool(self, name, replica_count=3):
        self.ops.append({'op': 'create-pool', 'name': name,
                         'replicas': replica_count})

    def set_ops(self, ops):
        """Set request ops to provided value.

        Useful for injecting ops that come from a previous request
        to allow comparisons to ensure validity.
        """
        self.ops = ops

    @property
    def request(self):
        return json.dumps({'api-version': self.api_version, 'ops': self.ops,
                           'request-id': self.request_id})

    def _ops_equal(self, other):
        if len(self.ops) == len(other.ops):
            for req_no in range(0, len(self.ops)):
                for key in ['replicas', 'name', 'op']:
                    if self.ops[req_no][key] != other.ops[req_no][key]:
                        return False
        else:
            return False
        return True

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        if self.api_version == other.api_version and \
                self._ops_equal(other):
            return True
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)


class CephBrokerRsp(object):
    """Ceph broker response.

    Response is json-decoded and contents provided as methods/properties.

    The API is versioned and defaults to version 1.
    """

    def __init__(self, encoded_rsp):
        self.api_version = None
        self.rsp = json.loads(encoded_rsp)

    @property
    def request_id(self):
        return self.rsp.get('request-id')

    @property
    def exit_code(self):
        return self.rsp.get('exit-code')

    @property
    def exit_msg(self):
        return self.rsp.get('stderr')


# Ceph Broker Conversation:
# If a charm needs an action to be taken by ceph it can create a CephBrokerRq
# and send that request to ceph via the ceph relation. The CephBrokerRq has a
# unique id so that the client can identity which CephBrokerRsp is associated
# with the request. Ceph will also respond to each client unit individually
# creating a response key per client unit eg glance/0 will get a CephBrokerRsp
# via key broker-rsp-glance-0
#
# To use this the charm can just do something like:
#
# from charmhelpers.contrib.storage.linux.ceph import (
#     send_request_if_needed,
#     is_request_complete,
#     CephBrokerRq,
# )
#
# @hooks.hook('ceph-relation-changed')
# def ceph_changed():
#     rq = CephBrokerRq()
#     rq.add_op_create_pool(name='poolname', replica_count=3)
#
#     if is_request_complete(rq):
#         <Request complete actions>
#     else:
#         send_request_if_needed(get_ceph_request())
#
# CephBrokerRq and CephBrokerRsp are serialized into JSON. Below is an example
# of glance having sent a request to ceph which ceph has successfully processed
#  'ceph:8': {
#      'ceph/0': {
#          'auth': 'cephx',
#          'broker-rsp-glance-0': '{"request-id": "0bc7dc54", "exit-code": 0}',
#          'broker_rsp': '{"request-id": "0da543b8", "exit-code": 0}',
#          'ceph-public-address': '10.5.44.103',
#          'key': 'AQCLDttVuHXINhAAvI144CB09dYchhHyTUY9BQ==',
#          'private-address': '10.5.44.103',
#      },
#      'glance/0': {
#          'broker_req': ('{"api-version": 1, "request-id": "0bc7dc54", '
#                         '"ops": [{"replicas": 3, "name": "glance", '
#                         '"op": "create-pool"}]}'),
#          'private-address': '10.5.44.109',
#      },
#  }

def get_previous_request(rid):
    """Return the last ceph broker request sent on a given relation

    @param rid: Relation id to query for request
    """
    request = None
    broker_req = relation_get(attribute='broker_req', rid=rid,
                              unit=local_unit())
    if broker_req:
        request_data = json.loads(broker_req)
        request = CephBrokerRq(api_version=request_data['api-version'],
                               request_id=request_data['request-id'])
        request.set_ops(request_data['ops'])
    return request


def get_request_states(request):
    """Return a dict of requests per relation id with their corresponding
       completion state.

    This allows a charm, which has a request for ceph, to see whether there is
    an equivalent request already being processed and if so what state that
    request is in.

    @param request: A CephBrokerRq object
    """
    complete = []
    requests = {}
    for rid in relation_ids('ceph'):
        complete = False
        previous_request = get_previous_request(rid)
        if request == previous_request:
            sent = True
            complete = is_broker_request_complete(previous_request, rid)
        else:
            sent = False
            complete = False
        requests[rid] = {
            'sent': sent,
            'complete': complete,
        }
    return requests


def is_request_sent(request):
    """Check to see if a functionally equivalent request has already been sent

    Returns True if a similair request has been sent

    @param request: A CephBrokerRq object
    """
    states = get_request_states(request)
    for rid in states.keys():
        if not states[rid]['sent']:
            return False
    return True


def is_request_complete(request):
    """Check to see if a functionally equivalent request has already been
    completed

    Returns True if a similair request has been completed

    @param request: A CephBrokerRq object
    """
    states = get_request_states(request)
    for rid in states.keys():
        if not states[rid]['complete']:
            return False
    return True


def is_broker_request_complete(request, rid):
    """Check if a given request has been completed on the given relation

    @param request: A CephBrokerRq object
    @param rid: Relation ID
    """
    broker_key = get_broker_rsp_key()
    for unit in related_units(rid):
        rdata = relation_get(rid=rid, unit=unit)
        if rdata.get(broker_key):
            rsp = CephBrokerRsp(rdata.get(broker_key))
            if rsp.request_id == request.request_id:
                if not rsp.exit_code:
                    return True
        else:
            # The remote unit sent no reply targeted at this unit so either the
            # remote ceph cluster does not support unit targeted replies or it
            # has not processed our request yet.
            if rdata.get('broker_rsp'):
                request_data = json.loads(rdata['broker_rsp'])
                if request_data.get('request-id'):
                    log('Ignoring legacy broker_rsp without unit key as remote '
                        'service supports unit specific replies', level=DEBUG)
                else:
                    log('Using legacy broker_rsp as remote service does not '
                        'supports unit specific replies', level=DEBUG)
                    rsp = CephBrokerRsp(rdata['broker_rsp'])
                    if not rsp.exit_code:
                        return True
    return False


def get_broker_rsp_key():
    """Return broker response key for this unit

    This is the key that ceph is going to use to pass request status
    information back to this unit
    """
    return 'broker-rsp-' + local_unit().replace('/', '-')


def send_request_if_needed(request):
    """Send broker request if an equivalent request has not already been sent

    @param request: A CephBrokerRq object
    """
    if is_request_sent(request):
        log('Request already sent but not complete, not sending new request',
            level=DEBUG)
    else:
        for rid in relation_ids('ceph'):
            log('Sending request {}'.format(request.request_id), level=DEBUG)
            relation_set(relation_id=rid, broker_req=request.request)
