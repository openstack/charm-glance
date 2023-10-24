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

import sys
from unittest.mock import patch

sys.path.append('actions')
sys.path.append('hooks')
sys.path.append('unit_tests')

# Patch out lsb_release() and get_platform() as unit tests should be fully
# insulated from the underlying platform.  Unit tests assume that the system is
# ubuntu jammy.
patch(
    'charmhelpers.osplatform.get_platform', return_value='ubuntu'
).start()
patch(
    'charmhelpers.core.host.lsb_release',
    return_value={
        'DISTRIB_CODENAME': 'jammy'
    }).start()
