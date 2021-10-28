# Copyright 2020 - The Android Open Source Project
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
"""Tests for create."""

import unittest

from unittest import mock

from acloud import errors
from acloud.create import create_args
from acloud.internal import constants
from acloud.internal.lib import driver_test_lib


def _CreateArgs():
    """set default pass in arguments."""
    mock_args = mock.MagicMock(
        flavor=None,
        num=1,
        adb_port=None,
        hw_property=None,
        stable_cheeps_host_image_name=None,
        stable_cheeps_host_image_project=None,
        username=None,
        password=None,
        cheeps_betty_image=None,
        local_image=None,
        local_kernel_image=None,
        local_system_image=None,
        kernel_branch=None,
        kernel_build_id=None,
        kernel_build_target=None,
        system_branch=None,
        system_build_id=None,
        system_build_target=None,
        local_instance=None,
        remote_host=None,
        host_user=constants.GCE_USER,
        host_ssh_private_key_path=None,
        emulator_build_id=None,
        emulator_build_target=None,
        avd_type=constants.TYPE_CF,
        autoconnect=constants.INS_KEY_VNC)
    return mock_args


# pylint: disable=invalid-name,protected-access
class CreateArgsTest(driver_test_lib.BaseDriverTest):
    """Test create_args functions."""

    def testVerifyArgs(self):
        """test VerifyArgs."""
        mock_args = _CreateArgs()
        # Test args default setting shouldn't raise error.
        self.assertEqual(None, create_args.VerifyArgs(mock_args))

    def testVerifyArgs_Goldfish(self):
        """test goldfish arguments."""
        # emulator_build_id with wrong avd_type.
        mock_args = _CreateArgs()
        mock_args.emulator_build_id = 123456
        self.assertRaises(errors.UnsupportedCreateArgs,
                          create_args.VerifyArgs, mock_args)
        # Valid emulator_build_id.
        mock_args.avd_type = constants.TYPE_GF
        create_args.VerifyArgs(mock_args)
        # emulator_build_target with wrong avd_type.
        mock_args.avd_type = constants.TYPE_CF
        mock_args.emulator_build_id = None
        mock_args.emulator_build_target = "sdk_tools_linux"
        mock_args.remote_host = "192.0.2.2"
        self.assertRaises(errors.UnsupportedCreateArgs,
                          create_args.VerifyArgs, mock_args)
        # emulator_build_target without remote_host.
        mock_args.avd_type = constants.TYPE_GF
        mock_args.emulator_build_target = "sdk_tools_linux"
        mock_args.remote_host = None
        self.assertRaises(errors.UnsupportedCreateArgs,
                          create_args.VerifyArgs, mock_args)
        # system_build_target without remote_host.
        mock_args.emulator_build_target = None
        mock_args.system_build_target = "aosp_x86_64-userdebug"
        mock_args.remote_host = None
        self.assertRaises(errors.UnsupportedCreateArgs,
                          create_args.VerifyArgs, mock_args)
        # Valid build targets.
        mock_args.remote_host = "192.0.2.2"
        mock_args.emulator_build_target = "sdk_tools_linux"
        mock_args.system_build_target = "aosp_x86_64-userdebug"
        mock_args.kernel_build_target = "aosp_x86_64-userdebug"
        create_args.VerifyArgs(mock_args)

    def testVerifyArgs_ConnectWebRTC(self):
        """test VerifyArgs args.autconnect webrtc.

        WebRTC only apply to remote cuttlefish instance

        """
        mock_args = _CreateArgs()
        mock_args.autoconnect = constants.INS_KEY_WEBRTC
        # Test remote instance and avd_type cuttlefish(default)
        # Test args.autoconnect webrtc shouldn't raise error.
        self.assertEqual(None, create_args.VerifyArgs(mock_args))


if __name__ == "__main__":
    unittest.main()
