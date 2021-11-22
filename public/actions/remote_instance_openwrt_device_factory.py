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
"""RemoteInstanceDeviceFactory provides basic interface to create an OpenWrt
device factory."""

import logging
import subprocess

from acloud.internal import constants
from acloud.internal.lib import utils
from acloud.internal.lib.ssh import Ssh
from acloud.public.actions import gce_device_factory


logger = logging.getLogger(__name__)
_INSTALL_PKG_CMD = (
    "'sudo apt-get update && "
    "sudo apt-get -y install perl gawk wget git-core rsync file'")
# TODO(b/189417881): Make OpenWrt image version configurable.
_IMAGE_VERSION = "21.02.0-rc3"
_IMAGE_PATH = "openwrt-imagebuilder-%s-x86-64.Linux-x86_64" % _IMAGE_VERSION
_IMAGE_URL = "https://downloads.openwrt.org/releases/%(ver)s/targets/x86/64/%(img_path)s.tar.xz" % {
    "ver": _IMAGE_VERSION,
    "img_path": _IMAGE_PATH
}
_ZIP_PATH_HEAD = "bin/targets/x86/64/openwrt-%s-x86-64-generic" % _IMAGE_VERSION
_BUILD_OPENWRT_CMD = (
    "'curl -o tmp.tar.xz %(img_url)s && "
    "tar -xf tmp.tar.xz && "
    "rm tmp.tar.xz && "
    "cd %(img_path)s && "
    "make .profiles.mk && "
    "make image PROFILE=generic && "
    "gzip -d %(zip_path)s-squashfs-rootfs.img.gz'"
) % {
    "img_url": _IMAGE_URL,
    "img_path": _IMAGE_PATH,
    "zip_path": _ZIP_PATH_HEAD}
_OPENWRT_ROOT_PATH = "/home/vsoc-01/%(img_path)s/%(zip_path)s-squashfs-rootfs.img" % {
        "img_path": _IMAGE_PATH,
        "zip_path": _ZIP_PATH_HEAD}
_OPENWRT_KERNEL_PATH = "/home/vsoc-01/%(img_path)s/%(zip_path)s-kernel.bin" % {
        "img_path": _IMAGE_PATH,
        "zip_path": _ZIP_PATH_HEAD}
_LAUNCH_OPENWRT_CMD = (
    "./bin/launch_cvd -daemon -console=true -pause_in_bootloader -otheros_root_image=%s "
    "-otheros_kernel_path=%s -base_instance_num 2"
    % (_OPENWRT_ROOT_PATH, _OPENWRT_KERNEL_PATH))
_NO_RETRY = 0
_TIMEOUT = 30
# Screen commands to control OpenWrt device.
_CMD_SCREEN_PRINT_ENV = r"screen -r -X stuff 'printenv^M'"
_CMD_SCREEN_RESET_ENV = r"screen -r -X stuff 'env\ default\ -f\ -a\ -^M'"
_CMD_SCREEN_SET_FDT_AND_BOOT = r"screen -r -X stuff 'setenv\ fdt_addr_r\ %s^M\ boot^M'"


class OpenWrtDeviceFactory(gce_device_factory.GCEDeviceFactory):
    """A class that can produce a openwrt device.

    Attributes:
        _avd_spec: An AVDSpec instance.
        _ssh: An Ssh object.

    """
    LOG_FILES = []

    def __init__(self, avd_spec, instance):
        """Initialize.

        Args:
            avd_spec: An AVDSpec instance.
            instance: String, the instance name.
        """
        self._avd_spec = avd_spec
        super().__init__(avd_spec)
        self._ssh = Ssh(
            ip=self._compute_client.GetInstanceIP(instance),
            user=constants.GCE_USER,
            ssh_private_key_path=avd_spec.cfg.ssh_private_key_path,
            extra_args_ssh_tunnel=avd_spec.cfg.extra_args_ssh_tunnel,
            report_internal_ip=avd_spec.report_internal_ip)

    def CreateDevice(self):
        """Creates the OpenWrt device."""
        # TODO(189417881): Update job status into report and move the hint
        # messages into device summary.
        self._InstallPackages()
        self._BuildOpenWrtImage()
        self._LaunchOpenWrt()
        self._BootOpenWrt()
        self._HintConnectMessage()

    @utils.TimeExecute(function_description="Install required packages")
    def _InstallPackages(self):
        """Install required packages for OpenWrt devices."""
        self._ssh.Run(_INSTALL_PKG_CMD)

    @utils.TimeExecute(function_description="Build OpenWrt images")
    def _BuildOpenWrtImage(self):
        """Build OpenWrt root image and kernel."""
        self._ssh.Run(_BUILD_OPENWRT_CMD)

    @utils.TimeExecute(function_description="Launch OpenWrt device")
    def _LaunchOpenWrt(self):
        """Lanuch OpenWrt device and create console file."""
        try:
            self._ssh.Run(_LAUNCH_OPENWRT_CMD, timeout=_TIMEOUT, retry=_NO_RETRY)
        except subprocess.CalledProcessError:
            logger.debug("Create OpenWRT screen file: cuttlefish_runtime/console")


    def _OpenScreenSection(self):
        """Open Screen scection."""
        self._ssh.Run("screen -d -m ./cuttlefish_runtime/console")

    def _GetFdtAddrEnv(self):
        """Get fdt_addr_r value.

        Get the environment value from the console log file.

        Returns:
            String, the environment value of "fdtcontroladdr".
        """
        console_log = "./cuttlefish_runtime/console_log"
        self._ssh.Run(_CMD_SCREEN_PRINT_ENV)
        output = self._ssh.GetCmdOutput("cat %s" % console_log)
        for line in output.splitlines():
            if line.startswith("fdtcontroladdr="):
                logger.debug("Get environment %s", line)
                return line.replace("fdtcontroladdr=", "").strip()
        return None

    @utils.TimeExecute(function_description="Waiting OpenWrt device boot up")
    def _BootOpenWrt(self):
        """Boot OpenWrt device.

        The process includes:
            1. Create screen section.
            2. Reset environment to default values.
            3. Set fdt_addr_r environment value.
        """
        self._OpenScreenSection()
        env_fdt_addr = self._GetFdtAddrEnv()
        self._ssh.Run(_CMD_SCREEN_RESET_ENV)
        self._ssh.Run(_CMD_SCREEN_SET_FDT_AND_BOOT % env_fdt_addr)

    def _HintConnectMessage(self):
        """Display the ssh and screen commands for users."""
        utils.PrintColorString(
            "Please run the following commands to control the OpenWrt device:\n")
        utils.PrintColorString(
            "$ %(ssh_cmd)s\n$ screen -r\n" %
            {"ssh_cmd": self._ssh.GetBaseCmd(constants.SSH_BIN)},
            utils.TextColors.OKGREEN)
