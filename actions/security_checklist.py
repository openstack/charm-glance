#!/usr/bin/env python3
#
# Copyright 2019 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import configparser
import json
import os
import sys

sys.path.append('.')

import charmhelpers.contrib.openstack.audits as audits
from charmhelpers.contrib.openstack.audits import (
    openstack_security_guide,
)
from charmhelpers.contrib.openstack.utils import (
    CompareOpenStackReleases,
    os_release)


# Via the openstack_security_guide above, we are running the following
# security assertions automatically:
#
# - Check-Image-01 validate-file-ownership
# - Check-Image-02 validate-file-permissions


@audits.audit(audits.is_audit_type(audits.AuditType.OpenStackSecurityGuide),
              audits.before_openstack_release('glance-common', 'rocky'))
def prevent_masked_port_scans(audit_options):
    """Validate that masked port scans are disabled.

    Security Guide Check Name: Check-Image-05

    :param audit_options: Dictionary of options for audit configuration
    :type audit_options: Dict
    :raises: AssertionError if the assertion fails.
    """
    try:
        with open('/etc/glance/policy.json') as f:
            policy = json.loads(f.read())
    except json.decoder.JSONDecodeError:
        assert False, "policy.json is invalid JSON"
    assert policy is not None, "policy.json should restrict copy_from"
    assert policy.get('copy_from') is not None, \
        "policy.json should restrict copy_from"


@audits.audit(audits.is_audit_type(audits.AuditType.OpenStackSecurityGuide))
def validate_glance_uses_keystone(audit_options):
    """Validate that the service uses Keystone for authentication.

    Security Guide Check Name: Check-Image-03

    :param audit_options: Dictionary of options for audit configuration
    :type audit_options: Dict
    :raises: AssertionError if the assertion fails.
    """
    conf = configparser.ConfigParser()
    conf.read(os.path.join('/etc/glance/glance-api.conf'))
    glance_api = dict(conf)
    assert glance_api.get('DEFAULT', {}).get('auth_strategy') == "keystone", \
        "Keystone should be used for auth in glance-api.conf"
    cmp_release = CompareOpenStackReleases(os_release('glance-common'))
    if cmp_release <= 'stein':
        conf = configparser.ConfigParser()
        conf.read(os.path.join('/etc/glance/glance-registry.conf'))
        glance_registry = dict(conf)
        assert glance_registry.get('DEFAULT', {}) \
                              .get('auth_strategy') == "keystone", \
            "Keystone should be used for auth in glance-registry.conf"


@audits.audit(audits.is_audit_type(audits.AuditType.OpenStackSecurityGuide))
def validate_glance_uses_tls_for_keystone(audit_options):
    """Verify that TLS is used to communicate with Keystone.

    Security Guide Check Name: Check-Image-04

    :param audit_options: Dictionary of options for audit configuration
    :type audit_options: Dict
    :raises: AssertionError if the assertion fails.
    """
    conf = configparser.ConfigParser()
    conf.read(os.path.join('/etc/glance/glance-api.conf'))
    glance_api = dict(conf)
    assert not glance_api.get('keystone_authtoken', {}).get('insecure'), \
        "Insecure mode should not be used with TLS"
    assert glance_api.get('keystone_authtoken', {}).get('auth_uri'). \
        startswith("https://"), \
        "TLS should be used to authenticate with Keystone"
    cmp_release = CompareOpenStackReleases(os_release('glance-common'))
    if cmp_release <= 'stein':
        conf = configparser.ConfigParser()
        conf.read(os.path.join('/etc/glance/glance-registry.conf'))
        glance_registry = dict(conf)
        assert not glance_registry.get(
            'keystone_authtoken', {}).get('insecure'), \
            "Insecure mode should not be used with TLS"
        assert glance_registry.get('keystone_authtoken', {}).get('auth_uri'). \
            startswith("https://"), \
            "TLS should be used to authenticate with Keystone"


def main():
    config = {
        'config_path': '/etc/glance',
        'config_file': 'glance-api.conf',
        'audit_type': audits.AuditType.OpenStackSecurityGuide,
        'files': openstack_security_guide.FILE_ASSERTIONS['glance'],
        'excludes': [
            'validate-uses-tls-for-glance',
            'validate-uses-keystone',
            'validate-uses-tls-for-keystone',
        ],
    }
    return audits.action_parse_results(audits.run(config))


if __name__ == "__main__":
    sys.exit(main())
