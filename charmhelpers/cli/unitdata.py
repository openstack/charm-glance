# Copyright 2014-2015 Canonical Limited.
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

from . import cmdline
from charmhelpers.core import unitdata


@cmdline.subcommand_builder('unitdata', description="Store and retrieve data")
def unitdata_cmd(subparser):
    nested = subparser.add_subparsers()
    get_cmd = nested.add_parser('get', help='Retrieve data')
    get_cmd.add_argument('key', help='Key to retrieve the value of')
    get_cmd.set_defaults(action='get', value=None)
    set_cmd = nested.add_parser('set', help='Store data')
    set_cmd.add_argument('key', help='Key to set')
    set_cmd.add_argument('value', help='Value to store')
    set_cmd.set_defaults(action='set')

    def _unitdata_cmd(action, key, value):
        if action == 'get':
            return unitdata.kv().get(key)
        elif action == 'set':
            unitdata.kv().set(key, value)
            unitdata.kv().flush()
            return ''
    return _unitdata_cmd
