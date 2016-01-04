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

import os
from subprocess import check_call
from charmhelpers.fetch import (
    BaseFetchHandler,
    UnhandledSource,
    filter_installed_packages,
    apt_install,
)
from charmhelpers.core.host import mkdir


if filter_installed_packages(['bzr']) != []:
    apt_install(['bzr'])
    if filter_installed_packages(['bzr']) != []:
        raise NotImplementedError('Unable to install bzr')


class BzrUrlFetchHandler(BaseFetchHandler):
    """Handler for bazaar branches via generic and lp URLs"""
    def can_handle(self, source):
        url_parts = self.parse_url(source)
        if url_parts.scheme not in ('bzr+ssh', 'lp', ''):
            return False
        elif not url_parts.scheme:
            return os.path.exists(os.path.join(source, '.bzr'))
        else:
            return True

    def branch(self, source, dest):
        if not self.can_handle(source):
            raise UnhandledSource("Cannot handle {}".format(source))
        if os.path.exists(dest):
            check_call(['bzr', 'pull', '--overwrite', '-d', dest, source])
        else:
            check_call(['bzr', 'branch', source, dest])

    def install(self, source, dest=None):
        url_parts = self.parse_url(source)
        branch_name = url_parts.path.strip("/").split("/")[-1]
        if dest:
            dest_dir = os.path.join(dest, branch_name)
        else:
            dest_dir = os.path.join(os.environ.get('CHARM_DIR'), "fetched",
                                    branch_name)

        if not os.path.exists(dest_dir):
            mkdir(dest_dir, perms=0o755)
        try:
            self.branch(source, dest_dir)
        except OSError as e:
            raise UnhandledSource(e.strerror)
        return dest_dir
