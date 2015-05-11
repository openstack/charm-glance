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

import six
from collections import OrderedDict
from charmhelpers.contrib.amulet.deployment import (
    AmuletDeployment
)


class OpenStackAmuletDeployment(AmuletDeployment):
    """OpenStack amulet deployment.

       This class inherits from AmuletDeployment and has additional support
       that is specifically for use by OpenStack charms.
       """

    def __init__(self, series=None, openstack=None, source=None, stable=True):
        """Initialize the deployment environment."""
        super(OpenStackAmuletDeployment, self).__init__(series)
        self.openstack = openstack
        self.source = source
        self.stable = stable
        # Note(coreycb): this needs to be changed when new next branches come
        # out.
        self.current_next = "trusty"

    def _determine_branch_locations(self, other_services):
        """Determine the branch locations for the other services.

           Determine if the local branch being tested is derived from its
           stable or next (dev) branch, and based on this, use the corresonding
           stable or next branches for the other_services."""
        base_charms = ['mysql', 'mongodb']

        if self.series in ['precise', 'trusty']:
            base_series = self.series
        else:
            base_series = self.current_next

        if self.stable:
            for svc in other_services:
                temp = 'lp:charms/{}/{}'
                svc['location'] = temp.format(base_series,
                                              svc['name'])
        else:
            for svc in other_services:
                if svc['name'] in base_charms:
                    temp = 'lp:charms/{}/{}'
                    svc['location'] = temp.format(base_series,
                                                  svc['name'])
                else:
                    temp = 'lp:~openstack-charmers/charms/{}/{}/next'
                    svc['location'] = temp.format(self.current_next,
                                                  svc['name'])
        return other_services

    def _add_services(self, this_service, other_services):
        """Add services to the deployment and set openstack-origin/source."""
        other_services = self._determine_branch_locations(other_services)

        super(OpenStackAmuletDeployment, self)._add_services(this_service,
                                                             other_services)

        services = other_services
        services.append(this_service)
        use_source = ['mysql', 'mongodb', 'rabbitmq-server', 'ceph',
                      'ceph-osd', 'ceph-radosgw']
        # Openstack subordinate charms do not expose an origin option as that
        # is controlled by the principle
        ignore = ['neutron-openvswitch']

        if self.openstack:
            for svc in services:
                if svc['name'] not in use_source + ignore:
                    config = {'openstack-origin': self.openstack}
                    self.d.configure(svc['name'], config)

        if self.source:
            for svc in services:
                if svc['name'] in use_source and svc['name'] not in ignore:
                    config = {'source': self.source}
                    self.d.configure(svc['name'], config)

    def _configure_services(self, configs):
        """Configure all of the services."""
        for service, config in six.iteritems(configs):
            self.d.configure(service, config)

    def _get_openstack_release(self):
        """Get openstack release.

           Return an integer representing the enum value of the openstack
           release.
           """
        # Must be ordered by OpenStack release (not by Ubuntu release):
        (self.precise_essex, self.precise_folsom, self.precise_grizzly,
         self.precise_havana, self.precise_icehouse,
         self.trusty_icehouse, self.trusty_juno, self.utopic_juno,
         self.trusty_kilo, self.vivid_kilo) = range(10)

        releases = {
            ('precise', None): self.precise_essex,
            ('precise', 'cloud:precise-folsom'): self.precise_folsom,
            ('precise', 'cloud:precise-grizzly'): self.precise_grizzly,
            ('precise', 'cloud:precise-havana'): self.precise_havana,
            ('precise', 'cloud:precise-icehouse'): self.precise_icehouse,
            ('trusty', None): self.trusty_icehouse,
            ('trusty', 'cloud:trusty-juno'): self.trusty_juno,
            ('trusty', 'cloud:trusty-kilo'): self.trusty_kilo,
            ('utopic', None): self.utopic_juno,
            ('vivid', None): self.vivid_kilo}
        return releases[(self.series, self.openstack)]

    def _get_openstack_release_string(self):
        """Get openstack release string.

           Return a string representing the openstack release.
           """
        releases = OrderedDict([
            ('precise', 'essex'),
            ('quantal', 'folsom'),
            ('raring', 'grizzly'),
            ('saucy', 'havana'),
            ('trusty', 'icehouse'),
            ('utopic', 'juno'),
            ('vivid', 'kilo'),
        ])
        if self.openstack:
            os_origin = self.openstack.split(':')[1]
            return os_origin.split('%s-' % self.series)[1].split('/')[0]
        else:
            return releases[self.series]
