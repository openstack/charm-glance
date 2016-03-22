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


class BaseAudit(object):  # NO-QA
    """Base class for hardening checks.

    The lifecycle of a hardening check is to first check to see if the system
    is in compliance for the specified check. If it is not in compliance, the
    check method will return a value which will be supplied to the.
    """
    def __init__(self, *args, **kwargs):
        self.unless = kwargs.get('unless', None)
        super(BaseAudit, self).__init__()

    def ensure_compliance(self):
        """Checks to see if the current hardening check is in compliance or
        not.

        If the check that is performed is not in compliance, then an exception
        should be raised.
        """
        pass

    def _take_action(self):
        """Determines whether to perform the action or not.

        Checks whether or not an action should be taken. This is determined by
        the truthy value for the unless parameter. If unless is a callback
        method, it will be invoked with no parameters in order to determine
        whether or not the action should be taken. Otherwise, the truthy value
        of the unless attribute will determine if the action should be
        performed.
        """
        # Do the action if there isn't an unless override.
        if self.unless is None:
            return True

        # Invoke the callback if there is one.
        if hasattr(self.unless, '__call__'):
            results = self.unless()
            if results:
                return False
            else:
                return True

        if self.unless:
            return False
        else:
            return True
