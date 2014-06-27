from charmhelpers.contrib.amulet.deployment import (
    AmuletDeployment
)


class OpenStackAmuletDeployment(AmuletDeployment):
    """This class inherits from AmuletDeployment and has additional support
       that is specifically for use by OpenStack charms."""

    def __init__(self, series=None, openstack=None):
        """Initialize the deployment environment."""
        self.openstack = None
        super(OpenStackAmuletDeployment, self).__init__(series)

        if openstack:
            self.openstack = openstack

    def _configure_services(self, configs):
        """Configure all of the services."""
        for service, config in configs.iteritems():
            if service == self.this_service:
                config['openstack-origin'] = self.openstack
            self.d.configure(service, config)

    def _get_openstack_release(self):
        """Return an integer representing the enum value of the openstack
           release."""
        self.precise_essex, self.precise_folsom, self.precise_grizzly, \
            self.precise_havana, self.precise_icehouse, \
            self.trusty_icehouse = range(6)
        releases = {
            ('precise', None): self.precise_essex,
            ('precise', 'cloud:precise-folsom'): self.precise_folsom,
            ('precise', 'cloud:precise-grizzly'): self.precise_grizzly,
            ('precise', 'cloud:precise-havana'): self.precise_havana,
            ('precise', 'cloud:precise-icehouse'): self.precise_icehouse,
            ('trusty', None): self.trusty_icehouse}
        return releases[(self.series, self.openstack)]
