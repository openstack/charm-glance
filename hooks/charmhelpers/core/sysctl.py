#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

__author__ = 'Jorge Niedbalski R. <jorge.niedbalski@canonical.com>'

import yaml

from subprocess import check_call

from charmhelpers.core.hookenv import (
    log,
    DEBUG,
)


def create(sysctl_dict, sysctl_file):
    """Creates a sysctl.conf file from a YAML associative array

    :param sysctl_dict: a dict of sysctl options eg { 'kernel.max_pid': 1337 }
    :type sysctl_dict: dict
    :param sysctl_file: path to the sysctl file to be saved
    :type sysctl_file: str or unicode
    :returns: None
    """
    sysctl_dict = yaml.load(sysctl_dict)

    with open(sysctl_file, "w") as fd:
        for key, value in sysctl_dict.items():
            fd.write("{}={}\n".format(key, value))

    log("Updating sysctl_file: %s values: %s" % (sysctl_file, sysctl_dict),
        level=DEBUG)

    check_call(["sysctl", "-p", sysctl_file])
