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
from charmhelpers.contrib.benchmark import Benchmark


@cmdline.subcommand(command_name='benchmark-start')
def start():
    Benchmark.start()


@cmdline.subcommand(command_name='benchmark-finish')
def finish():
    Benchmark.finish()


@cmdline.subcommand_builder('benchmark-composite', description="Set the benchmark composite score")
def service(subparser):
    subparser.add_argument("value", help="The composite score.")
    subparser.add_argument("units", help="The units the composite score represents, i.e., 'reads/sec'.")
    subparser.add_argument("direction", help="'asc' if a lower score is better, 'desc' if a higher score is better.")
    return Benchmark.set_composite_score
