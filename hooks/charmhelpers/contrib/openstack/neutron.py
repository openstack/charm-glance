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

# Various utilies for dealing with Neutron and the renaming from Quantum.

import six
from subprocess import check_output

from charmhelpers.core.hookenv import (
    config,
    log,
    ERROR,
)

from charmhelpers.contrib.openstack.utils import os_release


def headers_package():
    """Ensures correct linux-headers for running kernel are installed,
    for building DKMS package"""
    kver = check_output(['uname', '-r']).decode('UTF-8').strip()
    return 'linux-headers-%s' % kver

QUANTUM_CONF_DIR = '/etc/quantum'


def kernel_version():
    """ Retrieve the current major kernel version as a tuple e.g. (3, 13) """
    kver = check_output(['uname', '-r']).decode('UTF-8').strip()
    kver = kver.split('.')
    return (int(kver[0]), int(kver[1]))


def determine_dkms_package():
    """ Determine which DKMS package should be used based on kernel version """
    # NOTE: 3.13 kernels have support for GRE and VXLAN native
    if kernel_version() >= (3, 13):
        return []
    else:
        return ['openvswitch-datapath-dkms']


# legacy


def quantum_plugins():
    from charmhelpers.contrib.openstack import context
    return {
        'ovs': {
            'config': '/etc/quantum/plugins/openvswitch/'
                      'ovs_quantum_plugin.ini',
            'driver': 'quantum.plugins.openvswitch.ovs_quantum_plugin.'
                      'OVSQuantumPluginV2',
            'contexts': [
                context.SharedDBContext(user=config('neutron-database-user'),
                                        database=config('neutron-database'),
                                        relation_prefix='neutron',
                                        ssl_dir=QUANTUM_CONF_DIR)],
            'services': ['quantum-plugin-openvswitch-agent'],
            'packages': [[headers_package()] + determine_dkms_package(),
                         ['quantum-plugin-openvswitch-agent']],
            'server_packages': ['quantum-server',
                                'quantum-plugin-openvswitch'],
            'server_services': ['quantum-server']
        },
        'nvp': {
            'config': '/etc/quantum/plugins/nicira/nvp.ini',
            'driver': 'quantum.plugins.nicira.nicira_nvp_plugin.'
                      'QuantumPlugin.NvpPluginV2',
            'contexts': [
                context.SharedDBContext(user=config('neutron-database-user'),
                                        database=config('neutron-database'),
                                        relation_prefix='neutron',
                                        ssl_dir=QUANTUM_CONF_DIR)],
            'services': [],
            'packages': [],
            'server_packages': ['quantum-server',
                                'quantum-plugin-nicira'],
            'server_services': ['quantum-server']
        }
    }

NEUTRON_CONF_DIR = '/etc/neutron'


def neutron_plugins():
    from charmhelpers.contrib.openstack import context
    release = os_release('nova-common')
    plugins = {
        'ovs': {
            'config': '/etc/neutron/plugins/openvswitch/'
                      'ovs_neutron_plugin.ini',
            'driver': 'neutron.plugins.openvswitch.ovs_neutron_plugin.'
                      'OVSNeutronPluginV2',
            'contexts': [
                context.SharedDBContext(user=config('neutron-database-user'),
                                        database=config('neutron-database'),
                                        relation_prefix='neutron',
                                        ssl_dir=NEUTRON_CONF_DIR)],
            'services': ['neutron-plugin-openvswitch-agent'],
            'packages': [[headers_package()] + determine_dkms_package(),
                         ['neutron-plugin-openvswitch-agent']],
            'server_packages': ['neutron-server',
                                'neutron-plugin-openvswitch'],
            'server_services': ['neutron-server']
        },
        'nvp': {
            'config': '/etc/neutron/plugins/nicira/nvp.ini',
            'driver': 'neutron.plugins.nicira.nicira_nvp_plugin.'
                      'NeutronPlugin.NvpPluginV2',
            'contexts': [
                context.SharedDBContext(user=config('neutron-database-user'),
                                        database=config('neutron-database'),
                                        relation_prefix='neutron',
                                        ssl_dir=NEUTRON_CONF_DIR)],
            'services': [],
            'packages': [],
            'server_packages': ['neutron-server',
                                'neutron-plugin-nicira'],
            'server_services': ['neutron-server']
        },
        'nsx': {
            'config': '/etc/neutron/plugins/vmware/nsx.ini',
            'driver': 'vmware',
            'contexts': [
                context.SharedDBContext(user=config('neutron-database-user'),
                                        database=config('neutron-database'),
                                        relation_prefix='neutron',
                                        ssl_dir=NEUTRON_CONF_DIR)],
            'services': [],
            'packages': [],
            'server_packages': ['neutron-server',
                                'neutron-plugin-vmware'],
            'server_services': ['neutron-server']
        },
        'n1kv': {
            'config': '/etc/neutron/plugins/cisco/cisco_plugins.ini',
            'driver': 'neutron.plugins.cisco.network_plugin.PluginV2',
            'contexts': [
                context.SharedDBContext(user=config('neutron-database-user'),
                                        database=config('neutron-database'),
                                        relation_prefix='neutron',
                                        ssl_dir=NEUTRON_CONF_DIR)],
            'services': [],
            'packages': [[headers_package()] + determine_dkms_package(),
                         ['neutron-plugin-cisco']],
            'server_packages': ['neutron-server',
                                'neutron-plugin-cisco'],
            'server_services': ['neutron-server']
        },
        'Calico': {
            'config': '/etc/neutron/plugins/ml2/ml2_conf.ini',
            'driver': 'neutron.plugins.ml2.plugin.Ml2Plugin',
            'contexts': [
                context.SharedDBContext(user=config('neutron-database-user'),
                                        database=config('neutron-database'),
                                        relation_prefix='neutron',
                                        ssl_dir=NEUTRON_CONF_DIR)],
            'services': ['calico-felix',
                         'bird',
                         'neutron-dhcp-agent',
                         'nova-api-metadata'],
            'packages': [[headers_package()] + determine_dkms_package(),
                         ['calico-compute',
                          'bird',
                          'neutron-dhcp-agent',
                          'nova-api-metadata']],
            'server_packages': ['neutron-server', 'calico-control'],
            'server_services': ['neutron-server']
        },
        'vsp': {
            'config': '/etc/neutron/plugins/nuage/nuage_plugin.ini',
            'driver': 'neutron.plugins.nuage.plugin.NuagePlugin',
            'contexts': [
                context.SharedDBContext(user=config('neutron-database-user'),
                                        database=config('neutron-database'),
                                        relation_prefix='neutron',
                                        ssl_dir=NEUTRON_CONF_DIR)],
            'services': [],
            'packages': [],
            'server_packages': ['neutron-server', 'neutron-plugin-nuage'],
            'server_services': ['neutron-server']
        }
    }
    if release >= 'icehouse':
        # NOTE: patch in ml2 plugin for icehouse onwards
        plugins['ovs']['config'] = '/etc/neutron/plugins/ml2/ml2_conf.ini'
        plugins['ovs']['driver'] = 'neutron.plugins.ml2.plugin.Ml2Plugin'
        plugins['ovs']['server_packages'] = ['neutron-server',
                                             'neutron-plugin-ml2']
        # NOTE: patch in vmware renames nvp->nsx for icehouse onwards
        plugins['nvp'] = plugins['nsx']
    return plugins


def neutron_plugin_attribute(plugin, attr, net_manager=None):
    manager = net_manager or network_manager()
    if manager == 'quantum':
        plugins = quantum_plugins()
    elif manager == 'neutron':
        plugins = neutron_plugins()
    else:
        log("Network manager '%s' does not support plugins." % (manager),
            level=ERROR)
        raise Exception

    try:
        _plugin = plugins[plugin]
    except KeyError:
        log('Unrecognised plugin for %s: %s' % (manager, plugin), level=ERROR)
        raise Exception

    try:
        return _plugin[attr]
    except KeyError:
        return None


def network_manager():
    '''
    Deals with the renaming of Quantum to Neutron in H and any situations
    that require compatability (eg, deploying H with network-manager=quantum,
    upgrading from G).
    '''
    release = os_release('nova-common')
    manager = config('network-manager').lower()

    if manager not in ['quantum', 'neutron']:
        return manager

    if release in ['essex']:
        # E does not support neutron
        log('Neutron networking not supported in Essex.', level=ERROR)
        raise Exception
    elif release in ['folsom', 'grizzly']:
        # neutron is named quantum in F and G
        return 'quantum'
    else:
        # ensure accurate naming for all releases post-H
        return 'neutron'


def parse_mappings(mappings):
    parsed = {}
    if mappings:
        mappings = mappings.split()
        for m in mappings:
            p = m.partition(':')
            key = p[0].strip()
            if p[1]:
                parsed[key] = p[2].strip()
            else:
                parsed[key] = ''

    return parsed


def parse_bridge_mappings(mappings):
    """Parse bridge mappings.

    Mappings must be a space-delimited list of provider:bridge mappings.

    Returns dict of the form {provider:bridge}.
    """
    return parse_mappings(mappings)


def parse_data_port_mappings(mappings, default_bridge='br-data'):
    """Parse data port mappings.

    Mappings must be a space-delimited list of bridge:port mappings.

    Returns dict of the form {bridge:port}.
    """
    _mappings = parse_mappings(mappings)
    if not _mappings or list(_mappings.values()) == ['']:
        if not mappings:
            return {}

        # For backwards-compatibility we need to support port-only provided in
        # config.
        _mappings = {default_bridge: mappings.split()[0]}

    bridges = _mappings.keys()
    ports = _mappings.values()
    if len(set(bridges)) != len(bridges):
        raise Exception("It is not allowed to have more than one port "
                        "configured on the same bridge")

    if len(set(ports)) != len(ports):
        raise Exception("It is not allowed to have the same port configured "
                        "on more than one bridge")

    return _mappings


def parse_vlan_range_mappings(mappings):
    """Parse vlan range mappings.

    Mappings must be a space-delimited list of provider:start:end mappings.

    The start:end range is optional and may be omitted.

    Returns dict of the form {provider: (start, end)}.
    """
    _mappings = parse_mappings(mappings)
    if not _mappings:
        return {}

    mappings = {}
    for p, r in six.iteritems(_mappings):
        mappings[p] = tuple(r.split(':'))

    return mappings
