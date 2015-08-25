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

__author__ = 'Jorge Niedbalski <niedbalski@ubuntu.com>'

import os
import subprocess


def sed(filename, before, after, flags='g'):
    """
    Search and replaces the given pattern on filename.

    :param filename: relative or absolute file path.
    :param before: expression to be replaced (see 'man sed')
    :param after: expression to replace with (see 'man sed')
    :param flags: sed-compatible regex flags in example, to make
    the  search and replace case insensitive, specify ``flags="i"``.
    The ``g`` flag is always specified regardless, so you do not
    need to remember to include it when overriding this parameter.
    :returns: If the sed command exit code was zero then return,
    otherwise raise CalledProcessError.
    """
    expression = r's/{0}/{1}/{2}'.format(before,
                                         after, flags)

    return subprocess.check_call(["sed", "-i", "-r", "-e",
                                  expression,
                                  os.path.expanduser(filename)])
