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

import yaml
from charmhelpers.core import fstab
from charmhelpers.core import sysctl
from charmhelpers.core.host import (
    add_group,
    add_user_to_group,
    fstab_mount,
    mkdir,
)
from charmhelpers.core.strutils import bytes_from_string
from subprocess import check_output


def hugepage_support(user, group='hugetlb', nr_hugepages=256,
                     max_map_count=65536, mnt_point='/run/hugepages/kvm',
                     pagesize='2MB', mount=True, set_shmmax=False):
    """Enable hugepages on system.

    Args:
    user (str)  -- Username to allow access to hugepages to
    group (str) -- Group name to own hugepages
    nr_hugepages (int) -- Number of pages to reserve
    max_map_count (int) -- Number of Virtual Memory Areas a process can own
    mnt_point (str) -- Directory to mount hugepages on
    pagesize (str) -- Size of hugepages
    mount (bool) -- Whether to Mount hugepages
    """
    group_info = add_group(group)
    gid = group_info.gr_gid
    add_user_to_group(user, group)
    if max_map_count < 2 * nr_hugepages:
        max_map_count = 2 * nr_hugepages
    sysctl_settings = {
        'vm.nr_hugepages': nr_hugepages,
        'vm.max_map_count': max_map_count,
        'vm.hugetlb_shm_group': gid,
    }
    if set_shmmax:
        shmmax_current = int(check_output(['sysctl', '-n', 'kernel.shmmax']))
        shmmax_minsize = bytes_from_string(pagesize) * nr_hugepages
        if shmmax_minsize > shmmax_current:
            sysctl_settings['kernel.shmmax'] = shmmax_minsize
    sysctl.create(yaml.dump(sysctl_settings), '/etc/sysctl.d/10-hugepage.conf')
    mkdir(mnt_point, owner='root', group='root', perms=0o755, force=False)
    lfstab = fstab.Fstab()
    fstab_entry = lfstab.get_entry_by_attr('mountpoint', mnt_point)
    if fstab_entry:
        lfstab.remove_entry(fstab_entry)
    entry = lfstab.Entry('nodev', mnt_point, 'hugetlbfs',
                         'mode=1770,gid={},pagesize={}'.format(gid, pagesize), 0, 0)
    lfstab.add_entry(entry)
    if mount:
        fstab_mount(mnt_point)
