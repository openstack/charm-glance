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

from __future__ import absolute_import  # required for external apt import
from apt import apt_pkg
from six import string_types

from charmhelpers.fetch import (
    apt_cache,
    apt_purge
)
from charmhelpers.core.hookenv import (
    log,
    DEBUG,
    WARNING,
)
from charmhelpers.contrib.hardening.audits import BaseAudit


class AptConfig(BaseAudit):

    def __init__(self, config, **kwargs):
        self.config = config

    def verify_config(self):
        apt_pkg.init()
        for cfg in self.config:
            value = apt_pkg.config.get(cfg['key'], cfg.get('default', ''))
            if value and value != cfg['expected']:
                log("APT config '%s' has unexpected value '%s' "
                    "(expected='%s')" %
                    (cfg['key'], value, cfg['expected']), level=WARNING)

    def ensure_compliance(self):
        self.verify_config()


class RestrictedPackages(BaseAudit):
    """Class used to audit restricted packages on the system."""

    def __init__(self, pkgs, **kwargs):
        super(RestrictedPackages, self).__init__(**kwargs)
        if isinstance(pkgs, string_types) or not hasattr(pkgs, '__iter__'):
            self.pkgs = [pkgs]
        else:
            self.pkgs = pkgs

    def ensure_compliance(self):
        cache = apt_cache()

        for p in self.pkgs:
            if p not in cache:
                continue

            pkg = cache[p]
            if not self.is_virtual_package(pkg):
                if not pkg.current_ver:
                    log("Package '%s' is not installed." % pkg.name,
                        level=DEBUG)
                    continue
                else:
                    log("Restricted package '%s' is installed" % pkg.name,
                        level=WARNING)
                    self.delete_package(cache, pkg)
            else:
                log("Checking restricted virtual package '%s' provides" %
                    pkg.name, level=DEBUG)
                self.delete_package(cache, pkg)

    def delete_package(self, cache, pkg):
        """Deletes the package from the system.

        Deletes the package form the system, properly handling virtual
        packages.

        :param cache: the apt cache
        :param pkg: the package to remove
        """
        if self.is_virtual_package(pkg):
            log("Package '%s' appears to be virtual - purging provides" %
                pkg.name, level=DEBUG)
            for _p in pkg.provides_list:
                self.delete_package(cache, _p[2].parent_pkg)
        elif not pkg.current_ver:
            log("Package '%s' not installed" % pkg.name, level=DEBUG)
            return
        else:
            log("Purging package '%s'" % pkg.name, level=DEBUG)
            apt_purge(pkg.name)

    def is_virtual_package(self, pkg):
        return pkg.has_provides and not pkg.has_versions
