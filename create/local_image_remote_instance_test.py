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
"""Tests for LocalImageRemoteInstance."""

import unittest

from unittest import mock

from acloud.create import avd_spec
from acloud.create import create
from acloud.create import create_common
from acloud.internal import constants
from acloud.internal.lib import driver_test_lib
from acloud.internal.lib import utils
from acloud.public.actions import common_operations
from acloud.public.actions import remote_instance_cf_device_factory
from acloud.public.actions import remote_instance_fvp_device_factory

class LocalImageRemoteInstanceTest(driver_test_lib.BaseDriverTest):
    """Test LocalImageRemoteInstance method."""

    # pylint: disable=no-member
    def testRun(self):
        """Test Create AVD of cuttlefish local image remote instance."""
        args = mock.MagicMock()
        args.skip_pre_run_check = True
        spec = mock.MagicMock()
        spec.avd_type = constants.TYPE_CF
        spec.instance_type = constants.INSTANCE_TYPE_REMOTE
        spec.image_source = constants.IMAGE_SRC_LOCAL
        spec.connect_vnc = False
        spec.connect_webrtc = True
        self.Patch(avd_spec, "AVDSpec", return_value=spec)
        self.Patch(remote_instance_cf_device_factory,
                   "RemoteInstanceDeviceFactory")
        self.Patch(create_common, "GetCvdHostPackage")
        self.Patch(common_operations, "CreateDevices")
        self.Patch(utils, "LaunchBrowserFromReport")
        # cuttfish
        create.Run(args)
        remote_instance_cf_device_factory.RemoteInstanceDeviceFactory.assert_called_once()
        common_operations.CreateDevices.assert_called_once()
        utils.LaunchBrowserFromReport.assert_called_once()
        common_operations.CreateDevices.reset_mock()

        # fvp
        spec.avd_type = constants.TYPE_FVP
        self.Patch(avd_spec, "AVDSpec", return_value=spec)
        self.Patch(remote_instance_fvp_device_factory,
                   "RemoteInstanceDeviceFactory")
        create.Run(args)
        remote_instance_fvp_device_factory.RemoteInstanceDeviceFactory.assert_called_once()
        common_operations.CreateDevices.assert_called_once()

        spec.connect_vnc = True
        spec.connect_webrtc = False
        self.Patch(avd_spec, "AVDSpec", return_value=spec)
        self.Patch(utils, "LaunchVNCFromReport")
        create.Run(args)
        utils.LaunchVNCFromReport.assert_called_once()


if __name__ == "__main__":
    unittest.main()
