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

from charmhelpers.core.hookenv import (
    config,
    unit_get,
)
from charmhelpers.contrib.network.ip import (
    get_address_in_network,
    is_address_in_network,
    is_ipv6,
    get_ipv6_addr,
)
from charmhelpers.contrib.hahelpers.cluster import is_clustered

from functools import partial

PUBLIC = 'public'
INTERNAL = 'int'
ADMIN = 'admin'

ADDRESS_MAP = {
    PUBLIC: {
        'config': 'os-public-network',
        'fallback': 'public-address'
    },
    INTERNAL: {
        'config': 'os-internal-network',
        'fallback': 'private-address'
    },
    ADMIN: {
        'config': 'os-admin-network',
        'fallback': 'private-address'
    }
}


def canonical_url(configs, endpoint_type=PUBLIC):
    """Returns the correct HTTP URL to this host given the state of HTTPS
    configuration, hacluster and charm configuration.

    :param configs: OSTemplateRenderer config templating object to inspect
                    for a complete https context.
    :param endpoint_type: str endpoint type to resolve.
    :param returns: str base URL for services on the current service unit.
    """
    scheme = 'http'
    if 'https' in configs.complete_contexts():
        scheme = 'https'
    address = resolve_address(endpoint_type)
    if is_ipv6(address):
        address = "[{}]".format(address)
    return '%s://%s' % (scheme, address)


def resolve_address(endpoint_type=PUBLIC):
    """Return unit address depending on net config.

    If unit is clustered with vip(s) and has net splits defined, return vip on
    correct network. If clustered with no nets defined, return primary vip.

    If not clustered, return unit address ensuring address is on configured net
    split if one is configured.

    :param endpoint_type: Network endpoing type
    """
    resolved_address = None
    vips = config('vip')
    if vips:
        vips = vips.split()

    net_type = ADDRESS_MAP[endpoint_type]['config']
    net_addr = config(net_type)
    net_fallback = ADDRESS_MAP[endpoint_type]['fallback']
    clustered = is_clustered()
    if clustered:
        if not net_addr:
            # If no net-splits defined, we expect a single vip
            resolved_address = vips[0]
        else:
            for vip in vips:
                if is_address_in_network(net_addr, vip):
                    resolved_address = vip
                    break
    else:
        if config('prefer-ipv6'):
            fallback_addr = get_ipv6_addr(exc_list=vips)[0]
        else:
            fallback_addr = unit_get(net_fallback)

        resolved_address = get_address_in_network(net_addr, fallback_addr)

    if resolved_address is None:
        raise ValueError("Unable to resolve a suitable IP address based on "
                         "charm state and configuration. (net_type=%s, "
                         "clustered=%s)" % (net_type, clustered))

    return resolved_address


def endpoint_url(configs, url_template, port, endpoint_type=PUBLIC,
                 override=None):
    """Returns the correct endpoint URL to advertise to Keystone.

    This method provides the correct endpoint URL which should be advertised to
    the keystone charm for endpoint creation. This method allows for the url to
    be overridden to force a keystone endpoint to have specific URL for any of
    the defined scopes (admin, internal, public).

    :param configs: OSTemplateRenderer config templating object to inspect
                    for a complete https context.
    :param url_template: str format string for creating the url template. Only
                         two values will be passed - the scheme+hostname
                        returned by the canonical_url and the port.
    :param endpoint_type: str endpoint type to resolve.
    :param override: str the name of the config option which overrides the
                     endpoint URL defined by the charm itself. None will
                     disable any overrides (default).
    """
    if override:
        # Return any user-defined overrides for the keystone endpoint URL.
        user_value = config(override)
        if user_value:
            return user_value.strip()

    return url_template % (canonical_url(configs, endpoint_type), port)


public_endpoint = partial(endpoint_url, endpoint_type=PUBLIC)

internal_endpoint = partial(endpoint_url, endpoint_type=INTERNAL)

admin_endpoint = partial(endpoint_url, endpoint_type=ADMIN)
