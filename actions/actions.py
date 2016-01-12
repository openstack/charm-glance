#!/usr/bin/python

import sys
import os

from charmhelpers.core.host import service_pause, service_resume
from charmhelpers.core.hookenv import action_fail
from charmhelpers.core.unitdata import HookData, kv

from hooks.glance_utils import services, assess_status
from hooks.glance_relations import CONFIGS


def pause(args):
    """Pause all the Glance services.

    @raises Exception if any services fail to stop
    """
    for service in services():
        stopped = service_pause(service)
        if not stopped:
            raise Exception("{} didn't stop cleanly.".format(service))
    with HookData()():
        kv().set('unit-paused', True)
    assess_status(CONFIGS)


def resume(args):
    """Resume all the Glance services.

    @raises Exception if any services fail to start
    """
    for service in services():
        started = service_resume(service)
        if not started:
            raise Exception("{} didn't start cleanly.".format(service))
    with HookData()():
        kv().set('unit-paused', False)
    assess_status(CONFIGS)


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
