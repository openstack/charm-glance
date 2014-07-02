
from netaddr import IPAddress, IPNetwork

class VIPConfiguration():
    
    def __init__(self, configuration):
        self.vip = []
        for vip in configuration.split():
            self.vips.append(IPAddress(vip))

    def getVIP(self, network):
        ''' Determine the VIP for the provided network        
        :network str: CIDR presented network, e.g. 192.168.1.1/24
        :returns str: IP address of VIP in provided network or None
        '''
        network = IPNetwork(network)
        for vip in self.vips:
            if vip in network:
                return str(vip)
        return None

    def getNIC(self, network):
        ''' Determine the physical network interface in use
        for the specified network'''

