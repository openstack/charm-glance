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

from charmhelpers.core.hookenv import (
    log,
    DEBUG,
)
from charmhelpers.contrib.hardening.host.checks import (
    apt,
    limits,
    login,
    minimize_access,
    pam,
    profile,
    securetty,
    suid_sgid,
    sysctl
)


def run_os_checks():
    log("Starting OS hardening checks.", level=DEBUG)
    checks = apt.get_audits()
    checks.extend(limits.get_audits())
    checks.extend(login.get_audits())
    checks.extend(minimize_access.get_audits())
    checks.extend(pam.get_audits())
    checks.extend(profile.get_audits())
    checks.extend(securetty.get_audits())
    checks.extend(suid_sgid.get_audits())
    checks.extend(sysctl.get_audits())

    for check in checks:
        log("Running '%s' check" % (check.__class__.__name__), level=DEBUG)
        check.ensure_compliance()

    log("OS hardening checks complete.", level=DEBUG)
