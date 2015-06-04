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
# Authors:
#  James Page <james.page@ubuntu.com>
#  Adam Gandelman <adamg@ubuntu.com>
#

"""
Helpers for clustering and determining "cluster leadership" and other
clustering-related helpers.
"""

import subprocess
import os

from socket import gethostname as get_unit_hostname

import six

from charmhelpers.core.hookenv import (
    log,
    relation_ids,
    related_units as relation_list,
    relation_get,
    config as config_get,
    INFO,
    ERROR,
    WARNING,
    unit_get,
)
from charmhelpers.core.decorators import (
    retry_on_exception,
)
from charmhelpers.core.strutils import (
    bool_from_string,
)

DC_RESOURCE_NAME = 'DC'


class HAIncompleteConfig(Exception):
    pass


class CRMResourceNotFound(Exception):
    pass


def is_elected_leader(resource):
    """
    Returns True if the charm executing this is the elected cluster leader.

    It relies on two mechanisms to determine leadership:
        1. If the charm is part of a corosync cluster, call corosync to
        determine leadership.
        2. If the charm is not part of a corosync cluster, the leader is
        determined as being "the alive unit with the lowest unit numer". In
        other words, the oldest surviving unit.
    """
    if is_clustered():
        if not is_crm_leader(resource):
            log('Deferring action to CRM leader.', level=INFO)
            return False
    else:
        peers = peer_units()
        if peers and not oldest_peer(peers):
            log('Deferring action to oldest service unit.', level=INFO)
            return False
    return True


def is_clustered():
    for r_id in (relation_ids('ha') or []):
        for unit in (relation_list(r_id) or []):
            clustered = relation_get('clustered',
                                     rid=r_id,
                                     unit=unit)
            if clustered:
                return True
    return False


def is_crm_dc():
    """
    Determine leadership by querying the pacemaker Designated Controller
    """
    cmd = ['crm', 'status']
    try:
        status = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        if not isinstance(status, six.text_type):
            status = six.text_type(status, "utf-8")
    except subprocess.CalledProcessError:
        return False
    current_dc = ''
    for line in status.split('\n'):
        if line.startswith('Current DC'):
            # Current DC: juju-lytrusty-machine-2 (168108163) - partition with quorum
            current_dc = line.split(':')[1].split()[0]
    if current_dc == get_unit_hostname():
        return True
    return False


@retry_on_exception(5, base_delay=2, exc_type=CRMResourceNotFound)
def is_crm_leader(resource, retry=False):
    """
    Returns True if the charm calling this is the elected corosync leader,
    as returned by calling the external "crm" command.

    We allow this operation to be retried to avoid the possibility of getting a
    false negative. See LP #1396246 for more info.
    """
    if resource == DC_RESOURCE_NAME:
        return is_crm_dc()
    cmd = ['crm', 'resource', 'show', resource]
    try:
        status = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        if not isinstance(status, six.text_type):
            status = six.text_type(status, "utf-8")
    except subprocess.CalledProcessError:
        status = None

    if status and get_unit_hostname() in status:
        return True

    if status and "resource %s is NOT running" % (resource) in status:
        raise CRMResourceNotFound("CRM resource %s not found" % (resource))

    return False


def is_leader(resource):
    log("is_leader is deprecated. Please consider using is_crm_leader "
        "instead.", level=WARNING)
    return is_crm_leader(resource)


def peer_units(peer_relation="cluster"):
    peers = []
    for r_id in (relation_ids(peer_relation) or []):
        for unit in (relation_list(r_id) or []):
            peers.append(unit)
    return peers


def peer_ips(peer_relation='cluster', addr_key='private-address'):
    '''Return a dict of peers and their private-address'''
    peers = {}
    for r_id in relation_ids(peer_relation):
        for unit in relation_list(r_id):
            peers[unit] = relation_get(addr_key, rid=r_id, unit=unit)
    return peers


def oldest_peer(peers):
    """Determines who the oldest peer is by comparing unit numbers."""
    local_unit_no = int(os.getenv('JUJU_UNIT_NAME').split('/')[1])
    for peer in peers:
        remote_unit_no = int(peer.split('/')[1])
        if remote_unit_no < local_unit_no:
            return False
    return True


def eligible_leader(resource):
    log("eligible_leader is deprecated. Please consider using "
        "is_elected_leader instead.", level=WARNING)
    return is_elected_leader(resource)


def https():
    '''
    Determines whether enough data has been provided in configuration
    or relation data to configure HTTPS
    .
    returns: boolean
    '''
    use_https = config_get('use-https')
    if use_https and bool_from_string(use_https):
        return True
    if config_get('ssl_cert') and config_get('ssl_key'):
        return True
    for r_id in relation_ids('identity-service'):
        for unit in relation_list(r_id):
            # TODO - needs fixing for new helper as ssl_cert/key suffixes with CN
            rel_state = [
                relation_get('https_keystone', rid=r_id, unit=unit),
                relation_get('ca_cert', rid=r_id, unit=unit),
            ]
            # NOTE: works around (LP: #1203241)
            if (None not in rel_state) and ('' not in rel_state):
                return True
    return False


def determine_api_port(public_port, singlenode_mode=False):
    '''
    Determine correct API server listening port based on
    existence of HTTPS reverse proxy and/or haproxy.

    public_port: int: standard public port for given service

    singlenode_mode: boolean: Shuffle ports when only a single unit is present

    returns: int: the correct listening port for the API service
    '''
    i = 0
    if singlenode_mode:
        i += 1
    elif len(peer_units()) > 0 or is_clustered():
        i += 1
    if https():
        i += 1
    return public_port - (i * 10)


def determine_apache_port(public_port, singlenode_mode=False):
    '''
    Description: Determine correct apache listening port based on public IP +
    state of the cluster.

    public_port: int: standard public port for given service

    singlenode_mode: boolean: Shuffle ports when only a single unit is present

    returns: int: the correct listening port for the HAProxy service
    '''
    i = 0
    if singlenode_mode:
        i += 1
    elif len(peer_units()) > 0 or is_clustered():
        i += 1
    return public_port - (i * 10)


def get_hacluster_config(exclude_keys=None):
    '''
    Obtains all relevant configuration from charm configuration required
    for initiating a relation to hacluster:

        ha-bindiface, ha-mcastport, vip

    param: exclude_keys: list of setting key(s) to be excluded.
    returns: dict: A dict containing settings keyed by setting name.
    raises: HAIncompleteConfig if settings are missing.
    '''
    settings = ['ha-bindiface', 'ha-mcastport', 'vip']
    conf = {}
    for setting in settings:
        if exclude_keys and setting in exclude_keys:
            continue

        conf[setting] = config_get(setting)
    missing = []
    [missing.append(s) for s, v in six.iteritems(conf) if v is None]
    if missing:
        log('Insufficient config data to configure hacluster.', level=ERROR)
        raise HAIncompleteConfig
    return conf


def canonical_url(configs, vip_setting='vip'):
    '''
    Returns the correct HTTP URL to this host given the state of HTTPS
    configuration and hacluster.

    :configs    : OSTemplateRenderer: A config tempating object to inspect for
                                      a complete https context.

    :vip_setting:                str: Setting in charm config that specifies
                                      VIP address.
    '''
    scheme = 'http'
    if 'https' in configs.complete_contexts():
        scheme = 'https'
    if is_clustered():
        addr = config_get(vip_setting)
    else:
        addr = unit_get('private-address')
    return '%s://%s' % (scheme, addr)
