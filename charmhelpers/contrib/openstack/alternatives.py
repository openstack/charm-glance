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

''' Helper for managing alternatives for file conflict resolution '''

import subprocess
import shutil
import os


def install_alternative(name, target, source, priority=50):
    ''' Install alternative configuration '''
    if (os.path.exists(target) and not os.path.islink(target)):
        # Move existing file/directory away before installing
        shutil.move(target, '{}.bak'.format(target))
    cmd = [
        'update-alternatives', '--force', '--install',
        target, name, source, str(priority)
    ]
    subprocess.check_call(cmd)
