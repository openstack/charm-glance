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


class HAIncompleteConfig(Exception):
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


def is_crm_leader(resource):
    """
    Returns True if the charm calling this is the elected corosync leader,
    as returned by calling the external "crm" command.
    """
    cmd = [
        "crm", "resource",
        "show", resource
    ]
    try:
        status = subprocess.check_output(cmd)
    except subprocess.CalledProcessError:
        return False
    else:
        if get_unit_hostname() in status:
            return True
        else:
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
    if config_get('use-https') == "yes":
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


def determine_api_port(public_port):
    '''
    Determine correct API server listening port based on
    existence of HTTPS reverse proxy and/or haproxy.

    public_port: int: standard public port for given service

    returns: int: the correct listening port for the API service
    '''
    i = 0
    if len(peer_units()) > 0 or is_clustered():
        i += 1
    if https():
        i += 1
    return public_port - (i * 10)


def determine_apache_port(public_port):
    '''
    Description: Determine correct apache listening port based on public IP +
    state of the cluster.

    public_port: int: standard public port for given service

    returns: int: the correct listening port for the HAProxy service
    '''
    i = 0
    if len(peer_units()) > 0 or is_clustered():
        i += 1
    return public_port - (i * 10)


def get_hacluster_config():
    '''
    Obtains all relevant configuration from charm configuration required
    for initiating a relation to hacluster:

        ha-bindiface, ha-mcastport, vip

    returns: dict: A dict containing settings keyed by setting name.
    raises: HAIncompleteConfig if settings are missing.
    '''
    settings = ['ha-bindiface', 'ha-mcastport', 'vip']
    conf = {}
    for setting in settings:
        conf[setting] = config_get(setting)
    missing = []
    [missing.append(s) for s, v in conf.iteritems() if v is None]
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
