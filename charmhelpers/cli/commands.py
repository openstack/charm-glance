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

"""
This module loads sub-modules into the python runtime so they can be
discovered via the inspect module. In order to prevent flake8 from (rightfully)
telling us these are unused modules, throw a ' # noqa' at the end of each import
so that the warning is suppressed.
"""

from . import CommandLine  # noqa

"""
Import the sub-modules which have decorated subcommands to register with chlp.
"""
from . import host  # noqa
from . import benchmark  # noqa
from . import unitdata  # noqa
from . import hookenv  # noqa
