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

from collections import OrderedDict

from charmhelpers.core.hookenv import (
    config,
    log,
    DEBUG,
    WARNING,
)
from charmhelpers.contrib.hardening.host.checks import run_os_checks
from charmhelpers.contrib.hardening.ssh.checks import run_ssh_checks
from charmhelpers.contrib.hardening.mysql.checks import run_mysql_checks
from charmhelpers.contrib.hardening.apache.checks import run_apache_checks


def harden(overrides=None):
    """Hardening decorator.

    This is the main entry point for running the hardening stack. In order to
    run modules of the stack you must add this decorator to charm hook(s) and
    ensure that your charm config.yaml contains the 'harden' option set to
    one or more of the supported modules. Setting these will cause the
    corresponding hardening code to be run when the hook fires.

    This decorator can and should be applied to more than one hook or function
    such that hardening modules are called multiple times. This is because
    subsequent calls will perform auditing checks that will report any changes
    to resources hardened by the first run (and possibly perform compliance
    actions as a result of any detected infractions).

    :param overrides: Optional list of stack modules used to override those
                      provided with 'harden' config.
    :returns: Returns value returned by decorated function once executed.
    """
    def _harden_inner1(f):
        log("Hardening function '%s'" % (f.__name__), level=DEBUG)

        def _harden_inner2(*args, **kwargs):
            RUN_CATALOG = OrderedDict([('os', run_os_checks),
                                       ('ssh', run_ssh_checks),
                                       ('mysql', run_mysql_checks),
                                       ('apache', run_apache_checks)])

            enabled = overrides or (config("harden") or "").split()
            if enabled:
                modules_to_run = []
                # modules will always be performed in the following order
                for module, func in six.iteritems(RUN_CATALOG):
                    if module in enabled:
                        enabled.remove(module)
                        modules_to_run.append(func)

                if enabled:
                    log("Unknown hardening modules '%s' - ignoring" %
                        (', '.join(enabled)), level=WARNING)

                for hardener in modules_to_run:
                    log("Executing hardening module '%s'" %
                        (hardener.__name__), level=DEBUG)
                    hardener()
            else:
                log("No hardening applied to '%s'" % (f.__name__), level=DEBUG)

            return f(*args, **kwargs)
        return _harden_inner2

    return _harden_inner1
