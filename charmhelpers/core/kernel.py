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

__author__ = "Jorge Niedbalski <jorge.niedbalski@canonical.com>"

from charmhelpers.core.hookenv import (
    log,
    INFO
)

from subprocess import check_call, check_output
import re


def modprobe(module, persist=True):
    """Load a kernel module and configure for auto-load on reboot."""
    cmd = ['modprobe', module]

    log('Loading kernel module %s' % module, level=INFO)

    check_call(cmd)
    if persist:
        with open('/etc/modules', 'r+') as modules:
            if module not in modules.read():
                modules.write(module)


def rmmod(module, force=False):
    """Remove a module from the linux kernel"""
    cmd = ['rmmod']
    if force:
        cmd.append('-f')
    cmd.append(module)
    log('Removing kernel module %s' % module, level=INFO)
    return check_call(cmd)


def lsmod():
    """Shows what kernel modules are currently loaded"""
    return check_output(['lsmod'],
                        universal_newlines=True)


def is_module_loaded(module):
    """Checks if a kernel module is already loaded"""
    matches = re.findall('^%s[ ]+' % module, lsmod(), re.M)
    return len(matches) > 0


def update_initramfs(version='all'):
    """Updates an initramfs image"""
    return check_call(["update-initramfs", "-k", version, "-u"])
