# Copyright 2016 Canonical Limited.
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

from charmhelpers.contrib.hardening.utils import get_settings
from charmhelpers.contrib.hardening.audits.apt import (
    AptConfig,
    RestrictedPackages,
)


def get_audits():
    """Get OS hardening apt audits.

    :returns:  dictionary of audits
    """
    audits = [AptConfig([{'key': 'APT::Get::AllowUnauthenticated',
                          'expected': 'false'}])]

    settings = get_settings('os')
    clean_packages = settings['security']['packages_clean']
    if clean_packages:
        security_packages = settings['security']['packages_list']
        if security_packages:
            audits.append(RestrictedPackages(security_packages))

    return audits
