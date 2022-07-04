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

import os
import subprocess
import tempfile
import unittest
from unittest import mock

from acloud import errors
from acloud.internal import constants
from acloud.internal.lib import cvd_utils


class CvdUtilsTest(unittest.TestCase):
    """Test the functions in cvd_utils."""

    @staticmethod
    def _CreateFile(path, data=b""):
        """Create and write binary data to a file."""
        with open(path, "wb") as file_obj:
            file_obj.write(data)

    def testGetAdbPorts(self):
        """Test GetAdbPorts."""
        self.assertEqual([6520], cvd_utils.GetAdbPorts(None, None))
        self.assertEqual([6520], cvd_utils.GetAdbPorts(1, 1))
        self.assertEqual([6521, 6522], cvd_utils.GetAdbPorts(2, 2))

    def testGetVncPorts(self):
        """Test GetVncPorts."""
        self.assertEqual([6444], cvd_utils.GetVncPorts(None, None))
        self.assertEqual([6444], cvd_utils.GetVncPorts(1, 1))
        self.assertEqual([6445, 6446], cvd_utils.GetVncPorts(2, 2))

    @mock.patch("acloud.internal.lib.cvd_utils.os.path.isdir")
    def testFindLocalLogs(self, mock_isdir):
        """Test FindLocalLogs."""
        mock_isdir.return_value = False
        expected_logs = [
            {
                "path": "/dir/launcher.log",
                "type": constants.LOG_TYPE_CUTTLEFISH_LOG
            },
            {"path": "/dir/kernel.log", "type": constants.LOG_TYPE_KERNEL_LOG},
            {"path": "/dir/logcat", "type": constants.LOG_TYPE_LOGCAT},
        ]
        self.assertEqual(expected_logs, cvd_utils.FindLocalLogs("/dir", 1))

        expected_path = "/dir/instances/cvd-2/logs"
        mock_isdir.side_effect = lambda path: path == expected_path
        expected_logs = [
            {
                "path": "/dir/instances/cvd-2/logs/launcher.log",
                "type": constants.LOG_TYPE_CUTTLEFISH_LOG
            },
            {
                "path": "/dir/instances/cvd-2/logs/kernel.log",
                "type": constants.LOG_TYPE_KERNEL_LOG
            },
            {
                "path": "/dir/instances/cvd-2/logs/logcat",
                "type": constants.LOG_TYPE_LOGCAT
            },
        ]
        self.assertEqual(expected_logs, cvd_utils.FindLocalLogs("/dir", 2))

    @staticmethod
    @mock.patch("acloud.internal.lib.cvd_utils.os.path.isdir",
                return_value=False)
    def testUploadImageZip(_mock_isdir):
        """Test UploadArtifacts with image zip."""
        mock_ssh = mock.Mock()
        cvd_utils.UploadArtifacts(mock_ssh, "/mock/img.zip", "/mock/cvd.tgz")
        mock_ssh.Run.assert_any_call("/usr/bin/install_zip.sh . < "
                                     "/mock/img.zip")
        mock_ssh.Run.assert_any_call("tar -x -z -f - < /mock/cvd.tgz")

    @staticmethod
    @mock.patch("acloud.internal.lib.cvd_utils.glob")
    @mock.patch("acloud.internal.lib.cvd_utils.os.path.isdir",
                return_value=True)
    @mock.patch("acloud.internal.lib.cvd_utils.ssh.ShellCmdWithRetry")
    def testUploadImageDir(mock_shell, _mock_isdir, mock_glob):
        """Test UploadArtifacts with image directory."""
        mock_ssh = mock.Mock()
        mock_ssh.GetBaseCmd.return_value = "/mock/ssh"
        expected_shell_cmd = ("tar -cf - --lzop -S -C /mock/dir "
                              "super.img bootloader kernel android-info.txt | "
                              "/mock/ssh -- tar -xf - --lzop -S")
        expected_ssh_cmd = "tar -x -z -f - < /mock/cvd.tgz"

        # Test with required_images file.
        mock_open = mock.mock_open(read_data="super.img\nbootloader\nkernel")
        with mock.patch("acloud.internal.lib.cvd_utils.open", mock_open):
            cvd_utils.UploadArtifacts(mock_ssh, "/mock/dir", "/mock/cvd.tgz")
        mock_open.assert_called_with("/mock/dir/required_images", "r",
                                     encoding="utf-8")
        mock_glob.glob.assert_not_called()
        mock_shell.assert_called_with(expected_shell_cmd)
        mock_ssh.Run.assert_called_with(expected_ssh_cmd)

        # Test with glob.
        mock_ssh.reset_mock()
        mock_shell.reset_mock()
        mock_glob.glob.side_effect = (
            lambda path: [path.replace("*", "super")])
        with mock.patch("acloud.internal.lib.cvd_utils.open",
                        side_effect=IOError("file does not exist")):
            cvd_utils.UploadArtifacts(mock_ssh, "/mock/dir", "/mock/cvd.tgz")
        mock_glob.glob.assert_called()
        mock_shell.assert_called_with(expected_shell_cmd)
        mock_ssh.Run.assert_called_with(expected_ssh_cmd)

    def testUploadBootImages(self):
        """Test FindBootImages and UploadExtraImages."""
        mock_ssh = mock.Mock()
        with tempfile.TemporaryDirectory(prefix="cvd_utils") as image_dir:
            boot_image_path = os.path.join(image_dir, "boot.img")
            self._CreateFile(boot_image_path, b"ANDROID!test")
            self._CreateFile(os.path.join(image_dir, "vendor_boot.img"))

            mock_avd_spec = mock.Mock(local_kernel_image=boot_image_path)
            args = cvd_utils.UploadExtraImages(mock_ssh, mock_avd_spec)
            self.assertEqual(["-boot_image", "acloud_cf/boot.img"], args)
            mock_ssh.Run.assert_called_once_with("mkdir -p acloud_cf")
            mock_ssh.ScpPushFile.assert_called_once()

            mock_ssh.reset_mock()
            mock_avd_spec.local_kernel_image = image_dir
            args = cvd_utils.UploadExtraImages(mock_ssh, mock_avd_spec)
            self.assertEqual(
                ["-boot_image", "acloud_cf/boot.img",
                 "-vendor_boot_image", "acloud_cf/vendor_boot.img"],
                args)
            mock_ssh.Run.assert_called_once()
            self.assertEqual(2, mock_ssh.ScpPushFile.call_count)

    def testUploadKernelImages(self):
        """Test FindKernelImages and UploadExtraImages."""
        mock_ssh = mock.Mock()
        with tempfile.TemporaryDirectory(prefix="cvd_utils") as image_dir:
            kernel_image_path = os.path.join(image_dir, "Image")
            self._CreateFile(kernel_image_path)
            self._CreateFile(os.path.join(image_dir, "initramfs.img"))

            mock_avd_spec = mock.Mock(local_kernel_image=kernel_image_path)
            with self.assertRaises(errors.GetLocalImageError):
                cvd_utils.UploadExtraImages(mock_ssh, mock_avd_spec)

            mock_ssh.reset_mock()
            mock_avd_spec.local_kernel_image = image_dir
            args = cvd_utils.UploadExtraImages(mock_ssh, mock_avd_spec)
            self.assertEqual(
                ["-kernel_path", "acloud_cf/kernel",
                 "-initramfs_path", "acloud_cf/initramfs.img"],
                args)
            mock_ssh.Run.assert_called_once()
            self.assertEqual(2, mock_ssh.ScpPushFile.call_count)

    def testCleanUpRemoteCvd(self):
        """Test CleanUpRemoteCvd."""
        mock_ssh = mock.Mock()
        cvd_utils.CleanUpRemoteCvd(mock_ssh, raise_error=True)
        mock_ssh.Run.assert_any_call("./bin/stop_cvd")
        mock_ssh.Run.assert_any_call("'rm -rf ./*'")

        mock_ssh.reset_mock()
        mock_ssh.Run.side_effect = [
            subprocess.CalledProcessError(cmd="should raise", returncode=1)]
        with self.assertRaises(subprocess.CalledProcessError):
            cvd_utils.CleanUpRemoteCvd(mock_ssh, raise_error=True)

        mock_ssh.reset_mock()
        mock_ssh.Run.side_effect = [
            subprocess.CalledProcessError(cmd="should ignore", returncode=1),
            None]
        cvd_utils.CleanUpRemoteCvd(mock_ssh, raise_error=False)
        mock_ssh.Run.assert_any_call("./bin/stop_cvd", retry=0)
        mock_ssh.Run.assert_any_call("'rm -rf ./*'")

    @mock.patch("acloud.internal.lib.cvd_utils.utils")
    def testFindRemoteLogs(self, mock_utils):
        """Test FindRemoteLogs with the runtime directories in Android 12."""
        mock_ssh = mock.Mock()
        mock_utils.FindRemoteFiles.return_value = [
            "/kernel.log", "/logcat", "/launcher.log", "/access-kregistry",
            "/cuttlefish_config.json"]

        logs = cvd_utils.FindRemoteLogs(mock_ssh, None, None)
        mock_ssh.Run.assert_called_with("test -d cuttlefish/instances/cvd-1",
                                        retry=0)
        mock_utils.FindRemoteFiles.assert_called_with(
            mock_ssh, ["cuttlefish/instances/cvd-1"])
        expected_logs = [
            {
                "path": "/kernel.log",
                "type": constants.LOG_TYPE_KERNEL_LOG,
                "name": "kernel.log"
            },
            {
                "path": "/logcat",
                "type": constants.LOG_TYPE_LOGCAT,
                "name": "full_gce_logcat"
            },
            {
                "path": "/launcher.log",
                "type": constants.LOG_TYPE_CUTTLEFISH_LOG,
                "name": "launcher.log"
            },
            {
                "path": "/cuttlefish_config.json",
                "type": constants.LOG_TYPE_CUTTLEFISH_LOG,
                "name": "cuttlefish_config.json"
            },
            {
                "path": "cuttlefish/instances/cvd-1/tombstones",
                "type": constants.LOG_TYPE_DIR,
                "name": "tombstones-zip"
            },
        ]
        self.assertEqual(expected_logs, logs)

    @mock.patch("acloud.internal.lib.cvd_utils.utils")
    def testFindRemoteLogsWithLegacyDirs(self, mock_utils):
        """Test FindRemoteLogs with the runtime directories in Android 11."""
        mock_ssh = mock.Mock()
        mock_ssh.Run.side_effect = subprocess.CalledProcessError(
            cmd="test", returncode=1)
        mock_utils.FindRemoteFiles.return_value = [
            "cuttlefish_runtime/kernel.log", "cuttlefish_runtime.4/kernel.log"]

        logs = cvd_utils.FindRemoteLogs(mock_ssh, 3, 2)
        mock_ssh.Run.assert_called_with("test -d cuttlefish/instances/cvd-3",
                                        retry=0)
        mock_utils.FindRemoteFiles.assert_called_with(
            mock_ssh, ["cuttlefish_runtime", "cuttlefish_runtime.4"])
        expected_logs = [
            {
                "path": "cuttlefish_runtime/kernel.log",
                "type": constants.LOG_TYPE_KERNEL_LOG,
                "name": "kernel.log"
            },
            {
                "path": "cuttlefish_runtime.4/kernel.log",
                "type": constants.LOG_TYPE_KERNEL_LOG,
                "name": "kernel.1.log"
            },
            {
                "path": "cuttlefish_runtime/tombstones",
                "type": constants.LOG_TYPE_DIR,
                "name": "tombstones-zip"
            },
            {
                "path": "cuttlefish_runtime.4/tombstones",
                "type": constants.LOG_TYPE_DIR,
                "name": "tombstones-zip.1"
            },
        ]
        self.assertEqual(expected_logs, logs)

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
