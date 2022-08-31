# Copyright 2019 - The Android Open Source Project
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

"""RemoteInstanceDeviceFactory provides basic interface to create a cuttlefish
device factory."""

import logging

from acloud.internal import constants
from acloud.internal.lib import cvd_utils
from acloud.public.actions import gce_device_factory
from acloud.pull import pull


logger = logging.getLogger(__name__)
_SCREEN_CONSOLE_COMMAND = "screen ~/cuttlefish_runtime/console"


class RemoteInstanceDeviceFactory(gce_device_factory.GCEDeviceFactory):
    """A class that can produce a cuttlefish device.

    Attributes:
        avd_spec: AVDSpec object that tells us what we're going to create.
        cfg: An AcloudConfig instance.
        local_image_artifact: A string, path to local image.
        cvd_host_package_artifact: A string, path to cvd host package.
        report_internal_ip: Boolean, True for the internal ip is used when
                            connecting from another GCE instance.
        credentials: An oauth2client.OAuth2Credentials instance.
        compute_client: An object of cvd_compute_client.CvdComputeClient.
        ssh: An Ssh object.
    """
    def __init__(self, avd_spec, local_image_artifact=None,
                 cvd_host_package_artifact=None):
        super().__init__(avd_spec, local_image_artifact)
        self._all_logs = {}
        self._cvd_host_package_artifact = cvd_host_package_artifact

    # pylint: disable=broad-except
    def CreateInstance(self):
        """Create a single configured cuttlefish device.

        Returns:
            A string, representing instance name.
        """
        instance = self._CreateGceInstance()
        # If instance is failed, no need to go next step.
        if instance in self.GetFailures():
            return instance
        try:
            image_args = self._ProcessArtifacts()
            failures = self._compute_client.LaunchCvd(
                instance,
                self._avd_spec,
                self._cfg.extra_data_disk_size_gb,
                boot_timeout_secs=self._avd_spec.boot_timeout_secs,
                extra_args=image_args)
            for failing_instance, error_msg in failures.items():
                self._SetFailures(failing_instance, error_msg)
        except Exception as e:
            self._SetFailures(instance, e)

        self._FindLogFiles(
            instance,
            instance in self.GetFailures() and not self._avd_spec.no_pull_log)
        return instance

    def _ProcessArtifacts(self):
        """Process artifacts.

        - If images source is local, tool will upload images from local site to
          remote instance.
        - If images source is remote, tool will download images from android
          build to remote instance. Before download images, we have to update
          fetch_cvd to remote instance.

        Returns:
            A list of strings, the launch_cvd arguments.
        """
        avd_spec = self._avd_spec
        if avd_spec.image_source == constants.IMAGE_SRC_LOCAL:
            cvd_utils.UploadArtifacts(
                self._ssh,
                cvd_utils.GCE_BASE_DIR,
                self._local_image_artifact or avd_spec.local_image_dir,
                self._cvd_host_package_artifact)
        elif avd_spec.image_source == constants.IMAGE_SRC_REMOTE:
            self._compute_client.UpdateFetchCvd()
            self._compute_client.FetchBuild(
                avd_spec.remote_image,
                avd_spec.system_build_info,
                avd_spec.kernel_build_info,
                avd_spec.boot_build_info,
                avd_spec.bootloader_build_info,
                avd_spec.ota_build_info)

        if avd_spec.mkcert and avd_spec.connect_webrtc:
            self._compute_client.UpdateCertificate()

        if avd_spec.extra_files:
            self._compute_client.UploadExtraFiles(avd_spec.extra_files)

        return cvd_utils.UploadExtraImages(
            self._ssh, cvd_utils.GCE_BASE_DIR, avd_spec)

    def _FindLogFiles(self, instance, download):
        """Find and pull all log files from instance.

        Args:
            instance: String, instance name.
            download: Whether to download the files to a temporary directory
                      and show messages to the user.
        """
        logs = [cvd_utils.HOST_KERNEL_LOG]
        if self._avd_spec.image_source == constants.IMAGE_SRC_REMOTE:
            logs.append(
                cvd_utils.GetRemoteFetcherConfigJson(cvd_utils.GCE_BASE_DIR))
        logs.extend(cvd_utils.FindRemoteLogs(
            self._ssh,
            cvd_utils.GCE_BASE_DIR,
            self._avd_spec.base_instance_num,
            self._avd_spec.num_avds_per_instance))
        self._all_logs[instance] = logs

        if download:
            # To avoid long download time, fetch from the first device only.
            log_files = pull.GetAllLogFilePaths(self._ssh,
                                                constants.REMOTE_LOG_FOLDER)
            error_log_folder = pull.PullLogs(self._ssh, log_files, instance)
            self._compute_client.ExtendReportData(constants.ERROR_LOG_FOLDER,
                                                  error_log_folder)

    def GetOpenWrtInfoDict(self):
        """Get openwrt info dictionary.

        Returns:
            A openwrt info dictionary. None for the case is not openwrt device.
        """
        if not self._avd_spec.openwrt:
            return None
        return {"ssh_command": self._compute_client.GetSshConnectCmd(),
                "screen_command": _SCREEN_CONSOLE_COMMAND}

    def GetAdbPorts(self):
        """Get ADB ports of the created devices.

        Returns:
            The port numbers as a list of integers.
        """
        return cvd_utils.GetAdbPorts(self._avd_spec.base_instance_num,
                                     self._avd_spec.num_avds_per_instance)

    def GetVncPorts(self):
        """Get VNC ports of the created devices.

        Returns:
            The port numbers as a list of integers.
        """
        return cvd_utils.GetVncPorts(self._avd_spec.base_instance_num,
                                     self._avd_spec.num_avds_per_instance)

    def GetBuildInfoDict(self):
        """Get build info dictionary.

        Returns:
            A build info dictionary. None for local image case.
        """
        if self._avd_spec.image_source == constants.IMAGE_SRC_LOCAL:
            return None
        return cvd_utils.GetRemoteBuildInfoDict(self._avd_spec)

    def GetLogs(self):
        """Get all device logs.

        Returns:
            A dictionary that maps instance names to lists of report.LogFile.
        """
        return self._all_logs
