#!/usr/bin/env python3
#
# Copyright 2021 - The Android Open Source Project
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

"""Unit tests for GoldfishRemoteHostClient."""

import unittest

from acloud.internal.lib import driver_test_lib
from acloud.internal.lib import goldfish_remote_host_client


class GoldfishRemoteHostClientTest(driver_test_lib.BaseDriverTest):
    """Unit tests for GoldfishRemoteHostClient."""

    def testFormatInstanceName(self):
        """Test FormatInstanceName."""
        build_info = {"build_id": "123456",
                      "build_target": "sdk_phone_x86_64-userdebug"}
        instance_name = goldfish_remote_host_client.FormatInstanceName(
            "192.0.2.1", 5444, build_info)
        self.assertEqual(
            "host-192.0.2.1-goldfish-5444-123456-sdk_phone_x86_64-userdebug",
            instance_name)

    def testGetInstanceIP(self):
        """Test GetInstanceIP."""
        client = goldfish_remote_host_client.GoldfishRemoteHostClient()
        ip_addr = client.GetInstanceIP(
            "host-192.0.2.1-goldfish-5444-123456-sdk_phone_x86_64-userdebug")
        self.assertEqual(ip_addr.external, "192.0.2.1")
        self.assertEqual(ip_addr.internal, "192.0.2.1")


if __name__ == "__main__":
    unittest.main()
