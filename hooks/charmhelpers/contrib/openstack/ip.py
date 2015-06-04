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
    service_name,
)
from charmhelpers.contrib.network.ip import (
    get_address_in_network,
    is_address_in_network,
    is_ipv6,
    get_ipv6_addr,
)
from charmhelpers.contrib.hahelpers.cluster import is_clustered

PUBLIC = 'public'
INTERNAL = 'int'
ADMIN = 'admin'

ADDRESS_MAP = {
    PUBLIC: {
        'config': 'os-public-network',
        'fallback': 'public-address',
        'override': 'os-public-hostname',
    },
    INTERNAL: {
        'config': 'os-internal-network',
        'fallback': 'private-address',
        'override': 'os-internal-hostname',
    },
    ADMIN: {
        'config': 'os-admin-network',
        'fallback': 'private-address',
        'override': 'os-admin-hostname',
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
    scheme = _get_scheme(configs)

    address = resolve_address(endpoint_type)
    if is_ipv6(address):
        address = "[{}]".format(address)

    return '%s://%s' % (scheme, address)


def _get_scheme(configs):
    """Returns the scheme to use for the url (either http or https)
    depending upon whether https is in the configs value.

    :param configs: OSTemplateRenderer config templating object to inspect
                    for a complete https context.
    :returns: either 'http' or 'https' depending on whether https is
              configured within the configs context.
    """
    scheme = 'http'
    if configs and 'https' in configs.complete_contexts():
        scheme = 'https'
    return scheme


def _get_address_override(endpoint_type=PUBLIC):
    """Returns any address overrides that the user has defined based on the
    endpoint type.

    Note: this function allows for the service name to be inserted into the
    address if the user specifies {service_name}.somehost.org.

    :param endpoint_type: the type of endpoint to retrieve the override
                          value for.
    :returns: any endpoint address or hostname that the user has overridden
              or None if an override is not present.
    """
    override_key = ADDRESS_MAP[endpoint_type]['override']
    addr_override = config(override_key)
    if not addr_override:
        return None
    else:
        return addr_override.format(service_name=service_name())


def resolve_address(endpoint_type=PUBLIC):
    """Return unit address depending on net config.

    If unit is clustered with vip(s) and has net splits defined, return vip on
    correct network. If clustered with no nets defined, return primary vip.

    If not clustered, return unit address ensuring address is on configured net
    split if one is configured.

    :param endpoint_type: Network endpoing type
    """
    resolved_address = _get_address_override(endpoint_type)
    if resolved_address:
        return resolved_address

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
