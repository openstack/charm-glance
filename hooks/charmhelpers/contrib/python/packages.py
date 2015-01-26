#!/usr/bin/env python
# coding: utf-8

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

__author__ = "Jorge Niedbalski <jorge.niedbalski@canonical.com>"

from charmhelpers.fetch import apt_install, apt_update
from charmhelpers.core.hookenv import log

try:
    from pip import main as pip_execute
except ImportError:
    apt_update()
    apt_install('python-pip')
    from pip import main as pip_execute


def parse_options(given, available):
    """Given a set of options, check if available"""
    for key, value in sorted(given.items()):
        if key in available:
            yield "--{0}={1}".format(key, value)


def pip_install_requirements(requirements, **options):
    """Install a requirements file """
    command = ["install"]

    available_options = ('proxy', 'src', 'log', )
    for option in parse_options(options, available_options):
        command.append(option)

    command.append("-r {0}".format(requirements))
    log("Installing from file: {} with options: {}".format(requirements,
                                                           command))
    pip_execute(command)


def pip_install(package, fatal=False, upgrade=False, **options):
    """Install a python package"""
    command = ["install"]

    available_options = ('proxy', 'src', 'log', "index-url", )
    for option in parse_options(options, available_options):
        command.append(option)

    if upgrade:
        command.append('--upgrade')

    if isinstance(package, list):
        command.extend(package)
    else:
        command.append(package)

    log("Installing {} package with options: {}".format(package,
                                                        command))
    pip_execute(command)


def pip_uninstall(package, **options):
    """Uninstall a python package"""
    command = ["uninstall", "-q", "-y"]

    available_options = ('proxy', 'log', )
    for option in parse_options(options, available_options):
        command.append(option)

    if isinstance(package, list):
        command.extend(package)
    else:
        command.append(package)

    log("Uninstalling {} package with options: {}".format(package,
                                                          command))
    pip_execute(command)


def pip_list():
    """Returns the list of current python installed packages
    """
    return pip_execute(["list"])
