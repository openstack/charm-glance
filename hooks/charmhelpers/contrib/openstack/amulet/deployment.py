from charmhelpers.contrib.amulet.deployment import (
    AmuletDeployment
)


class OpenStackAmuletDeployment(AmuletDeployment):
    """OpenStack amulet deployment.

       This class inherits from AmuletDeployment and has additional support
       that is specifically for use by OpenStack charms.
       """

    def __init__(self, series=None, openstack=None, source=None):
        """Initialize the deployment environment."""
        super(OpenStackAmuletDeployment, self).__init__(series)
        self.openstack = openstack
        self.source = source

    def _add_services(self, this_service, other_services):
        """Add services to the deployment and set openstack-origin."""
        super(OpenStackAmuletDeployment, self)._add_services(this_service,
                                                             other_services)
        name = 0
        services = other_services
        services.append(this_service)
        use_source = ['mysql', 'mongodb', 'rabbitmq-server', 'ceph']

        if self.openstack:
            for svc in services:
                if svc[name] not in use_source:
                    config = {'openstack-origin': self.openstack}
                    self.d.configure(svc[name], config)

        if self.source:
            for svc in services:
                if svc[name] in use_source:
                    config = {'source': self.source}
                    self.d.configure(svc[name], config)

    def _configure_services(self, configs):
        """Configure all of the services."""
        for service, config in configs.iteritems():
            self.d.configure(service, config)

    def _get_openstack_release(self):
        """Get openstack release.

           Return an integer representing the enum value of the openstack
           release.
           """
        (self.precise_essex, self.precise_folsom, self.precise_grizzly,
         self.precise_havana, self.precise_icehouse,
         self.trusty_icehouse) = range(6)
        releases = {
            ('precise', None): self.precise_essex,
            ('precise', 'cloud:precise-folsom'): self.precise_folsom,
            ('precise', 'cloud:precise-grizzly'): self.precise_grizzly,
            ('precise', 'cloud:precise-havana'): self.precise_havana,
            ('precise', 'cloud:precise-icehouse'): self.precise_icehouse,
            ('trusty', None): self.trusty_icehouse}
        return releases[(self.series, self.openstack)]
