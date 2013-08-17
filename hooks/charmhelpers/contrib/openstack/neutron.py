# Various utilies for dealing with Neutron and the renaming from Quantum.

from charmhelpers.core.hookenv import (
    config,
    log,
    ERROR,
)

from charmhelpers.contrib.openstack.utils import os_release


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
                                        relation_prefix='neutron')],
            'services': ['quantum-plugin-openvswitch-agent'],
            'packages': ['quantum-plugin-openvswitch-agent',
                         'openvswitch-datapath-dkms'],
        },
        'nvp': {
            'config': '/etc/quantum/plugins/nicira/nvp.ini',
            'driver': 'quantum.plugins.nicira.nicira_nvp_plugin.'
                      'QuantumPlugin.NvpPluginV2',
            'services': [],
            'packages': ['quantum-plugin-nicira'],
        }
    }


def neutron_plugins():
    from charmhelpers.contrib.openstack import context
    return {
        'ovs': {
            'config': '/etc/neutron/plugins/openvswitch/'
                      'ovs_neutron_plugin.ini',
            'driver': 'neutron.plugins.openvswitch.ovs_neutron_plugin.'
                      'OVSNeutronPluginV2',
            'contexts': [
                context.SharedDBContext(user=config('neutron-database-user'),
                                        database=config('neutron-database'),
                                        relation_prefix='neutron')],
            'services': ['neutron-plugin-openvswitch-agent'],
            'packages': ['neutron-plugin-openvswitch-agent',
                         'openvswitch-datapath-dkms'],
        },
        'nvp': {
            'config': '/etc/neutron/plugins/nicira/nvp.ini',
            'driver': 'neutron.plugins.nicira.nicira_nvp_plugin.'
                      'NeutronPlugin.NvpPluginV2',
            'services': [],
            'packages': ['neutron-plugin-nicira'],
        }
    }


def neutron_plugin_attribute(plugin, attr, net_manager=None):
    manager = net_manager or network_manager()
    if manager == 'quantum':
        plugins = quantum_plugins()
    elif manager == 'neutron':
        plugins = neutron_plugins()
    else:
        log('Error: Network manager does not support plugins.')
        raise Exception

    try:
        _plugin = plugins[plugin]
    except KeyError:
        log('Unrecognised plugin for %s: %s' % (manager, plugin), level=ERROR)
        raise

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
        raise
    elif release in ['folsom', 'grizzly']:
        # neutron is named quantum in F and G
        return 'quantum'
    else:
        # ensure accurate naming for all releases post-H
        return 'neutron'
