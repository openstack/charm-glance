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

import six
import subprocess

from charmhelpers.core.hookenv import (
    log,
    WARNING,
)
from charmhelpers.contrib.hardening.audits.file import (
    FilePermissionAudit,
    DirectoryPermissionAudit,
    TemplatedFile,
)
from charmhelpers.contrib.hardening.mysql import TEMPLATES_DIR
from charmhelpers.contrib.hardening import utils


def get_audits():
    """Get MySQL hardening config audits.

    :returns:  dictionary of audits
    """
    if subprocess.call(['which', 'mysql'], stdout=subprocess.PIPE) != 0:
        log("MySQL does not appear to be installed on this node - "
            "skipping mysql hardening", level=WARNING)
        return []

    settings = utils.get_settings('mysql')
    hardening_settings = settings['hardening']
    my_cnf = hardening_settings['mysql-conf']

    audits = [
        FilePermissionAudit(paths=[my_cnf], user='root',
                            group='root', mode=0o0600),

        TemplatedFile(hardening_settings['hardening-conf'],
                      MySQLConfContext(),
                      TEMPLATES_DIR,
                      mode=0o0750,
                      user='mysql',
                      group='root',
                      service_actions=[{'service': 'mysql',
                                        'actions': ['restart']}]),

        # MySQL and Percona charms do not allow configuration of the
        # data directory, so use the default.
        DirectoryPermissionAudit('/var/lib/mysql',
                                 user='mysql',
                                 group='mysql',
                                 recursive=False,
                                 mode=0o755),

        DirectoryPermissionAudit('/etc/mysql',
                                 user='root',
                                 group='root',
                                 recursive=False,
                                 mode=0o700),
    ]

    return audits


class MySQLConfContext(object):
    """Defines the set of key/value pairs to set in a mysql config file.

    This context, when called, will return a dictionary containing the
    key/value pairs of setting to specify in the
    /etc/mysql/conf.d/hardening.cnf file.
    """
    def __call__(self):
        settings = utils.get_settings('mysql')
        # Translate for python3
        return {'mysql_settings':
                [(k, v) for k, v in six.iteritems(settings['security'])]}
