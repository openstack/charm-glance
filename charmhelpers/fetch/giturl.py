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
from subprocess import check_call, CalledProcessError
from charmhelpers.fetch import (
    BaseFetchHandler,
    UnhandledSource,
    filter_installed_packages,
    apt_install,
)

if filter_installed_packages(['git']) != []:
    apt_install(['git'])
    if filter_installed_packages(['git']) != []:
        raise NotImplementedError('Unable to install git')


class GitUrlFetchHandler(BaseFetchHandler):
    """Handler for git branches via generic and github URLs"""
    def can_handle(self, source):
        url_parts = self.parse_url(source)
        # TODO (mattyw) no support for ssh git@ yet
        if url_parts.scheme not in ('http', 'https', 'git', ''):
            return False
        elif not url_parts.scheme:
            return os.path.exists(os.path.join(source, '.git'))
        else:
            return True

    def clone(self, source, dest, branch="master", depth=None):
        if not self.can_handle(source):
            raise UnhandledSource("Cannot handle {}".format(source))

        if os.path.exists(dest):
            cmd = ['git', '-C', dest, 'pull', source, branch]
        else:
            cmd = ['git', 'clone', source, dest, '--branch', branch]
            if depth:
                cmd.extend(['--depth', depth])
        check_call(cmd)

    def install(self, source, branch="master", dest=None, depth=None):
        url_parts = self.parse_url(source)
        branch_name = url_parts.path.strip("/").split("/")[-1]
        if dest:
            dest_dir = os.path.join(dest, branch_name)
        else:
            dest_dir = os.path.join(os.environ.get('CHARM_DIR'), "fetched",
                                    branch_name)
        try:
            self.clone(source, dest_dir, branch, depth)
        except CalledProcessError as e:
            raise UnhandledSource(e)
        except OSError as e:
            raise UnhandledSource(e.strerror)
        return dest_dir
