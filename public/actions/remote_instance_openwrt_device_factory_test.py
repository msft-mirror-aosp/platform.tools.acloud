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
"""Tests for remote_instance_openwrt_device_factory."""

import subprocess
import unittest

from unittest import mock

from acloud import errors
from acloud.create import avd_spec
from acloud.internal import constants
from acloud.internal.lib import android_build_client
from acloud.internal.lib import auth
from acloud.internal.lib import cvd_compute_client_multi_stage
from acloud.internal.lib import driver_test_lib
from acloud.internal.lib import gcompute_client
from acloud.internal.lib import ssh
from acloud.list import list as list_instances
from acloud.public.actions import remote_instance_openwrt_device_factory


class RemoteInstanceOpenwrtDeviceFactoryTest(driver_test_lib.BaseDriverTest):
    """Test RemoteInstanceOpenwrtDeviceFactory"""

    def setUp(self):
        """Set up the test."""
        super().setUp()
        self.Patch(gcompute_client.ComputeClient, "GetInstanceIP",
                   return_value=ssh.IP(ip="fake_ip"))
        self.Patch(auth, "CreateCredentials", return_value=mock.MagicMock())
        self.Patch(android_build_client.AndroidBuildClient, "InitResourceHandle")
        self.Patch(cvd_compute_client_multi_stage.CvdComputeClient, "InitResourceHandle")
        self.Patch(list_instances, "GetInstancesFromInstanceNames", return_value=mock.MagicMock())
        self.Patch(list_instances, "ChooseOneRemoteInstance", return_value=mock.MagicMock())

        args = mock.MagicMock()
        args.config_file = ""
        args.avd_type = constants.TYPE_CF
        args.flavor = "phone"
        args.local_image = None
        args.build_id = "123"
        args.build_target = "fake_target"
        args.launch_args = None
        args.adb_port = None
        self.avd_spec = avd_spec.AVDSpec(args)
        self.instance = "fake_instance"
        self.openwrt_factory = remote_instance_openwrt_device_factory.OpenWrtDeviceFactory(
            self.avd_spec, self.instance)

    @mock.patch.object(remote_instance_openwrt_device_factory.OpenWrtDeviceFactory,
                       "_InstallPackages")
    @mock.patch.object(remote_instance_openwrt_device_factory.OpenWrtDeviceFactory,
                       "_BuildOpenWrtImage")
    @mock.patch.object(remote_instance_openwrt_device_factory.OpenWrtDeviceFactory,
                       "_LaunchOpenWrt")
    @mock.patch.object(remote_instance_openwrt_device_factory.OpenWrtDeviceFactory,
                       "_BootOpenWrt")
    def testCreateDevice(self, mock_boot, mock_launch, mock_build, mock_install):
        """Test CreateDevice."""
        self.openwrt_factory.CreateDevice()
        mock_install.assert_called_once()
        mock_build.assert_called_once()
        mock_launch.assert_called_once()
        mock_boot.assert_called_once()

    # pylint: disable=protected-access
    @mock.patch.object(ssh.Ssh, "Run")
    def testInstallPackages(self, mock_ssh):
        """Test InstallPackages."""
        self.openwrt_factory._InstallPackages()
        mock_ssh.assert_called_once()

    # pylint: disable=protected-access
    @mock.patch.object(ssh.Ssh, "Run")
    def testBuildOpenWrtImage(self, mock_ssh):
        """Test BuildOpenWrtImage."""
        self.openwrt_factory._BuildOpenWrtImage()
        mock_ssh.assert_called_once()

    # pylint: disable=protected-access
    @mock.patch.object(ssh.Ssh, "Run")
    def testLaunchOpenWrt(self, mock_ssh):
        """Test LaunchOpenWrt."""
        self.openwrt_factory._LaunchOpenWrt()
        mock_ssh.assert_called_once()

    def testOpenScreenSection(self):
        """Test OpenScreenSection."""
        self.Patch(ssh.Ssh, "Run",
                   side_effect=subprocess.CalledProcessError(None, "Command error."))
        with self.assertRaises(errors.CheckPathError):
            self.openwrt_factory._OpenScreenSection()

    # pylint: disable=protected-access
    def testGetFdtAddrEnv(self):
        """Test GetFdtAddrEnv."""
        self.Patch(ssh.Ssh, "Run")
        self.Patch(ssh.Ssh, "GetCmdOutput", return_value="fdtcontroladdr=12345")
        expected = "12345"
        self.assertEqual(expected, self.openwrt_factory._GetFdtAddrEnv())

        # Test "fdtcontroladdr" not in environment.
        self.Patch(ssh.Ssh, "GetCmdOutput", return_value="no_env")
        expected = None
        self.assertEqual(expected, self.openwrt_factory._GetFdtAddrEnv())

    # pylint: disable=protected-access
    @mock.patch.object(ssh.Ssh, "Run")
    @mock.patch.object(remote_instance_openwrt_device_factory.OpenWrtDeviceFactory,
                       "_OpenScreenSection")
    def testBootOpenWrt(self, mock_open, mock_ssh):
        """Test BootOpenWrt."""
        self.Patch(remote_instance_openwrt_device_factory.OpenWrtDeviceFactory,
                   "_GetFdtAddrEnv", return_value="12345")
        self.openwrt_factory._BootOpenWrt()
        mock_open.assert_called_once()
        ssh_cmd_1 = r"screen -r -X stuff 'env\ default\ -f\ -a\ -^M'"
        ssh_cmd_2 = r"screen -r -X stuff 'setenv\ fdt_addr_r\ 12345^M\ boot^M'"
        mock_ssh.assert_has_calls([mock.call(ssh_cmd_1), mock.call(ssh_cmd_2)])


if __name__ == '__main__':
    unittest.main()
