#!/usr/bin/python

import sys
import os

from charmhelpers.core.hookenv import action_fail

from hooks.glance_utils import (
    pause_unit_helper,
    resume_unit_helper,
    register_configs,
)


def pause(args):
    """Pause all the Glance services.

    @raises Exception if any services fail to stop
    """
    pause_unit_helper(register_configs())


def resume(args):
    """Resume all the Glance services.

    @raises Exception if any services fail to start
    """
    resume_unit_helper(register_configs())


# A dictionary of all the defined actions to callables (which take
# parsed arguments).
ACTIONS = {"pause": pause, "resume": resume}


def main(args):
    action_name = os.path.basename(args[0])
    try:
        action = ACTIONS[action_name]
    except KeyError:
        return "Action %s undefined" % action_name
    else:
        try:
            action(args)
        except Exception as e:
            action_fail(str(e))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
