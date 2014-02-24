#
# Copyright 2012 Canonical Ltd.
#
# Authors:
#  James Page <james.page@ubuntu.com>
#  Adam Gandelman <adamg@ubuntu.com>
#

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
    unit_get,
)


class HAIncompleteConfig(Exception):
    pass


def is_clustered():
    for r_id in (relation_ids('ha') or []):
        for unit in (relation_list(r_id) or []):
            clustered = relation_get('clustered',
                                     rid=r_id,
                                     unit=unit)
            if clustered:
                return True
    return False


def is_leader(resource):
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


def peer_units():
    peers = []
    for r_id in (relation_ids('cluster') or []):
        for unit in (relation_list(r_id) or []):
            peers.append(unit)
    return peers


def oldest_peer(peers):
    local_unit_no = int(os.getenv('JUJU_UNIT_NAME').split('/')[1])
    for peer in peers:
        remote_unit_no = int(peer.split('/')[1])
        if remote_unit_no < local_unit_no:
            return False
    return True


def eligible_leader(resource):
    if is_clustered():
        if not is_leader(resource):
            log('Deferring action to CRM leader.', level=INFO)
            return False
    else:
        peers = peer_units()
        if peers and not oldest_peer(peers):
            log('Deferring action to oldest service unit.', level=INFO)
            return False
    return True


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
            rel_state = [
                relation_get('https_keystone', rid=r_id, unit=unit),
                relation_get('ssl_cert', rid=r_id, unit=unit),
                relation_get('ssl_key', rid=r_id, unit=unit),
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

        ha-bindiface, ha-mcastport, vip, vip_iface, vip_cidr

    returns: dict: A dict containing settings keyed by setting name.
    raises: HAIncompleteConfig if settings are missing.
    '''
    settings = ['ha-bindiface', 'ha-mcastport', 'vip', 'vip_iface', 'vip_cidr']
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
