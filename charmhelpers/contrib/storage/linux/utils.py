from os import stat
from stat import S_ISBLK

from subprocess import (
    check_call
)


def is_block_device(path):
    '''
    Confirm device at path is a valid block device node.

    :returns: boolean: True if path is a block device, False if not.
    '''
    return S_ISBLK(stat(path).st_mode)


def zap_disk(block_device):
    '''
    Clear a block device of partition table. Relies on sgdisk, which is
    installed as pat of the 'gdisk' package in Ubuntu.

    :param block_device: str: Full path of block device to clean.
    '''
    check_call(['sgdisk', '--zap-all', block_device])
