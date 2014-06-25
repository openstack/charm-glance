import sys

from charmhelpers.fetch import apt_install
from charmhelpers.core.hookenv import (
    ERROR, log,
)

try:
    import netifaces
except ImportError:
    apt_install('python-netifaces')
    import netifaces

try:
    import netaddr
except ImportError:
    apt_install('python-netaddr')
    import netaddr


def _validate_cidr(network):
    try:
        netaddr.IPNetwork(network)
    except (netaddr.core.AddrFormatError, ValueError):
        raise ValueError("Network (%s) is not in CIDR presentation format" %
                         network)


def get_address_in_network(network, fallback=None, fatal=False):
    """
    Get an IPv4 address within the network from the host.

    Args:
        network (str): CIDR presentation format. For example,
                       '192.168.1.0/24'.
        fallback (str): If no address is found, return fallback.
        fatal (boolean): If no address is found, fallback is not
                         set and fatal is True then exit(1).
    """

    def not_found_error_out():
        log("No IP address found in network: %s" % network,
            level=ERROR)
        sys.exit(1)

    if network is None:
        if fallback is not None:
            return fallback
        else:
            if fatal:
                not_found_error_out()

    _validate_cidr(network)
    for iface in netifaces.interfaces():
        addresses = netifaces.ifaddresses(iface)
        if netifaces.AF_INET in addresses:
            addr = addresses[netifaces.AF_INET][0]['addr']
            netmask = addresses[netifaces.AF_INET][0]['netmask']
            cidr = netaddr.IPNetwork("%s/%s" % (addr, netmask))
            if cidr in netaddr.IPNetwork(network):
                return str(cidr.ip)

    if fallback is not None:
        return fallback

    if fatal:
        not_found_error_out()

    return None
