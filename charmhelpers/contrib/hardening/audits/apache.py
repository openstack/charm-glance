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

import re
import subprocess

from six import string_types

from charmhelpers.core.hookenv import (
    log,
    INFO,
    ERROR,
)

from charmhelpers.contrib.hardening.audits import BaseAudit


class DisabledModuleAudit(BaseAudit):
    """Audits Apache2 modules.

    Determines if the apache2 modules are enabled. If the modules are enabled
    then they are removed in the ensure_compliance.
    """
    def __init__(self, modules):
        if modules is None:
            self.modules = []
        elif isinstance(modules, string_types):
            self.modules = [modules]
        else:
            self.modules = modules

    def ensure_compliance(self):
        """Ensures that the modules are not loaded."""
        if not self.modules:
            return

        try:
            loaded_modules = self._get_loaded_modules()
            non_compliant_modules = []
            for module in self.modules:
                if module in loaded_modules:
                    log("Module '%s' is enabled but should not be." %
                        (module), level=INFO)
                    non_compliant_modules.append(module)

            if len(non_compliant_modules) == 0:
                return

            for module in non_compliant_modules:
                self._disable_module(module)
            self._restart_apache()
        except subprocess.CalledProcessError as e:
            log('Error occurred auditing apache module compliance. '
                'This may have been already reported. '
                'Output is: %s' % e.output, level=ERROR)

    @staticmethod
    def _get_loaded_modules():
        """Returns the modules which are enabled in Apache."""
        output = subprocess.check_output(['apache2ctl', '-M'])
        modules = []
        for line in output.strip().split():
            # Each line of the enabled module output looks like:
            #  module_name (static|shared)
            # Plus a header line at the top of the output which is stripped
            # out by the regex.
            matcher = re.search(r'^ (\S*)', line)
            if matcher:
                modules.append(matcher.group(1))
        return modules

    @staticmethod
    def _disable_module(module):
        """Disables the specified module in Apache."""
        try:
            subprocess.check_call(['a2dismod', module])
        except subprocess.CalledProcessError as e:
            # Note: catch error here to allow the attempt of disabling
            # multiple modules in one go rather than failing after the
            # first module fails.
            log('Error occurred disabling module %s. '
                'Output is: %s' % (module, e.output), level=ERROR)

    @staticmethod
    def _restart_apache():
        """Restarts the apache process"""
        subprocess.check_output(['service', 'apache2', 'restart'])
