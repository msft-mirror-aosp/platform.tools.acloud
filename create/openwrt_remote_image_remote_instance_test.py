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
"""Tests for OpenWrtRemoteImageRemoteInstance."""

import unittest

from unittest import mock

from acloud.create import openwrt_remote_image_remote_instance
from acloud.internal.lib import driver_test_lib
from acloud.public.actions import common_operations
from acloud.public.actions import remote_instance_cf_device_factory


class RemoteImageRemoteInstanceTest(driver_test_lib.BaseDriverTest):
    """Test OpenWrtRemoteImageRemoteInstance method."""

    def setUp(self):
        """Initialize new OpenWrtRemoteImageRemoteInstance."""
        super().setUp()
        self.openwrt_instance = (openwrt_remote_image_remote_instance.
                                 OpenWrtRemoteImageRemoteInstance())

    # pylint: disable=protected-access
    @mock.patch.object(common_operations, "CreateDevices")
    @mock.patch.object(remote_instance_cf_device_factory,
                       "RemoteInstanceDeviceFactory")
    def testCreateAVD(self, mock_factory, mock_create_device):
        """test CreateAVD."""
        avd_spec = mock.Mock()
        self.openwrt_instance._CreateAVD(avd_spec, no_prompts=True)
        mock_factory.assert_called_once()
        mock_create_device.assert_called_once()


if __name__ == '__main__':
    unittest.main()
