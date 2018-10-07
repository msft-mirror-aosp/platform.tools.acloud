#!/usr/bin/env python
#
# Copyright 2018 - The Android Open Source Project
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

"""Tests for acloud.internal.lib.cvd_compute_client."""

import unittest
import mock

from acloud.internal.lib import cvd_compute_client
from acloud.internal.lib import driver_test_lib
from acloud.internal.lib import gcompute_client


class CvdComputeClientTest(driver_test_lib.BaseDriverTest):
    """Test CvdComputeClient."""

    SSH_PUBLIC_KEY_PATH = ""
    INSTANCE = "fake-instance"
    IMAGE = "fake-image"
    IMAGE_PROJECT = "fake-iamge-project"
    MACHINE_TYPE = "fake-machine-type"
    NETWORK = "fake-network"
    ZONE = "fake-zone"
    BRANCH = "fake-branch"
    TARGET = "aosp_cf_x86_phone-userdebug"
    BUILD_ID = "2263051"
    KERNEL_BRANCH = "fake-kernel-branch"
    KERNEL_BUILD_ID = "1234567"
    DPI = 160
    X_RES = 720
    Y_RES = 1280
    METADATA = {"metadata_key": "metadata_value"}
    EXTRA_DATA_DISK_SIZE_GB = 4
    BOOT_DISK_SIZE_GB = 10

    def _GetFakeConfig(self):
        """Create a fake configuration object.

        Returns:
            A fake configuration mock object.
        """
        fake_cfg = mock.MagicMock()
        fake_cfg.ssh_public_key_path = self.SSH_PUBLIC_KEY_PATH
        fake_cfg.machine_type = self.MACHINE_TYPE
        fake_cfg.network = self.NETWORK
        fake_cfg.zone = self.ZONE
        fake_cfg.resolution = "{x}x{y}x32x{dpi}".format(
            x=self.X_RES, y=self.Y_RES, dpi=self.DPI)
        fake_cfg.metadata_variable = self.METADATA
        fake_cfg.extra_data_disk_size_gb = self.EXTRA_DATA_DISK_SIZE_GB
        return fake_cfg

    def setUp(self):
        """Set up the test."""
        super(CvdComputeClientTest, self).setUp()
        self.Patch(cvd_compute_client.CvdComputeClient, "InitResourceHandle")
        self.cvd_compute_client = cvd_compute_client.CvdComputeClient(
            self._GetFakeConfig(), mock.MagicMock())

    @mock.patch.object(gcompute_client.ComputeClient, "CompareMachineSize",
                       return_value=1)
    @mock.patch.object(gcompute_client.ComputeClient, "GetImage",
                       return_value={"diskSizeGb": 10})
    @mock.patch.object(gcompute_client.ComputeClient, "CreateInstance")
    @mock.patch.object(cvd_compute_client.CvdComputeClient, "_GetDiskArgs",
                       return_value=[{"fake_arg": "fake_value"}])
    @mock.patch("getpass.getuser", return_value="fake_user")
    def testCreateInstance(self, _get_user, _get_disk_args, mock_create,
                           _get_image, _compare_machine_size):
        """Test CreateInstance."""
        expected_metadata = {
            "cvd_01_dpi": str(self.DPI),
            "cvd_01_fetch_android_build_target": self.TARGET,
            "cvd_01_fetch_android_bid": "{branch}/{build_id}".format(
                branch=self.BRANCH, build_id=self.BUILD_ID),
            "cvd_01_fetch_kernel_bid": "{branch}/{build_id}".format(
                branch=self.KERNEL_BRANCH, build_id=self.KERNEL_BUILD_ID),
            "cvd_01_launch": "1",
            "cvd_01_x_res": str(self.X_RES),
            "cvd_01_y_res": str(self.Y_RES),
            "user": "fake_user",
            "cvd_01_data_policy":
                self.cvd_compute_client.DATA_POLICY_CREATE_IF_MISSING,
            "cvd_01_blank_data_disk_size": str(self.EXTRA_DATA_DISK_SIZE_GB * 1024),
        }
        expected_metadata.update(self.METADATA)
        expected_disk_args = [{"fake_arg": "fake_value"}]

        self.cvd_compute_client.CreateInstance(
            self.INSTANCE, self.IMAGE, self.IMAGE_PROJECT, self.TARGET, self.BRANCH,
            self.BUILD_ID, self.KERNEL_BRANCH, self.KERNEL_BUILD_ID,
            self.EXTRA_DATA_DISK_SIZE_GB)
        # gcompute_client.ComputeClient.CreateInstance.assert_called_with(
        mock_create.assert_called_with(
            self.cvd_compute_client,
            instance=self.INSTANCE,
            image_name=self.IMAGE,
            image_project=self.IMAGE_PROJECT,
            disk_args=expected_disk_args,
            metadata=expected_metadata,
            machine_type=self.MACHINE_TYPE,
            network=self.NETWORK,
            zone=self.ZONE)


if __name__ == "__main__":
    unittest.main()
