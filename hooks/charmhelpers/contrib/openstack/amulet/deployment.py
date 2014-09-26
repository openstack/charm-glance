from bzrlib.branch import Branch
import os
import re
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

    def _is_dev_branch(self):
        """Determine if branch being tested is a dev (i.e. next) branch."""
        branch = Branch.open(os.getcwd())
        parent = branch.get_parent()
        pattern = re.compile("^.*/next/$")
        if (pattern.match(parent)):
            return True
        else:
            return False

    def _determine_branch_locations(self, other_services):
        """Determine the branch locations for the other services.

           If the branch being tested is a dev branch, then determine the
           development branch locations for the other services. Otherwise,
           the default charm store branches will be used."""
        name = 0
        if self._is_dev_branch():
            updated_services = []
            for svc in other_services:
                if svc[name] in ['mysql', 'mongodb', 'rabbitmq-server']:
                    location = 'lp:charms/{}'.format(svc[name])
                else:
                    temp = 'lp:~openstack-charmers/charms/trusty/{}/next'
                    location = temp.format(svc[name])
                updated_services.append(svc + (location,))
            other_services = updated_services
        return other_services

    def _add_services(self, this_service, other_services):
        """Add services to the deployment and set openstack-origin/source."""
        name = 0
        other_services = self._determine_branch_locations(other_services)
        super(OpenStackAmuletDeployment, self)._add_services(this_service,
                                                             other_services)
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
