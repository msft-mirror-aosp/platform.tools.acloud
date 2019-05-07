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
"""Action to create goldfish device instances.

A Goldfish device is an emulated android device based on the android
emulator.
"""
import logging
import os

from acloud import errors
from acloud.public.actions import base_device_factory
from acloud.public.actions import common_operations
from acloud.internal import constants
from acloud.internal.lib import android_build_client
from acloud.internal.lib import auth
from acloud.internal.lib import goldfish_compute_client
from acloud.internal.lib import utils

logger = logging.getLogger(__name__)

_EMULATOR_INFO_FILENAME = "emulator-info.txt"
_EMULATOR_VERSION_PATTERN = "version-emulator"
_SYSIMAGE_INFO_FILENAME = "android-info.txt"
_SYSIMAGE_VERSION_PATTERN = "version-sysimage-{}-{}"


class GoldfishDeviceFactory(base_device_factory.BaseDeviceFactory):
    """A class that can produce a goldfish device.

    Attributes:
        _cfg: An AcloudConfig instance.
        _build_target: String, the build target, e.g. aosp_x86-eng.
        _build_id: String, Build id, e.g. "2263051", "P2804227"
        _emulator_build_target: String, the emulator build target, e.g. aosp_x86-eng.
        _emulator_build_id: String, emulator build id.
        _gpu: String, GPU to attach to the device or None. e.g. "nvidia-tesla-k80"
        _blank_data_disk_size_gb: Integer, extra disk size
        _build_client: An AndroidBuildClient instance
        _branch: String, android branch name, e.g. git_master
        _emulator_branch: String, emulator branch name, e.g. "aosp-emu-master-dev"
    """
    LOG_FILES = ["/home/vsoc-01/emulator.log",
                 "/home/vsoc-01/log/logcat.log",
                 "/home/vsoc-01/log/adb.log",
                 "/var/log/daemon.log"]

    def __init__(self,
                 cfg,
                 build_target,
                 build_id,
                 emulator_build_target,
                 emulator_build_id,
                 gpu=None,
                 avd_spec=None):

        """Initialize.

        Args:
            cfg: An AcloudConfig instance.
            build_target: String, the build target, e.g. aosp_x86-eng.
            build_id: String, Build id, e.g. "2263051", "P2804227"
            emulator_build_target: String, the emulator build target, e.g. aosp_x86-eng.
            emulator_build_id: String, emulator build id.
            gpu: String, GPU to attach to the device or None. e.g. "nvidia-tesla-k80"
            avd_spec: An AVDSpec instance.
        """

        self.credentials = auth.CreateCredentials(cfg)

        compute_client = goldfish_compute_client.GoldfishComputeClient(
            cfg, self.credentials)
        super(GoldfishDeviceFactory, self).__init__(compute_client)

        # Private creation parameters
        self._cfg = cfg
        self._build_target = build_target
        self._build_id = build_id
        self._emulator_build_id = emulator_build_id
        self._emulator_build_target = emulator_build_target
        self._gpu = gpu
        self._avd_spec = avd_spec
        self._blank_data_disk_size_gb = cfg.extra_data_disk_size_gb

        # Configure clients
        self._build_client = android_build_client.AndroidBuildClient(
            self.credentials)

        # Discover branches
        self._branch = self._build_client.GetBranch(build_target, build_id)
        self._emulator_branch = self._build_client.GetBranch(
            emulator_build_target, emulator_build_id)

    def CreateInstance(self):
        """Creates single configured goldfish device.

        Override method from parent class.

        Returns:
            String, the name of the created instance.
        """
        instance = self._compute_client.GenerateInstanceName(
            build_id=self._build_id, build_target=self._build_target)

        self._compute_client.CreateInstance(
            instance=instance,
            image_name=self._cfg.stable_goldfish_host_image_name,
            image_project=self._cfg.stable_goldfish_host_image_project,
            build_target=self._build_target,
            branch=self._branch,
            build_id=self._build_id,
            emulator_branch=self._emulator_branch,
            emulator_build_id=self._emulator_build_id,
            gpu=self._gpu,
            blank_data_disk_size_gb=self._blank_data_disk_size_gb,
            avd_spec=self._avd_spec)

        return instance


def ParseBuildInfo(filename, pattern):
    """Parse build id based on a substring.

    This will parse a file which contains build information to be used. For an
    emulator build, the file will contain the information about the corresponding
    stable system image build id. Similarly, for a system image build, the file
    will contain the information about the corresponding stable emulator build id.
    Pattern is a substring being used as a key to parse the build info. For
    example, "version-sysimage-git_pi-dev-sdk_gphone_x86_64-userdebug".

    Args:
        filename: Name of file to parse.
        pattern: Substring to look for in file

    Returns:
        Build id parsed from the file based on pattern
        Returns None if pattern not found in file
    """
    with open(filename) as build_info_file:
        for line in build_info_file:
            if pattern in line:
                return line.rstrip().split("=")[1]
    return None


def _FetchBuildIdFromFile(cfg, build_target, build_id, pattern, filename):
    """Parse and fetch build id from a file based on a pattern.

    Verify if one of the system image or emulator binary build id is missing.
    If found missing, then update according to the resource file.

    Args:
        cfg: An AcloudConfig instance.
        build_target: Target name.
        build_id: Build id, a string, e.g. "2263051", "P2804227"
        pattern: A string to parse build info file.
        filename: Name of file containing the build info.

    Returns:
        A build id or None
    """
    build_client = android_build_client.AndroidBuildClient(
        auth.CreateCredentials(cfg))

    with utils.TempDir() as tempdir:
        temp_filename = os.path.join(tempdir, filename)
        build_client.DownloadArtifact(build_target,
                                      build_id,
                                      filename,
                                      temp_filename)

        return ParseBuildInfo(temp_filename, pattern)


def CreateDevices(avd_spec=None,
                  cfg=None,
                  build_target=None,
                  build_id=None,
                  emulator_build_id=None,
                  gpu=None,
                  num=1,
                  serial_log_file=None,
                  logcat_file=None,
                  autoconnect=False,
                  branch=None,
                  report_internal_ip=False):
    """Create one or multiple Goldfish devices.

    Args:
        avd_spec: An AVDSpec instance.
        cfg: An AcloudConfig instance.
        build_target: String, the build target, e.g. aosp_x86-eng.
        build_id: String, Build id, e.g. "2263051", "P2804227"
        emulator_build_id: String, emulator build id.
        gpu: String, GPU to attach to the device or None. e.g. "nvidia-tesla-k80"
        num: Integer, Number of devices to create.
        serial_log_file: String, A path to a file where serial output should
                        be saved to.
        logcat_file: String, A path to a file where logcat logs should be saved.
        autoconnect: Boolean, Create ssh tunnel(s) and adb connect after device creation.
        branch: String, Branch name for system image.
        report_internal_ip: Boolean to report the internal ip instead of
                            external ip.

    Returns:
        A Report instance.
    """
    if avd_spec:
        cfg = avd_spec.cfg
        build_target = avd_spec.remote_image[constants.BUILD_TARGET]
        build_id = avd_spec.remote_image[constants.BUILD_ID]
        branch = avd_spec.remote_image[constants.BUILD_BRANCH]
        num = avd_spec.num
        emulator_build_id = avd_spec.emulator_build_id
        gpu = avd_spec.gpu
        serial_log_file = avd_spec.serial_log_file
        logcat_file = avd_spec.logcat_file
        autoconnect = avd_spec.autoconnect
        report_internal_ip = avd_spec.report_internal_ip

    if emulator_build_id is None:
        emulator_build_id = _FetchBuildIdFromFile(cfg,
                                                  build_target,
                                                  build_id,
                                                  _EMULATOR_VERSION_PATTERN,
                                                  _EMULATOR_INFO_FILENAME)

    if emulator_build_id is None:
        raise errors.CommandArgError("Emulator build id not found "
                                     "in %s" % _EMULATOR_INFO_FILENAME)

    if build_id is None:
        pattern = _SYSIMAGE_VERSION_PATTERN.format(branch, build_target)
        build_id = _FetchBuildIdFromFile(cfg,
                                         cfg.emulator_build_target,
                                         emulator_build_id,
                                         pattern,
                                         _SYSIMAGE_INFO_FILENAME)

    if build_id is None:
        raise errors.CommandArgError("Emulator system image build id not found "
                                     "in %s" % _SYSIMAGE_INFO_FILENAME)
    logger.info(
        "Creating a goldfish device in project %s, build_target: %s, "
        "build_id: %s, emulator_bid: %s, GPU: %s, num: %s, "
        "serial_log_file: %s, logcat_file: %s, "
        "autoconnect: %s", cfg.project, build_target, build_id,
        emulator_build_id, gpu, num, serial_log_file, logcat_file, autoconnect)

    device_factory = GoldfishDeviceFactory(cfg, build_target, build_id,
                                           cfg.emulator_build_target,
                                           emulator_build_id, gpu, avd_spec)

    return common_operations.CreateDevices(
        command="create_gf",
        cfg=cfg,
        device_factory=device_factory,
        num=num,
        report_internal_ip=report_internal_ip,
        autoconnect=autoconnect,
        vnc_port=constants.DEFAULT_GOLDFISH_VNC_PORT,
        adb_port=constants.DEFAULT_GOLDFISH_ADB_PORT,
        serial_log_file=serial_log_file,
        logcat_file=logcat_file)
