#!/usr/bin/env python3
#
# Copyright 2022 - The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for RemoteHostClient."""

import unittest

from acloud.internal.lib import driver_test_lib
from acloud.internal.lib import remote_host_client


class RemoteHostClientTest(driver_test_lib.BaseDriverTest):
    """Unit tests for RemoteHostClient."""

    _IP_ADDRESS = "192.0.2.1"

    def testGetInstanceIP(self):
        """Test GetInstanceIP."""
        client = remote_host_client.RemoteHostClient(self._IP_ADDRESS)
        ip_addr = client.GetInstanceIP("name")
        self.assertEqual(ip_addr.external, self._IP_ADDRESS)
        self.assertEqual(ip_addr.internal, self._IP_ADDRESS)


if __name__ == "__main__":
    unittest.main()
