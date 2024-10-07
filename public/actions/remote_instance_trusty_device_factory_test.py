# Copyright 2024 - The Android Open Source Project
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
"""Tests for remote_instance_trusty_device_factory."""

import glob
import logging
import os
import tempfile
import unittest
import uuid

from unittest import mock

from acloud.create import avd_spec
from acloud.internal import constants
from acloud.internal.lib import android_build_client
from acloud.internal.lib import auth
from acloud.internal.lib import cvd_compute_client_multi_stage
from acloud.internal.lib import driver_test_lib
from acloud.list import list as list_instances
from acloud.public.actions import remote_instance_trusty_device_factory

logger = logging.getLogger(__name__)

_EXPECTED_CONFIG_JSON = '''{"linux": "kernel", "linux_arch": "arm64", \
"atf": "atf/qemu/debug", "qemu": "bin/trusty_qemu_system_aarch64", \
"extra_qemu_flags": ["-machine", "gic-version=2"], "android_image_dir": ".", \
"rpmbd": "bin/rpmb_dev", "arch": "arm64", "adb": "bin/adb"}'''


class RemoteInstanceDeviceFactoryTest(driver_test_lib.BaseDriverTest):
    """Test RemoteInstanceDeviceFactory."""

    def setUp(self):
        super().setUp()
        self.Patch(auth, "CreateCredentials", return_value=mock.MagicMock())
        self.Patch(android_build_client.AndroidBuildClient, "InitResourceHandle")
        self.Patch(android_build_client.AndroidBuildClient, "DownloadArtifact")
        self.Patch(cvd_compute_client_multi_stage.CvdComputeClient, "InitResourceHandle")
        self.Patch(list_instances, "GetInstancesFromInstanceNames", return_value=mock.MagicMock())
        self.Patch(list_instances, "ChooseOneRemoteInstance", return_value=mock.MagicMock())
        self.Patch(glob, "glob", return_value=["fake.img"])

    # pylint: disable=protected-access
    @mock.patch("acloud.public.actions.remote_instance_trusty_device_factory."
                "cvd_utils")
    def testLocalImage(self, mock_cvd_utils):
        """test ProcessArtifacts with local image."""
        fake_emulator_package = "/fake/trusty_build/trusty_image_package.tar.gz"
        fake_image_name = "/fake/qemu_trusty_arm64-img-eng.username.zip"
        fake_host_package_name = "/fake/trusty_host_package.tar.gz"
        fake_tmp_path = "/fake/tmp_file"

        args = mock.MagicMock()
        args.config_file = ""
        args.avd_type = constants.TYPE_TRUSTY
        args.flavor = "phone"
        args.local_image = constants.FIND_IN_BUILD_ENV
        args.launch_args = None
        args.autoconnect = constants.INS_KEY_WEBRTC
        args.local_trusty_image = fake_emulator_package
        args.trusty_host_package = fake_host_package_name
        args.reuse_gce = None
        mock_cvd_utils.GCE_BASE_DIR = "gce_base_dir"

        # Test local images
        avd_spec_local_img = avd_spec.AVDSpec(args)

        self.Patch(os.path, "exists", return_value=True)
        factory_local_img = remote_instance_trusty_device_factory.RemoteInstanceDeviceFactory(
            avd_spec_local_img,
            fake_image_name)
        mock_ssh = mock.Mock()
        factory_local_img._ssh = mock_ssh

        temp_config = ""
        def WriteTempConfig(s):
            nonlocal temp_config
            temp_config += s
        temp_config_mock = mock.MagicMock()
        temp_config_mock.__enter__().name = fake_tmp_path
        temp_config_mock.__enter__().write.side_effect = WriteTempConfig
        self.Patch(tempfile, "NamedTemporaryFile", return_value=temp_config_mock)

        factory_local_img._ProcessArtifacts()

        mock_cvd_utils.UploadArtifacts.assert_called_once_with(
            mock.ANY, mock_cvd_utils.GCE_BASE_DIR, fake_image_name,
            fake_host_package_name)
        mock_ssh.Run.assert_called_once_with(
            f"tar -xzf - -C {mock_cvd_utils.GCE_BASE_DIR} "
            f"< {fake_emulator_package}")
        self.assertEqual(temp_config, _EXPECTED_CONFIG_JSON)
        mock_ssh.ScpPushFile.assert_called_with(
            fake_tmp_path, f"{mock_cvd_utils.GCE_BASE_DIR}/config.json")

    # pylint: disable=protected-access
    @mock.patch("acloud.public.actions.remote_instance_trusty_device_factory."
                "cvd_utils")
    def testRemoteImage(self, mock_cvd_utils):
        """test ProcessArtifacts with remote image source."""
        fake_tmp_path = "/fake/tmp_file"

        args = mock.MagicMock()
        args.config_file = ""
        args.avd_type = constants.TYPE_TRUSTY
        args.flavor = "phone"
        args.local_image = None
        args.launch_args = None
        args.autoconnect = constants.INS_KEY_WEBRTC
        args.local_trusty_image = None
        args.reuse_gce = None
        args.build_id = "default_build_id"
        args.branch = "default_branch"
        args.build_target = "default_target"
        args.kernel_build_id = "kernel_build_id"
        args.kernel_build_target = "kernel_target"
        args.host_package_build_id = None
        args.host_package_branch = None
        args.host_package_build_target = None
        mock_cvd_utils.GCE_BASE_DIR = "gce_base_dir"

        avd_spec_remote_img = avd_spec.AVDSpec(args)
        factory_remote_img = remote_instance_trusty_device_factory.RemoteInstanceDeviceFactory(
            avd_spec_remote_img)
        mock_ssh = mock.Mock()
        factory_remote_img._ssh = mock_ssh

        temp_file_mock = mock.MagicMock()
        temp_file_mock.__enter__().name = fake_tmp_path
        self.Patch(tempfile, "NamedTemporaryFile", return_value=temp_file_mock)

        factory_remote_img._ProcessArtifacts()

        # Download trusty image package
        factory_remote_img.GetComputeClient().build_api.DownloadArtifact.called_once()

        mock_ssh.Run.assert_has_calls(
            [
                mock.call(
                    "cvd fetch -credential_source=gce "
                    "-default_build=default_build_id/default_target "
                    "-kernel_build=kernel_build_id/kernel_target "
                    "-host_package_build=default_build_id/default_target{trusty-host_package.tar.gz}",
                    timeout=300,
                ),
                mock.call(
                    f"cd {mock_cvd_utils.GCE_BASE_DIR}/bin && "
                    "./replace_ramdisk_modules "
                    f"--android-ramdisk={mock_cvd_utils.GCE_BASE_DIR}/ramdisk.img "
                    f"--kernel-ramdisk={mock_cvd_utils.GCE_BASE_DIR}/initramfs.img "
                    f"--output-ramdisk={mock_cvd_utils.GCE_BASE_DIR}/ramdisk.img",
                    timeout=300,
                ),
                mock.call(
                    f"tar -xzf - -C {mock_cvd_utils.GCE_BASE_DIR} "
                    f"< {fake_tmp_path}"
                ),
            ]
        )


    @mock.patch.object(remote_instance_trusty_device_factory.RemoteInstanceDeviceFactory,
                       "CreateGceInstance")
    @mock.patch("acloud.public.actions.remote_instance_trusty_device_factory."
                "cvd_utils")
    def testLocalImageCreateInstance(self, mock_cvd_utils, mock_create_gce_instance):
        """Test CreateInstance with local images."""
        self.Patch(
            cvd_compute_client_multi_stage,
            "CvdComputeClient",
            return_value=mock.MagicMock())
        mock_cvd_utils.GCE_BASE_DIR = "gce_base_dir"
        mock_create_gce_instance.return_value = "instance"
        fake_avd_spec = mock.MagicMock()
        fake_avd_spec.image_source = constants.IMAGE_SRC_LOCAL
        fake_avd_spec._instance_name_to_reuse = None
        fake_avd_spec.no_pull_log = False
        fake_avd_spec.base_instance_num = None
        fake_avd_spec.num_avds_per_instance = None

        mock_cvd_utils.HOST_KERNEL_LOG = {"path": "/host_kernel.log"}

        fake_image_name = ""
        factory = remote_instance_trusty_device_factory.RemoteInstanceDeviceFactory(
            fake_avd_spec,
            fake_image_name)
        mock_ssh = mock.Mock()
        factory._ssh = mock_ssh
        factory.CreateInstance()
        mock_create_gce_instance.assert_called_once()
        mock_cvd_utils.UploadArtifacts.assert_called_once()
        # First call is unpacking image archive
        self.assertEqual(mock_ssh.Run.call_count, 2)
        self.assertIn(
            "gce_base_dir/run.py --config=config.json",
            mock_ssh.Run.call_args[0][0])

        self.assertEqual(3, len(factory.GetLogs().get("instance")))


if __name__ == "__main__":
    unittest.main()
