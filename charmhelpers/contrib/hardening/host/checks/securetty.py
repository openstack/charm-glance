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

from charmhelpers.contrib.hardening.audits.file import TemplatedFile
from charmhelpers.contrib.hardening.host import TEMPLATES_DIR
from charmhelpers.contrib.hardening import utils


def get_audits():
    """Get OS hardening Secure TTY audits.

    :returns:  dictionary of audits
    """
    audits = []
    audits.append(TemplatedFile('/etc/securetty', SecureTTYContext(),
                                template_dir=TEMPLATES_DIR,
                                mode=0o0400, user='root', group='root'))
    return audits


class SecureTTYContext(object):

    def __call__(self):
        settings = utils.get_settings('os')
        ctxt = {'ttys': settings['auth']['root_ttys']}
        return ctxt
