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

"""RemoteInstanceDeviceFactory provides basic interface to create a Trusty
device factory."""

import json
import logging
import os
import posixpath as remote_path
import shlex
import tempfile
import traceback

from acloud import errors
from acloud.create import create_common
from acloud.internal import constants
from acloud.internal.lib import cvd_utils
from acloud.internal.lib import utils
from acloud.public import report
from acloud.public.actions import gce_device_factory
from acloud.pull import pull


logger = logging.getLogger(__name__)
_CONFIG_JSON_FILENAME = "config.json"
_REMOTE_STDOUT_PATH = "kernel.log"
_REMOTE_STDERR_PATH = "qemu_trusty_err.log"
_TRUSTY_IMAGE_PACKAGE = "trusty_image_package.tar.gz"
_TRUSTY_HOST_PACKAGE_DIR = "trusty-host_package"
_TRUSTY_HOST_TARBALL = "trusty-host_package.tar.gz"

# Default Trusty image build. This does not depend on the android branch.
_DEFAULT_TRUSTY_BUILD_BRANCH = "aosp-trusty-master"
_DEFAULT_TRUSTY_BUILD_TARGET = "qemu_generic_arm64_test_debug"


def _TrustyImagePackageFilename(build_target):
    trusty_target = build_target.replace("_", "-")
    return f"{trusty_target}.{_TRUSTY_IMAGE_PACKAGE}"


def _FindHostPackage(package_path=None):
    if package_path:
        # checked in create_args._VerifyTrustyArgs
        return package_path
    dirs_to_check = create_common.GetNonEmptyEnvVars(
        constants.ENV_ANDROID_SOONG_HOST_OUT, constants.ENV_ANDROID_HOST_OUT
    )
    dist_dir = utils.GetDistDir()
    if dist_dir:
        dirs_to_check.append(dist_dir)

    for path in dirs_to_check:
        for name in [_TRUSTY_HOST_TARBALL, _TRUSTY_HOST_PACKAGE_DIR]:
            trusty_host_package = os.path.join(path, name)
            if os.path.exists(trusty_host_package):
                return trusty_host_package
    raise errors.GetTrustyLocalHostPackageError(
        "Can't find the trusty host package (Try lunching a trusty target "
        "like qemu_trusty_arm64-trunk_staging-userdebug and running 'm'): \n"
        + "\n".join(dirs_to_check))


class RemoteInstanceDeviceFactory(gce_device_factory.GCEDeviceFactory):
    """A class that can produce a Trusty device."""

    def __init__(self, avd_spec, local_android_image_artifact=None):
        super().__init__(avd_spec, local_android_image_artifact)
        self._all_logs = {}
        self._host_package_artifact = _FindHostPackage(
            avd_spec.trusty_host_package)

    # pylint: disable=broad-except
    def CreateInstance(self):
        """Create and start a single Trusty instance.

        Returns:
            The instance name as a string.
        """
        instance = self.CreateGceInstance()
        if instance in self.GetFailures():
            return instance

        try:
            self._ProcessArtifacts()
            self._StartTrusty()
        except Exception as e:
            self._SetFailures(instance, traceback.format_exception(e))

        self._FindLogFiles(
            instance,
            instance in self.GetFailures() and not self._avd_spec.no_pull_log)
        return instance

    def _ProcessArtifacts(self):
        """Process artifacts.

        - If images source is local, tool will upload images from local site to
          remote instance.
        - If images source is remote, tool will download images from android
          build to remote instance.
        """
        avd_spec = self._avd_spec
        if avd_spec.image_source == constants.IMAGE_SRC_LOCAL:
            cvd_utils.UploadArtifacts(
                self._ssh,
                cvd_utils.GCE_BASE_DIR,
                (self._local_image_artifact or avd_spec.local_image_dir),
                self._host_package_artifact)
            self._UploadTrustyImages(avd_spec.local_trusty_image)
        elif avd_spec.image_source == constants.IMAGE_SRC_REMOTE:
            self._FetchBuild()
            if self._compute_client.build_api.GetKernelBuild(
                    avd_spec.kernel_build_info):
                self._ReplaceModules()
            self._FetchAndUploadTrustyImages()

        config = {
            "linux": "kernel",
            "linux_arch": "arm64",
            "atf": "atf/qemu/debug",
            "qemu": "bin/trusty_qemu_system_aarch64",
            "extra_qemu_flags": ["-machine", "gic-version=2"],
            "android_image_dir": ".",
            "rpmbd": "bin/rpmb_dev",
            "arch": "arm64",
            "adb": "bin/adb",
        }
        with tempfile.NamedTemporaryFile(mode="w+t") as config_json_file:
            json.dump(config, config_json_file)
            config_json_file.flush()
            remote_config_path = remote_path.join(
                cvd_utils.GCE_BASE_DIR, _CONFIG_JSON_FILENAME)
            self._ssh.ScpPushFile(config_json_file.name, remote_config_path)

    # We are building our own command-line instead of using
    # self._compute_client.FetchBuild() because we need to use the host cvd
    # tool rather than `fetch_cvd`. The downloaded fetch_cvd tool is too
    # old and cannot handle a custom host package filename. This can be
    # removed when b/298447306 is fixed.
    @utils.TimeExecute(function_description="Fetching builds")
    def _FetchBuild(self):
        """Fetch builds from android build server."""
        avd_spec = self._avd_spec
        build_client = self._compute_client.build_api

        # Provide the default trusty host package artifact filename. We must
        # explicitly use the default build id/branch and target for the host
        # package if those values were not set for the host package so that we
        # can override the artifact filename.
        host_package = avd_spec.host_package_build_info.copy()
        if not (
            host_package[constants.BUILD_ID]
            or host_package[constants.BUILD_BRANCH]
        ):
            host_package[constants.BUILD_ID] = avd_spec.remote_image[
                constants.BUILD_ID]
            host_package[constants.BUILD_BRANCH] = avd_spec.remote_image[
                constants.BUILD_BRANCH]
        if not host_package[constants.BUILD_TARGET]:
            host_package[constants.BUILD_TARGET] = avd_spec.remote_image[
                constants.BUILD_TARGET]
        host_package.setdefault(constants.BUILD_ARTIFACT, _TRUSTY_HOST_TARBALL)

        fetch_args = build_client.GetFetchBuildArgs(
            avd_spec.remote_image,
            {},
            avd_spec.kernel_build_info,
            {},
            {},
            {},
            {},
            host_package,
        )
        fetch_cmd = (
            constants.CMD_CVD_FETCH
            + ["-credential_source=gce"]
            + fetch_args
        )
        self._ssh.Run(" ".join(fetch_cmd), timeout=constants.DEFAULT_SSH_TIMEOUT)

    def _ReplaceModules(self):
        """Replace modules in android ramdisk with modules from the kernel build"""
        android_ramdisk = remote_path.join(cvd_utils.GCE_BASE_DIR, "ramdisk.img")
        kernel_ramdisk = remote_path.join(cvd_utils.GCE_BASE_DIR, "initramfs.img")
        # We are switching to the bin/ directory so host tools are in the
        # current directory for python to find.
        self._ssh.Run(
            f"cd {cvd_utils.GCE_BASE_DIR}/bin && ./replace_ramdisk_modules "
            f"--android-ramdisk={android_ramdisk} "
            f"--kernel-ramdisk={kernel_ramdisk} "
            f"--output-ramdisk={android_ramdisk}",
            timeout=constants.DEFAULT_SSH_TIMEOUT)

    @utils.TimeExecute(function_description="Downloading and uploading Trusty image")
    def _FetchAndUploadTrustyImages(self):
        """Download Trusty image archive"""
        build_client = self._compute_client.build_api
        trusty_build_info = self._avd_spec.trusty_build_info
        build_id = trusty_build_info[constants.BUILD_ID]
        build_branch = (
            trusty_build_info[constants.BUILD_BRANCH]
            or _DEFAULT_TRUSTY_BUILD_BRANCH
        )
        build_target = (
            trusty_build_info[constants.BUILD_TARGET]
            or _DEFAULT_TRUSTY_BUILD_TARGET
        )
        if not build_id:
            build_id = build_client.GetLKGB(build_target, build_branch)
        with tempfile.NamedTemporaryFile(suffix=".tar.gz") as image_local_file:
            image_local_path = image_local_file.name
            build_client.DownloadArtifact(
                build_target,
                build_id,
                _TrustyImagePackageFilename(build_target),
                image_local_path,
            )
            self._UploadTrustyImages(image_local_path)

    def _UploadTrustyImages(self, archive_path):
        """Upload Trusty image archive"""
        remote_cmd = (f"tar -xzf - -C {cvd_utils.GCE_BASE_DIR} < "
                      + archive_path)
        logger.debug("remote_cmd:\n %s", remote_cmd)
        self._ssh.Run(remote_cmd)

    @utils.TimeExecute(function_description="Starting Trusty")
    def _StartTrusty(self):
        """Start the model on the GCE instance."""

        # We use an explicit subshell so we can run this command in the
        # background.
        cmd = "-- sh -c " + shlex.quote(shlex.quote(
            f"{cvd_utils.GCE_BASE_DIR}/run.py "
            f"--config={_CONFIG_JSON_FILENAME} "
            f"> {_REMOTE_STDOUT_PATH} 2> {_REMOTE_STDERR_PATH} &"
        ))
        self._ssh.Run(cmd, self._avd_spec.boot_timeout_secs or 30, retry=0)

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
        logs.append(
            report.LogFile(_REMOTE_STDOUT_PATH, constants.LOG_TYPE_KERNEL_LOG))
        logs.append(
            report.LogFile(_REMOTE_STDERR_PATH, constants.LOG_TYPE_TEXT))
        self._all_logs[instance] = logs

        logger.debug("logs: %s", logs)
        if download:
            # To avoid long download time, fetch from the first device only.
            log_paths = [log["path"] for log in logs]
            error_log_folder = pull.PullLogs(self._ssh, log_paths, instance)
            self._compute_client.ExtendReportData(
                constants.ERROR_LOG_FOLDER, error_log_folder)

    def GetLogs(self):
        """Get all device logs.

        Returns:
            A dictionary that maps instance names to lists of report.LogFile.
        """
        return self._all_logs
