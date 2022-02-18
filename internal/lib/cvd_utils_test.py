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

"""Tests for cvd_utils."""

import unittest
from unittest import mock

from acloud.internal.lib import cvd_utils


class CvdUtilsTest(unittest.TestCase):
    """Test the functions in cvd_utils."""

    @staticmethod
    def testUploadImageZip():
        """Test UploadImageZip."""
        mock_ssh = mock.Mock()
        cvd_utils.UploadImageZip(mock_ssh, "/mock/img.zip")
        mock_ssh.Run.assert_called_with("/usr/bin/install_zip.sh . < "
                                        "/mock/img.zip")

    @staticmethod
    @mock.patch("acloud.internal.lib.cvd_utils.glob")
    @mock.patch("acloud.internal.lib.cvd_utils.ssh.ShellCmdWithRetry")
    def testUploadImageDir(mock_shell, mock_glob):
        """Test UploadImageDir."""
        mock_ssh = mock.Mock()
        mock_ssh.GetBaseCmd.return_value = "/mock/ssh"
        expected_cmd = ("tar -cf - --lzop -S -C /mock/image_dir "
                        "super.img bootloader kernel android-info.txt | "
                        "/mock/ssh -- tar -xf - --lzop -S")

        # Test with required_images file.
        mock_open = mock.mock_open(read_data="super.img\nbootloader\nkernel")
        with mock.patch("acloud.internal.lib.cvd_utils.open", mock_open):
            cvd_utils.UploadImageDir(mock_ssh, "/mock/image_dir")
        mock_open.assert_called_with("/mock/image_dir/required_images", "r",
                                     encoding="utf-8")
        mock_glob.glob.assert_not_called()
        mock_shell.assert_called_with(expected_cmd)

        # Test with glob.
        mock_ssh.reset_mock()
        mock_shell.reset_mock()
        mock_glob.glob.side_effect = (
            lambda path: [path.replace("*", "super")])
        with mock.patch("acloud.internal.lib.cvd_utils.open",
                        side_effect=IOError("file does not exist")):
            cvd_utils.UploadImageDir(mock_ssh, "/mock/image_dir")
        mock_glob.glob.assert_called()
        mock_shell.assert_called_with(expected_cmd)

    @staticmethod
    def testUploadCvdHostPackage():
        """Test UploadCvdHostPackage."""
        mock_ssh = mock.Mock()
        cvd_utils.UploadCvdHostPackage(mock_ssh, "/mock/cvd.tar.gz")
        mock_ssh.Run.assert_called_with("tar -x -z -f - < /mock/cvd.tar.gz")

    def testGetRemoteBuildInfoDict(self):
        """Test GetRemoteBuildInfoDict."""
        remote_image = {
            "branch": "aosp-android-12-gsi",
            "build_id": "100000",
            "build_target": "aosp_cf_x86_64_phone-userdebug"}
        mock_avd_spec = mock.Mock(
            spec=[],
            remote_image=remote_image,
            kernel_build_info={"build_target": "kernel"},
            system_build_info={},
            bootloader_build_info={})
        self.assertEqual(remote_image,
                         cvd_utils.GetRemoteBuildInfoDict(mock_avd_spec))

        kernel_build_info = {
            "branch": "aosp_kernel-common-android12-5.10",
            "build_id": "200000",
            "build_target": "kernel_virt_x86_64"}
        system_build_info = {
            "branch": "aosp-android-12-gsi",
            "build_id": "300000",
            "build_target": "aosp_x86_64-userdebug"}
        bootloader_build_info = {
            "branch": "aosp_u-boot-mainline",
            "build_id": "400000",
            "build_target": "u-boot_crosvm_x86_64"}
        all_build_info = {
            "kernel_branch": "aosp_kernel-common-android12-5.10",
            "kernel_build_id": "200000",
            "kernel_build_target": "kernel_virt_x86_64",
            "system_branch": "aosp-android-12-gsi",
            "system_build_id": "300000",
            "system_build_target": "aosp_x86_64-userdebug",
            "bootloader_branch": "aosp_u-boot-mainline",
            "bootloader_build_id": "400000",
            "bootloader_build_target": "u-boot_crosvm_x86_64"}
        all_build_info.update(remote_image)
        mock_avd_spec = mock.Mock(
            spec=[],
            remote_image=remote_image,
            kernel_build_info=kernel_build_info,
            system_build_info=system_build_info,
            bootloader_build_info=bootloader_build_info)
        self.assertEqual(all_build_info,
                         cvd_utils.GetRemoteBuildInfoDict(mock_avd_spec))


if __name__ == "__main__":
    unittest.main()
