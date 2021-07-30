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

"""Unit tests for RemoteHostGoldfishDeviceFactory."""

import os
import tempfile
import unittest
import zipfile

from unittest import mock

from acloud.internal import constants
from acloud.internal.lib import driver_test_lib
from acloud.public.actions import remote_host_gf_device_factory as gf_factory


class RemoteHostGoldfishDeviceFactoryTest(driver_test_lib.BaseDriverTest):
    """Unit tests for RemoteHostGoldfishDeviceFactory."""

    _EMULATOR_INFO = "require version-emulator=111111\n"
    _X86_64_BUILD_INFO = {
        constants.BUILD_ID: "123456",
        constants.BUILD_TARGET: "sdk_x86_64-sdk",
    }
    _X86_64_INSTANCE_NAME = (
        "host-192.0.2.1-goldfish-5554-123456-sdk_x86_64-sdk")
    _ARM64_BUILD_INFO = {
        constants.BUILD_ID: "123456",
        constants.BUILD_TARGET: "sdk_arm64-sdk",
    }
    _ARM64_INSTANCE_NAME = (
        "host-192.0.2.1-goldfish-5554-123456-sdk_arm64-sdk")
    _CFG_ATTRS = {
        "ssh_private_key_path": "cfg_key_path",
        "extra_args_ssh_tunnel": "extra args",
        "emulator_build_target": "sdk_tools_linux",
    }
    _AVD_SPEC_ATTRS = {
        "cfg": None,
        "remote_image": _X86_64_BUILD_INFO,
        "image_download_dir": None,
        "host_user": "user",
        "remote_host": "192.0.2.1",
        "host_ssh_private_key_path": None,
        "emulator_build_id": None,
        "emulator_build_target": None,
        "boot_timeout_secs": None,
        "gpu": "auto",
    }
    _SSH_COMMAND = (
        "'export ANDROID_PRODUCT_OUT=~/acloud_gf/image/x86_64 "
        "ANDROID_TMP=~/acloud_gf/instance "
        "ANDROID_BUILD_TOP=~/acloud_gf/instance ; "
        "nohup acloud_gf/emulator/x86_64/emulator -verbose "
        "-show-kernel -read-only -ports 5554,5555 -no-window "
        "-logcat-output acloud_gf/instance/logcat.txt -gpu auto "
        "1> acloud_gf/instance/stdout.txt "
        "2> acloud_gf/instance/stderr.txt &'"
    )

    def setUp(self):
        super().setUp()
        self._mock_ssh = mock.Mock()
        self.Patch(gf_factory.ssh, "Ssh", return_value=self._mock_ssh)
        self.Patch(gf_factory.goldfish_remote_host_client,
                   "GoldfishRemoteHostClient")
        self.Patch(gf_factory.auth, "CreateCredentials")
        # Android build client.
        self._mock_android_build_client = mock.Mock()
        self._mock_android_build_client.DownloadArtifact.side_effect = (
            self._MockDownloadArtifact)
        self.Patch(gf_factory.android_build_client, "AndroidBuildClient",
                   return_value=self._mock_android_build_client)
        # AVD spec.
        mock_cfg = mock.Mock(spec=list(self._CFG_ATTRS.keys()),
                             **self._CFG_ATTRS)
        self._mock_avd_spec = mock.Mock(spec=list(self._AVD_SPEC_ATTRS.keys()),
                                        **self._AVD_SPEC_ATTRS)
        self._mock_avd_spec.cfg = mock_cfg

    @staticmethod
    def _CreateZip(path):
        """Create a zip file that contains a subdirectory."""
        with zipfile.ZipFile(path, "w") as zip_file:
            zip_file.writestr("x86_64/build.prop", "")
            zip_file.writestr("x86_64/test", "")

    def _MockDownloadArtifact(self, _build_target, _build_id, resource_id,
                              local_path, _attempt):
        if resource_id.endswith(".zip"):
            self._CreateZip(local_path)
        elif resource_id == "emulator-info.txt":
            with open(local_path, "w") as file:
                file.write(self._EMULATOR_INFO)
        else:
            with open(local_path, "w") as file:
                pass

    def testCreateInstanceWithCfg(self):
        """Test RemoteHostGoldfishDeviceFactory with default config."""
        factory = gf_factory.RemoteHostGoldfishDeviceFactory(
            self._mock_avd_spec)
        instance_name = factory.CreateInstance()

        self.assertEqual(self._X86_64_INSTANCE_NAME, instance_name)
        self.assertEqual(self._X86_64_BUILD_INFO, factory.GetBuildInfoDict())
        self.assertEqual({}, factory.GetFailures())
        # Artifacts.
        self._mock_android_build_client.DownloadArtifact.assert_any_call(
            "sdk_tools_linux", "111111",
            "sdk-repo-linux-emulator-111111.zip", mock.ANY, mock.ANY)
        self._mock_android_build_client.DownloadArtifact.assert_any_call(
            "sdk_x86_64-sdk", "123456",
            "sdk-repo-linux-system-images-123456.zip", mock.ANY, mock.ANY)
        self._mock_android_build_client.DownloadArtifact.assert_any_call(
            "sdk_x86_64-sdk", "123456",
            "emulator-info.txt", mock.ANY, mock.ANY)
        self.assertEqual(
            3, self._mock_android_build_client.DownloadArtifact.call_count)
        # Commands.
        self._mock_ssh.Run.assert_called_with(self._SSH_COMMAND)

    def testCreateInstanceWithAvdSpec(self):
        """Test RemoteHostGoldfishDeviceFactory with command options."""
        self._mock_avd_spec.remote_image = self._ARM64_BUILD_INFO
        self._mock_avd_spec.host_ssh_private_key_path = "key_path"
        self._mock_avd_spec.emulator_build_id = "999999"
        self._mock_avd_spec.emulator_build_target = "aarch64_sdk_tools_mac"
        self._mock_avd_spec.boot_timeout_secs = 1
        self._mock_android_build_client.DownloadArtifact.side_effect = (
            AssertionError("DownloadArtifact should not be called."))
        # All artifacts are cached.
        with tempfile.TemporaryDirectory() as download_dir:
            self._mock_avd_spec.image_download_dir = download_dir
            artifact_paths = (
                os.path.join(download_dir, "999999",
                             "aarch64_sdk_tools_mac",
                             "sdk-repo-darwin_aarch64-emulator-999999.zip"),
                os.path.join(download_dir, "123456",
                             "sdk_arm64-sdk",
                             "sdk-repo-linux-system-images-123456.zip"),
            )
            for artifact_path in artifact_paths:
                os.makedirs(os.path.dirname(artifact_path), exist_ok=True)
                self._CreateZip(artifact_path)

            factory = gf_factory.RemoteHostGoldfishDeviceFactory(
                self._mock_avd_spec)
            instance_name = factory.CreateInstance()

        self.assertEqual(self._ARM64_INSTANCE_NAME, instance_name)
        self.assertEqual(self._ARM64_BUILD_INFO, factory.GetBuildInfoDict())
        self.assertEqual({}, factory.GetFailures())


if __name__ == "__main__":
    unittest.main()
