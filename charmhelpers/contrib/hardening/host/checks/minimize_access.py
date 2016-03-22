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

from charmhelpers.contrib.hardening.audits.file import (
    FilePermissionAudit,
    ReadOnly,
)
from charmhelpers.contrib.hardening import utils


def get_audits():
    """Get OS hardening access audits.

    :returns:  dictionary of audits
    """
    audits = []
    settings = utils.get_settings('os')

    # Remove write permissions from $PATH folders for all regular users.
    # This prevents changing system-wide commands from normal users.
    path_folders = {'/usr/local/sbin',
                    '/usr/local/bin',
                    '/usr/sbin',
                    '/usr/bin',
                    '/bin'}
    extra_user_paths = settings['environment']['extra_user_paths']
    path_folders.update(extra_user_paths)
    audits.append(ReadOnly(path_folders))

    # Only allow the root user to have access to the shadow file.
    audits.append(FilePermissionAudit('/etc/shadow', 'root', 'root', 0o0600))

    if 'change_user' not in settings['security']['users_allow']:
        # su should only be accessible to user and group root, unless it is
        # expressly defined to allow users to change to root via the
        # security_users_allow config option.
        audits.append(FilePermissionAudit('/bin/su', 'root', 'root', 0o750))

    return audits
