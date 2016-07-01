#!/usr/bin/python
#
# Copyright 2016 Canonical Ltd
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

import traceback

from charmhelpers.contrib.openstack.utils import (
    git_install_requested,
)

from charmhelpers.core.hookenv import (
    action_set,
    action_fail,
    config,
)

from hooks.glance_utils import (
    git_install,
)

from hooks.glance_relations import (
    config_changed,
)


def git_reinstall():
    """Reinstall from source and restart services.

    If the openstack-origin-git config option was used to install openstack
    from source git repositories, then this action can be used to reinstall
    from updated git repositories, followed by a restart of services."""
    if not git_install_requested():
        action_fail('openstack-origin-git is not configured')
        return

    try:
        git_install(config('openstack-origin-git'))
        config_changed()
    except:
        action_set({'traceback': traceback.format_exc()})
        action_fail('git-reinstall resulted in an unexpected error')


if __name__ == '__main__':
    git_reinstall()
