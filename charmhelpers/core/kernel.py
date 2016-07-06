#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2014-2015 Canonical Limited.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
