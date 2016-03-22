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
    DirectoryPermissionAudit,
    TemplatedFile,
)
from charmhelpers.contrib.hardening.host import TEMPLATES_DIR
from charmhelpers.contrib.hardening import utils


def get_audits():
    """Get OS hardening security limits audits.

    :returns:  dictionary of audits
    """
    audits = []
    settings = utils.get_settings('os')

    # Ensure that the /etc/security/limits.d directory is only writable
    # by the root user, but others can execute and read.
    audits.append(DirectoryPermissionAudit('/etc/security/limits.d',
                                           user='root', group='root',
                                           mode=0o755))

    # If core dumps are not enabled, then don't allow core dumps to be
    # created as they may contain sensitive information.
    if not settings['security']['kernel_enable_core_dump']:
        audits.append(TemplatedFile('/etc/security/limits.d/10.hardcore.conf',
                                    SecurityLimitsContext(),
                                    template_dir=TEMPLATES_DIR,
                                    user='root', group='root', mode=0o0440))
    return audits


class SecurityLimitsContext(object):

    def __call__(self):
        settings = utils.get_settings('os')
        ctxt = {'disable_core_dump':
                not settings['security']['kernel_enable_core_dump']}
        return ctxt
