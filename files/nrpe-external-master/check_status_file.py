#!/usr/bin/python

#                                       m
#  mmmm   m   m  mmmm   mmmm    mmm   mm#mm
#  #" "#  #   #  #" "#  #" "#  #"  #    #
#  #   #  #   #  #   #  #   #  #""""    #
#  ##m#"  "mm"#  ##m#"  ##m#"  "#mm"    "mm
#  #             #      #
#  "             "      "
# This file is managed by puppet.  Do not make local changes.

#
# Copyright 2014 Canonical Ltd.
#
# Author: Jacek Nykis <jacek.nykis@canonical.com>
#

import re
import nagios_plugin


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(
        description='Read file and return nagios status based on its content',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-f', '--status-file', required=True,
                        help='Status file path')
    parser.add_argument('-c', '--critical-text', default='CRITICAL',
                        help='String indicating critical status')
    parser.add_argument('-w', '--warning-text', default='WARNING',
                        help='String indicating warning status')
    parser.add_argument('-o', '--ok-text', default='OK',
                        help='String indicating OK status')
    parser.add_argument('-u', '--unknown-text', default='UNKNOWN',
                        help='String indicating unknown status')
    return parser.parse_args()


def check_status(args):
    nagios_plugin.check_file_freshness(args.status_file, 43200)

    with open(args.status_file, "r") as f:
        content = [l.strip() for l in f.readlines()]

    for line in content:
        if re.search(args.critical_text, line):
            raise nagios_plugin.CriticalError(line)
        elif re.search(args.warning_text, line):
            raise nagios_plugin.WarnError(line)
        elif re.search(args.unknown_text, line):
            raise nagios_plugin.UnknownError(line)
        else:
            print line


if __name__ == '__main__':
    args = parse_args()
    nagios_plugin.try_check(check_status, args)
