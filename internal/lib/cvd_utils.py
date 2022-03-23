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

"""Utility functions that process cuttlefish images."""

import glob
import logging
import os
import posixpath as remote_path

from acloud import errors
from acloud.internal import constants
from acloud.internal.lib import ssh
from acloud.internal.lib import utils
from acloud.public import report


logger = logging.getLogger(__name__)

# bootloader and kernel are files required to launch AVD.
_ARTIFACT_FILES = ["*.img", "bootloader", "kernel"]
_REMOTE_IMAGE_DIR = "acloud_cf"
_BOOT_IMAGE_NAME = "boot.img"
_VENDOR_BOOT_IMAGE_NAME = "vendor_boot.img"
_REMOTE_BOOT_IMAGE_PATH = remote_path.join(_REMOTE_IMAGE_DIR, _BOOT_IMAGE_NAME)
_REMOTE_VENDOR_BOOT_IMAGE_PATH = remote_path.join(
    _REMOTE_IMAGE_DIR, _VENDOR_BOOT_IMAGE_NAME)


def UploadImageZip(ssh_obj, image_zip):
    """Upload an image zip to a remote host and a GCE instance.

    Args:
        ssh_obj: An Ssh object.
        image_zip: The path to the image zip.
    """
    remote_cmd = f"/usr/bin/install_zip.sh . < {image_zip}"
    logger.debug("remote_cmd:\n %s", remote_cmd)
    ssh_obj.Run(remote_cmd)


def UploadImageDir(ssh_obj, image_dir):
    """Upload an image directory to a remote host or a GCE instance.

    The images are compressed for faster upload.

    Args:
        ssh_obj: An Ssh object.
        image_dir: The directory containing the files to be uploaded.
    """
    try:
        images_path = os.path.join(image_dir, "required_images")
        with open(images_path, "r", encoding="utf-8") as images:
            artifact_files = images.read().splitlines()
    except IOError:
        # Older builds may not have a required_images file. In this case
        # we fall back to *.img.
        artifact_files = []
        for file_name in _ARTIFACT_FILES:
            artifact_files.extend(
                os.path.basename(image) for image in glob.glob(
                    os.path.join(image_dir, file_name)))
    # Upload android-info.txt to parse config value.
    artifact_files.append(constants.ANDROID_INFO_FILE)
    cmd = (f"tar -cf - --lzop -S -C {image_dir} {' '.join(artifact_files)} | "
           f"{ssh_obj.GetBaseCmd(constants.SSH_BIN)} -- tar -xf - --lzop -S")
    logger.debug("cmd:\n %s", cmd)
    ssh.ShellCmdWithRetry(cmd)


def UploadCvdHostPackage(ssh_obj, cvd_host_package):
    """Upload and a CVD host package to a remote host or a GCE instance.

    Args:
        ssh_obj: An Ssh object.
        cvd_host_package: The path tot the CVD host package.
    """
    remote_cmd = f"tar -x -z -f - < {cvd_host_package}"
    logger.debug("remote_cmd:\n %s", remote_cmd)
    ssh_obj.Run(remote_cmd)


def _FindBootImages(search_path):
    """Find boot and vendor_boot images in a path.

    Args:
        search_path: A path to an image file or an image directory.

    Returns:
        The boot image path and the vendor_boot image path. Each value can be
        None if the path doesn't exist.
    """
    if os.path.isfile(search_path):
        return search_path, None

    paths = [os.path.join(search_path, name) for name in
             (_BOOT_IMAGE_NAME, _VENDOR_BOOT_IMAGE_NAME)]
    return [(path if os.path.isfile(path) else None) for path in paths]


@utils.TimeExecute(function_description="Uploading local kernel images.")
def _UploadKernelImages(ssh_obj, search_path):
    """Find and upload kernel images to a remote host or a GCE instance.

    Args:
        ssh_obj: An Ssh object.
        search_path: A path to an image file or an image directory.

    Returns:
        A list of strings, the launch_cvd arguments including the remote paths.

    Raises:
        errors.GetLocalImageError if search_path does not contain kernel
        images.
    """
    # Assume that the caller cleaned up the remote home directory.
    ssh_obj.Run("mkdir -p " + _REMOTE_IMAGE_DIR)

    launch_cvd_args = []
    boot_image_path, vendor_boot_image_path = _FindBootImages(search_path)
    if boot_image_path:
        ssh_obj.ScpPushFile(boot_image_path, _REMOTE_BOOT_IMAGE_PATH)
        launch_cvd_args.extend(["-boot_image", _REMOTE_BOOT_IMAGE_PATH])
        if vendor_boot_image_path:
            ssh_obj.ScpPushFile(vendor_boot_image_path,
                                _REMOTE_VENDOR_BOOT_IMAGE_PATH)
            launch_cvd_args.extend(["-vendor_boot_image",
                                    _REMOTE_VENDOR_BOOT_IMAGE_PATH])
        return launch_cvd_args

    raise errors.GetLocalImageError(f"No kernel images in {search_path}.")


def UploadExtraImages(ssh_obj, avd_spec):
    """Find and upload the images specified in avd_spec.

    Args:
        ssh_obj: An Ssh object.
        avd_spec: An AvdSpec object containing extra image paths.

    Returns:
        A list of strings, the launch_cvd arguments including the remote paths.

    Raises:
        errors.GetLocalImageError if any specified image path does not exist.
    """
    if avd_spec.local_kernel_image:
        return _UploadKernelImages(ssh_obj, avd_spec.local_kernel_image)
    return []


def ConvertRemoteLogs(log_paths):
    """Convert paths on a remote host or a GCE instance to log objects.

    Args:
        log_paths: A collection of strings, the remote paths to the logs.

    Returns:
        A list of report.LogFile objects.
    """
    logs = []
    for log_path in log_paths:
        log = report.LogFile(log_path, constants.LOG_TYPE_TEXT)
        if log_path.endswith("kernel.log"):
            log = report.LogFile(log_path, constants.LOG_TYPE_KERNEL_LOG)
        elif log_path.endswith("logcat"):
            log = report.LogFile(log_path, constants.LOG_TYPE_LOGCAT,
                                 "full_gce_logcat")
        elif not (log_path.endswith(".log") or log_path.endswith(".json")):
            continue
        logs.append(log)
    return logs


def GetRemoteBuildInfoDict(avd_spec):
    """Convert remote build infos to a dictionary for reporting.

    Args:
        avd_spec: An AvdSpec object containing the build infos.

    Returns:
        A dict containing the build infos.
    """
    build_info_dict = {
        key: val for key, val in avd_spec.remote_image.items() if val}

    # kernel_target has a default value. If the user provides kernel_build_id
    # or kernel_branch, then convert kernel build info.
    if (avd_spec.kernel_build_info.get(constants.BUILD_ID) or
            avd_spec.kernel_build_info.get(constants.BUILD_BRANCH)):
        build_info_dict.update(
            {"kernel_" + key: val
             for key, val in avd_spec.kernel_build_info.items() if val}
        )
    build_info_dict.update(
        {"system_" + key: val
         for key, val in avd_spec.system_build_info.items() if val}
    )
    build_info_dict.update(
        {"bootloader_" + key: val
         for key, val in avd_spec.bootloader_build_info.items() if val}
    )
    return build_info_dict
