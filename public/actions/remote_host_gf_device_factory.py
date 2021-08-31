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

"""RemoteInstanceDeviceFactory provides basic interface to create a goldfish
device factory."""

import logging
import os
import posixpath as remote_path
import re
import shutil
import tempfile
import zipfile

from acloud import errors
from acloud.internal import constants
from acloud.internal.lib import android_build_client
from acloud.internal.lib import auth
from acloud.internal.lib import goldfish_remote_host_client
from acloud.internal.lib import utils
from acloud.internal.lib import ssh
from acloud.public.actions import base_device_factory


logger = logging.getLogger(__name__)
# Artifacts
_IMAGE_ZIP_NAME_FORMAT = "sdk-repo-linux-system-images-%(build_id)s.zip"
_EMULATOR_INFO_NAME = "emulator-info.txt"
_EMULATOR_VERSION_PATTERN = re.compile(r"require\s+version-emulator="
                                       r"(?P<build_id>\w+)")
_EMULATOR_ZIP_NAME_FORMAT = "sdk-repo-%(os)s-emulator-%(build_id)s.zip"
_EMULATOR_BIN_DIR_NAMES = ("bin64", "qemu")
_EMULATOR_BIN_NAME = "emulator"
# Remote paths
_REMOTE_WORKING_DIR = "acloud_gf"
_REMOTE_ARTIFACT_DIR = remote_path.join(_REMOTE_WORKING_DIR, "artifact")
_REMOTE_IMAGE_DIR = remote_path.join(_REMOTE_WORKING_DIR, "image")
_REMOTE_EMULATOR_DIR = remote_path.join(_REMOTE_WORKING_DIR, "emulator")
_REMOTE_INSTANCE_DIR = remote_path.join(_REMOTE_WORKING_DIR, "instance")
# Runtime parameters
_EMULATOR_DEFAULT_CONSOLE_PORT = 5554


class RemoteHostGoldfishDeviceFactory(base_device_factory.BaseDeviceFactory):
    """A class that creates a goldfish device on a remote host.

    Attributes:
        avd_spec: AVDSpec object that tells us what we're going to create.
        ssh: Ssh object that executes commands on the remote host.
        failures: A dictionary the maps instance names to
                  error.DeviceBootError objects.
    """
    def __init__(self, avd_spec):
        """Initialize the attributes and the compute client."""
        self._avd_spec = avd_spec
        self._ssh = ssh.Ssh(
            ip=ssh.IP(ip=self._avd_spec.remote_host),
            user=self._ssh_user,
            ssh_private_key_path=self._ssh_private_key_path,
            extra_args_ssh_tunnel=self._ssh_extra_args,
            report_internal_ip=False)
        self._failures = {}
        super().__init__(compute_client=(
            goldfish_remote_host_client.GoldfishRemoteHostClient()))

    @property
    def _ssh_user(self):
        return self._avd_spec.host_user or constants.GCE_USER

    @property
    def _ssh_private_key_path(self):
        return (self._avd_spec.host_ssh_private_key_path or
                self._avd_spec.cfg.ssh_private_key_path)

    @property
    def _ssh_extra_args(self):
        return self._avd_spec.cfg.extra_args_ssh_tunnel

    def CreateInstance(self):
        """Create a goldfish instance on the remote host.

        Returns:
            The instance name.
        """
        self._InitRemoteHost()
        remote_emulator_dir, remote_image_dir = self._PrepareArtifacts()

        instance_name = goldfish_remote_host_client.FormatInstanceName(
            self._avd_spec.remote_host,
            _EMULATOR_DEFAULT_CONSOLE_PORT,
            self._avd_spec.remote_image)
        try:
            self._StartEmulator(remote_emulator_dir, remote_image_dir)
            self._WaitForEmulator()
        except errors.DeviceBootError as e:
            self._failures[instance_name] = e
        return instance_name

    def _InitRemoteHost(self):
        """Remove existing instance and working directory."""
        # Disable authentication for emulator console.
        self._ssh.Run("""'echo -n "" > .emulator_console_auth_token'""")
        # TODO(b/185094559): Send kill command to emulator console.
        self._ssh.Run("'pkill -ef %s || true'" %
                      remote_path.join("~", _REMOTE_EMULATOR_DIR, '".*"'))
        # Delete instance files.
        self._ssh.Run("rm -rf %s" % _REMOTE_WORKING_DIR)

    def _PrepareArtifacts(self):
        """Prepare artifacts on remote host.

        This method retrieves artifacts from cache or Android Build API and
        uploads them to the remote host.
        """
        if self._avd_spec.image_download_dir:
            temp_download_dir = None
            download_dir = self._avd_spec.image_download_dir
        else:
            temp_download_dir = tempfile.mkdtemp()
            download_dir = temp_download_dir
            logger.info("--image-download-dir is not specified. Create "
                        "temporary download directory: %s", download_dir)

        try:
            emulator_zip_path, image_zip_path = self._RetrieveArtifacts(
                download_dir)
            return self._UploadArtifacts(emulator_zip_path, image_zip_path)
        finally:
            if temp_download_dir:
                shutil.rmtree(temp_download_dir, ignore_errors=True)

    @staticmethod
    def _InferEmulatorZipName(build_target, build_id):
        """Determine the emulator zip name in build artifacts.

        The emulator zip name is composed of build variables that are not
        revealed in the artifacts. This method infers the emulator zip name
        from its build target name.

        Args:
            build_target: The emulator build target name, e.g.,
                          "sdk_tools_linux", "aarch64_sdk_tools_mac".
            build_id: A string, the emulator build ID.

        Returns:
            The name of the emulator zip. e.g.,
            "sdk-repo-linux-emulator-123456.zip",
            "sdk-repo-darwin_aarch64-emulator-123456.zip".
        """
        split_target = [x for product_variant in build_target.split("-")
                        for x in product_variant.split("_")]
        if "darwin" in split_target or "mac" in split_target:
            os_name = "darwin"
        else:
            os_name = "linux"
        if "aarch64" in split_target:
            os_name = os_name + "_aarch64"
        return _EMULATOR_ZIP_NAME_FORMAT % {"os": os_name,
                                            "build_id": build_id}

    @staticmethod
    def _RetrieveArtifact(download_dir, build_api, build_target, build_id,
                          resource_id):
        """Retrieve an artifact from cache or Android Build API.

        Args:
            download_dir: The cache directory.
            build_api: An AndroidBuildClient object.
            build_target: A string, the build target of the artifact. e.g.,
                          "sdk_phone_x86_64-userdebug".
            build_id: A string, the build ID of the artifact.
            resource_id: A string, the name of the artifact. e.g.,
                         "sdk-repo-linux-system-images-123456.zip".

        Returns:
            The path to the artifact in download_dir.
        """
        local_path = os.path.join(download_dir, build_id, build_target,
                                  resource_id)
        if os.path.isfile(local_path):
            logger.info("Skip downloading existing artifact: %s", local_path)
            return local_path

        complete = False
        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            build_api.DownloadArtifact(build_target, build_id, resource_id,
                                       local_path, build_api.LATEST)
            complete = True
        finally:
            if not complete and os.path.isfile(local_path):
                os.remove(local_path)
        return local_path

    def _RetrieveEmulatorBuildID(self, download_dir, build_api, build_target,
                                 build_id):
        """Retrieve required emulator build from a goldfish image build."""
        emulator_info_path = self._RetrieveArtifact(download_dir, build_api,
                                                    build_target, build_id,
                                                    _EMULATOR_INFO_NAME)
        with open(emulator_info_path, 'r') as emulator_info:
            for line in emulator_info:
                match = _EMULATOR_VERSION_PATTERN.fullmatch(line.strip())
                if match:
                    logger.info("Found emulator build ID: %s", line)
                    return match.group("build_id")
        return None

    @utils.TimeExecute(function_description="Download Android Build artifacts")
    def _RetrieveArtifacts(self, download_dir):
        """Retrieve goldfish images and tools from cache or Android Build API.

        Args:
            download_dir: The cache directory.

        Returns:
            The paths to emulator zip and image zip.

        Raises:
            errors.GetRemoteImageError: Fails to download rom images.
        """
        credentials = auth.CreateCredentials(self._avd_spec.cfg)
        build_api = android_build_client.AndroidBuildClient(credentials)

        build_id = self._avd_spec.remote_image.get(constants.BUILD_ID)
        build_target = self._avd_spec.remote_image.get(constants.BUILD_TARGET)
        image_zip_name = _IMAGE_ZIP_NAME_FORMAT % {"build_id": build_id}
        image_zip_path = self._RetrieveArtifact(download_dir, build_api,
                                                build_target, build_id,
                                                image_zip_name)

        emu_build_id = self._avd_spec.emulator_build_id
        if not emu_build_id:
            emu_build_id = self._RetrieveEmulatorBuildID(
                download_dir, build_api, build_target, build_id)
            if not emu_build_id:
                raise errors.GetRemoteImageError(
                    "No emulator build ID in command line or "
                    "emulator-info.txt.")

        emu_build_target = (self._avd_spec.emulator_build_target or
                            self._avd_spec.cfg.emulator_build_target)
        emu_zip_name = self._InferEmulatorZipName(emu_build_target,
                                                  emu_build_id)
        emu_zip_path = self._RetrieveArtifact(download_dir, build_api,
                                              emu_build_target, emu_build_id,
                                              emu_zip_name)
        return emu_zip_path, image_zip_path

    @staticmethod
    def _GetSubdirNameInZip(zip_path):
        """Get the name of the only subdirectory in a zip.

        In an SDK repository zip, the images and the binaries are located in a
        subdirectory. This class needs to find out the subdirectory name in
        order to construct the remote commands.

        For example, in sdk-repo-*-emulator-*.zip, all files are in
        "emulator/". The zip entries are:

        emulator/NOTICE.txt
        emulator/emulator
        emulator/lib64/libc++.so
        ...

        This method scans the entries and returns the common subdirectory name.
        """
        sep = "/"
        with zipfile.ZipFile(zip_path, 'r') as zip_obj:
            entries = zip_obj.namelist()
            if len(entries) > 0 and sep in entries[0]:
                subdir = entries[0].split(sep, 1)[0]
                if all(e.startswith(subdir + sep) for e in entries):
                    return subdir
            logger.warning("Expect one subdirectory in %s. Actual entries: %s",
                           zip_path, " ".join(entries))
            return ""

    @utils.TimeExecute(
        function_description="Processing and uploading local images")
    def _UploadArtifacts(self, emulator_zip_path, image_zip_path):
        """Upload artifacts to remote host and extract them.

        Args:
            emulator_zip_path: The local path to the emulator zip.
            image_zip_path: The local path to the image zip.

        Returns:
            The remote paths to the extracted emulator tools and images.
        """
        self._ssh.Run("mkdir -p " +
                      " ".join([_REMOTE_INSTANCE_DIR, _REMOTE_ARTIFACT_DIR,
                                _REMOTE_EMULATOR_DIR, _REMOTE_IMAGE_DIR]))
        self._ssh.ScpPushFile(emulator_zip_path, _REMOTE_ARTIFACT_DIR)
        self._ssh.ScpPushFile(image_zip_path, _REMOTE_ARTIFACT_DIR)

        self._ssh.Run("unzip -d %s %s" % (
            _REMOTE_EMULATOR_DIR,
            remote_path.join(_REMOTE_ARTIFACT_DIR,
                             os.path.basename(emulator_zip_path))))
        self._ssh.Run("unzip -d %s %s" % (
            _REMOTE_IMAGE_DIR,
            remote_path.join(_REMOTE_ARTIFACT_DIR,
                             os.path.basename(image_zip_path))))
        remote_emulator_subdir = remote_path.join(
            _REMOTE_EMULATOR_DIR, self._GetSubdirNameInZip(emulator_zip_path))
        remote_image_subdir = remote_path.join(
            _REMOTE_IMAGE_DIR, self._GetSubdirNameInZip(image_zip_path))
        # TODO(b/141898893): In Android build environment, emulator gets build
        # information from $ANDROID_PRODUCT_OUT/system/build.prop.
        # If image_dir is an extacted SDK repository, the file is at
        # image_dir/build.prop. Acloud copies it to
        # image_dir/system/build.prop.
        src_path = remote_path.join(remote_image_subdir, "build.prop")
        dst_path = remote_path.join(remote_image_subdir, "system",
                                    "build.prop")
        self._ssh.Run("'mkdir -p %s ; cp %s %s'" %
                      (remote_path.dirname(dst_path), src_path, dst_path))
        return remote_emulator_subdir, remote_image_subdir

    @utils.TimeExecute(function_description="Start emulator")
    def _StartEmulator(self, remote_emulator_dir, remote_image_dir):
        """Start emulator command as a remote background process.

        Args:
            remote_emulator_dir: The emulator tool directory on remote host.
            remote_image_dir: The image directory on remote host.
        """
        remote_emulator_bin_path = remote_path.join(remote_emulator_dir,
                                                    _EMULATOR_BIN_NAME)
        remote_bin_paths = [remote_path.join(remote_emulator_dir, name) for
                            name in _EMULATOR_BIN_DIR_NAMES]
        remote_bin_paths.append(remote_emulator_bin_path)
        self._ssh.Run("chmod -R +x %s" % " ".join(remote_bin_paths))

        remote_logcat_path = os.path.join(_REMOTE_INSTANCE_DIR, "logcat.txt")
        remote_stdout_path = os.path.join(_REMOTE_INSTANCE_DIR, "stdout.txt")
        remote_stderr_path = os.path.join(_REMOTE_INSTANCE_DIR, "stderr.txt")

        env = {constants.ENV_ANDROID_PRODUCT_OUT: remote_image_dir,
               constants.ENV_ANDROID_TMP: _REMOTE_INSTANCE_DIR,
               constants.ENV_ANDROID_BUILD_TOP: _REMOTE_INSTANCE_DIR}
        adb_port = _EMULATOR_DEFAULT_CONSOLE_PORT + 1
        cmd = ["nohup", remote_emulator_bin_path, "-verbose", "-show-kernel",
               "-read-only", "-ports",
               str(_EMULATOR_DEFAULT_CONSOLE_PORT) + "," + str(adb_port),
               "-no-window", "-logcat-output", remote_logcat_path]
        if self._avd_spec.gpu:
            cmd.extend(("-gpu", self._avd_spec.gpu))
        self._ssh.Run(
            "'export {env} ; {cmd} 1> {stdout} 2> {stderr} &'".format(
                env=" ".join(k + "=~/" + v for k, v in env.items()),
                cmd=" ".join(cmd),
                stdout=remote_stdout_path,
                stderr=remote_stderr_path))

    @utils.TimeExecute(function_description="Wait for emulator")
    def _WaitForEmulator(self):
        """TODO(b/185094559): Wait for remote emulator console."""

    def GetBuildInfoDict(self):
        """Get build info dictionary.

        Returns:
            A build info dictionary.
        """
        build_info_dict = {key: val for key, val in
                           self._avd_spec.remote_image.items() if val}
        return build_info_dict

    def GetFailures(self):
        """Get Failures from all devices.

        Returns:
            A dictionary the contains all the failures.
            The key is the name of the instance that fails to boot,
            and the value is an errors.DeviceBootError object.
        """
        return self._failures
