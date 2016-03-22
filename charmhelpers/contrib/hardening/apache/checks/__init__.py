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
from charmhelpers.contrib.hardening.apache.checks import config


def run_apache_checks():
    log("Starting Apache hardening checks.", level=DEBUG)
    checks = config.get_audits()
    for check in checks:
        log("Running '%s' check" % (check.__class__.__name__), level=DEBUG)
        check.ensure_compliance()

    log("Apache hardening checks complete.", level=DEBUG)
