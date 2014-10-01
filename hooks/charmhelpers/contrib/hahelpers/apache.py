#
# Copyright 2012 Canonical Ltd.
#
# This file is sourced from lp:openstack-charm-helpers
#
# Authors:
#  James Page <james.page@ubuntu.com>
#  Adam Gandelman <adamg@ubuntu.com>
#

import subprocess

from charmhelpers.core.hookenv import (
    config as config_get,
    relation_get,
    relation_ids,
    related_units as relation_list,
    log,
    INFO,
)


def get_cert(cn=None):
    # TODO: deal with multiple https endpoints via charm config
    cert = config_get('ssl_cert')
    key = config_get('ssl_key')
    if not (cert and key):
        log("Inspecting identity-service relations for SSL certificate.",
            level=INFO)
        cert = key = None
        if cn:
            ssl_cert_attr = 'ssl_cert_{}'.format(cn)
            ssl_key_attr = 'ssl_key_{}'.format(cn)
        else:
            ssl_cert_attr = 'ssl_cert'
            ssl_key_attr = 'ssl_key'
        for r_id in relation_ids('identity-service'):
            for unit in relation_list(r_id):
                if not cert:
                    cert = relation_get(ssl_cert_attr,
                                        rid=r_id, unit=unit)
                if not key:
                    key = relation_get(ssl_key_attr,
                                       rid=r_id, unit=unit)
    return (cert, key)


def get_ca_cert():
    ca_cert = config_get('ssl_ca')
    if ca_cert is None:
        log("Inspecting identity-service relations for CA SSL certificate.",
            level=INFO)
        for r_id in relation_ids('identity-service'):
            for unit in relation_list(r_id):
                if ca_cert is None:
                    ca_cert = relation_get('ca_cert',
                                           rid=r_id, unit=unit)
    return ca_cert


def install_ca_cert(ca_cert):
    if ca_cert:
        with open('/usr/local/share/ca-certificates/keystone_juju_ca_cert.crt',
                  'w') as crt:
            crt.write(ca_cert)
        subprocess.check_call(['update-ca-certificates', '--fresh'])
