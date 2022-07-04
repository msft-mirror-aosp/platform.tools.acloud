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
import subprocess

from acloud import errors
from acloud.create import create_common
from acloud.internal import constants
from acloud.internal.lib import ssh
from acloud.internal.lib import utils
from acloud.public import report


logger = logging.getLogger(__name__)

# bootloader and kernel are files required to launch AVD.
_ARTIFACT_FILES = ["*.img", "bootloader", "kernel"]
_REMOTE_IMAGE_DIR = "acloud_cf"
# The boot image name pattern corresponds to the use cases:
# - In a cuttlefish build environment, ANDROID_PRODUCT_OUT conatins boot.img
#   and boot-debug.img. The former is the default boot image. The latter is not
#   useful for cuttlefish.
# - In an officially released GKI (Generic Kernel Image) package, the image
#   name is boot-<kernel version>.img.
_BOOT_IMAGE_NAME_PATTERN = r"boot(-[\d.]+)?\.img"
_VENDOR_BOOT_IMAGE_NAME = "vendor_boot.img"
_KERNEL_IMAGE_NAMES = ("kernel", "bzImage", "Image")
_INITRAMFS_IMAGE_NAME = "initramfs.img"
_REMOTE_BOOT_IMAGE_PATH = remote_path.join(_REMOTE_IMAGE_DIR, "boot.img")
_REMOTE_VENDOR_BOOT_IMAGE_PATH = remote_path.join(
    _REMOTE_IMAGE_DIR, _VENDOR_BOOT_IMAGE_NAME)
_REMOTE_KERNEL_IMAGE_PATH = remote_path.join(
    _REMOTE_IMAGE_DIR, _KERNEL_IMAGE_NAMES[0])
_REMOTE_INITRAMFS_IMAGE_PATH = remote_path.join(
    _REMOTE_IMAGE_DIR, _INITRAMFS_IMAGE_NAME)

_ANDROID_BOOT_IMAGE_MAGIC = b"ANDROID!"

# Cuttlefish runtime directory is specified by `-instance_dir <runtime_dir>`.
# Cuttlefish tools may create a symbolic link at the specified path.
# The actual location of the runtime directory depends on the version:
#
# In Android 10, the directory is `<runtime_dir>`.
#
# In Android 11 and 12, the directory is `<runtime_dir>.<num>`.
# `<runtime_dir>` is a symbolic link to the first device's directory.
#
# In the latest version, if `--instance-dir <runtime_dir>` is specified, the
# directory is `<runtime_dir>/instances/cvd-<num>`.
# `<runtime_dir>_runtime` and `<runtime_dir>.<num>` are symbolic links.
#
# If `--instance-dir <runtime_dir>` is not specified, the directory is
# `~/cuttlefish/instances/cvd-<num>`.
# `~/cuttlefish_runtime` and `~/cuttelfish_runtime.<num>` are symbolic links.
_LOCAL_LOG_DIR_FORMAT = os.path.join(
    "%(runtime_dir)s", "instances", "cvd-%(num)d", "logs")
_REMOTE_RUNTIME_DIR_FORMAT = remote_path.join(
    "cuttlefish", "instances", "cvd-%(num)d")
_REMOTE_LEGACY_RUNTIME_DIR_FORMAT = "cuttlefish_runtime.%(num)d"
HOST_KERNEL_LOG = report.LogFile(
    "/var/log/kern.log", constants.LOG_TYPE_KERNEL_LOG, "host_kernel.log")
FETCHER_CONFIG_JSON = report.LogFile(
    "fetcher_config.json", constants.LOG_TYPE_CUTTLEFISH_LOG)


def GetAdbPorts(base_instance_num, num_avds_per_instance):
    """Get ADB ports of cuttlefish.

    Args:
        base_instance_num: An integer or None, the instance number of the first
                           device.
        num_avds_per_instance: An integer or None, the number of devices.

    Returns:
        The port numbers as a list of integers.
    """
    return [constants.CF_ADB_PORT + (base_instance_num or 1) - 1 + index
            for index in range(num_avds_per_instance or 1)]


def GetVncPorts(base_instance_num, num_avds_per_instance):
    """Get VNC ports of cuttlefish.

    Args:
        base_instance_num: An integer or None, the instance number of the first
                           device.
        num_avds_per_instance: An integer or None, the number of devices.

    Returns:
        The port numbers as a list of integers.
    """
    return [constants.CF_VNC_PORT + (base_instance_num or 1) - 1 + index
            for index in range(num_avds_per_instance or 1)]


def _UploadImageZip(ssh_obj, image_zip):
    """Upload an image zip to a remote host and a GCE instance.

    Args:
        ssh_obj: An Ssh object.
        image_zip: The path to the image zip.
    """
    remote_cmd = f"/usr/bin/install_zip.sh . < {image_zip}"
    logger.debug("remote_cmd:\n %s", remote_cmd)
    ssh_obj.Run(remote_cmd)


def _UploadImageDir(ssh_obj, image_dir):
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


def _UploadCvdHostPackage(ssh_obj, cvd_host_package):
    """Upload a CVD host package to a remote host or a GCE instance.

    Args:
        ssh_obj: An Ssh object.
        cvd_host_package: The path to the CVD host package.
    """
    remote_cmd = f"tar -x -z -f - < {cvd_host_package}"
    logger.debug("remote_cmd:\n %s", remote_cmd)
    ssh_obj.Run(remote_cmd)


@utils.TimeExecute(function_description="Processing and uploading local images")
def UploadArtifacts(ssh_obj, image_path, cvd_host_package):
    """Upload images and a CVD host package to a remote host or a GCE instance.

    Args:
        ssh_obj: An Ssh object.
        image_path: A string, the path to the image zip built by `m dist` or
                    the directory containing the images built by `m`.
        cvd_host_package: A string, the path to the CVD host package in gzip.
    """
    if os.path.isdir(image_path):
        _UploadImageDir(ssh_obj, image_path)
    else:
        _UploadImageZip(ssh_obj, image_path)
    _UploadCvdHostPackage(ssh_obj, cvd_host_package)


def _IsBootImage(image_path):
    """Check if a file is an Android boot image by reading the magic bytes.

    Args:
        image_path: The file path.

    Returns:
        A boolean, whether the file is a boot image.
    """
    if not os.path.isfile(image_path):
        return False
    with open(image_path, "rb") as image_file:
        return image_file.read(8) == _ANDROID_BOOT_IMAGE_MAGIC


def FindBootImages(search_path):
    """Find boot and vendor_boot images in a path.

    Args:
        search_path: A path to an image file or an image directory.

    Returns:
        The boot image path and the vendor_boot image path. Each value can be
        None if the path doesn't exist.

    Raises:
        errors.GetLocalImageError if search_path contains more than one boot
        image or the file format is not correct.
    """
    boot_image_path = create_common.FindLocalImage(
        search_path, _BOOT_IMAGE_NAME_PATTERN, raise_error=False)
    if boot_image_path and not _IsBootImage(boot_image_path):
        raise errors.GetLocalImageError(
            f"{boot_image_path} is not a boot image.")

    vendor_boot_image_path = os.path.join(search_path, _VENDOR_BOOT_IMAGE_NAME)
    if not os.path.isfile(vendor_boot_image_path):
        vendor_boot_image_path = None

    return boot_image_path, vendor_boot_image_path


def FindKernelImages(search_path):
    """Find kernel and initramfs images in a path.

    Args:
        search_path: A path to an image directory.

    Returns:
        The kernel image path and the initramfs image path. Each value can be
        None if the path doesn't exist.
    """
    paths = [os.path.join(search_path, name) for name in _KERNEL_IMAGE_NAMES]
    kernel_image_path = next((path for path in paths if os.path.isfile(path)),
                             None)

    initramfs_image_path = os.path.join(search_path, _INITRAMFS_IMAGE_NAME)
    if not os.path.isfile(initramfs_image_path):
        initramfs_image_path = None

    return kernel_image_path, initramfs_image_path


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

    boot_image_path, vendor_boot_image_path = FindBootImages(search_path)
    if boot_image_path:
        ssh_obj.ScpPushFile(boot_image_path, _REMOTE_BOOT_IMAGE_PATH)
        launch_cvd_args = ["-boot_image", _REMOTE_BOOT_IMAGE_PATH]
        if vendor_boot_image_path:
            ssh_obj.ScpPushFile(vendor_boot_image_path,
                                _REMOTE_VENDOR_BOOT_IMAGE_PATH)
            launch_cvd_args.extend(["-vendor_boot_image",
                                    _REMOTE_VENDOR_BOOT_IMAGE_PATH])
        return launch_cvd_args

    kernel_image_path, initramfs_image_path = FindKernelImages(search_path)
    if kernel_image_path and initramfs_image_path:
        ssh_obj.ScpPushFile(kernel_image_path, _REMOTE_KERNEL_IMAGE_PATH)
        ssh_obj.ScpPushFile(initramfs_image_path, _REMOTE_INITRAMFS_IMAGE_PATH)
        return ["-kernel_path", _REMOTE_KERNEL_IMAGE_PATH,
                "-initramfs_path", _REMOTE_INITRAMFS_IMAGE_PATH]

    raise errors.GetLocalImageError(
        f"{search_path} is not a boot image or a directory containing images.")


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


def CleanUpRemoteCvd(ssh_obj, raise_error):
    """Call stop_cvd and delete the files on a remote host or a GCE instance.

    Args:
        ssh_obj: An Ssh object.
        raise_error: Whether to raise an error if the remote instance is not
                     running.

    Raises:
        subprocess.CalledProcessError if any command fails.
    """
    stop_cvd_cmd = "./bin/stop_cvd"
    if raise_error:
        ssh_obj.Run(stop_cvd_cmd)
    else:
        try:
            ssh_obj.Run(stop_cvd_cmd, retry=0)
        except subprocess.CalledProcessError as e:
            logger.debug(
                "Failed to stop_cvd (possibly no running device): %s", e)

    # This command deletes all files except hidden files under HOME.
    # It does not raise an error if no files can be deleted.
    ssh_obj.Run("'rm -rf ./*'")


def _GetRemoteRuntimeDirs(ssh_obj, base_instance_num, num_avds_per_instance):
    """Get cuttlefish runtime directories on a remote host or a GCE instance.

    Args:
        ssh_obj: An Ssh object.
        base_instance_num: An integer, the instance number of the first device.
        num_avds_per_instance: An integer, the number of devices.

    Returns:
        A list of strings, the paths to the runtime directories.
    """
    runtime_dir = _REMOTE_RUNTIME_DIR_FORMAT % {"num": base_instance_num}
    try:
        ssh_obj.Run(f"test -d {runtime_dir}", retry=0)
        return [_REMOTE_RUNTIME_DIR_FORMAT % {"num": base_instance_num + num}
                for num in range(num_avds_per_instance)]
    except subprocess.CalledProcessError:
        logger.debug("%s is not the runtime directory.", runtime_dir)

    legacy_runtime_dirs = [constants.REMOTE_LOG_FOLDER]
    legacy_runtime_dirs.extend(_REMOTE_LEGACY_RUNTIME_DIR_FORMAT %
                               {"num": base_instance_num + num}
                               for num in range(1, num_avds_per_instance))
    return legacy_runtime_dirs


def _GetRemoteTombstone(runtime_dir, name_suffix):
    """Get log object for tombstones in a remote cuttlefish runtime directory.

    Args:
        runtime_dir: The path to the remote cuttlefish runtime directory.
        name_suffix: The string appended to the log name. It is used to
                     distinguish log files found in different runtime_dirs.

    Returns:
        A report.LogFile object.
    """
    return report.LogFile(remote_path.join(runtime_dir, "tombstones"),
                          constants.LOG_TYPE_DIR,
                          "tombstones-zip" + name_suffix)


def FindRemoteLogs(ssh_obj, base_instance_num, num_avds_per_instance):
    """Find log objects on a remote host or a GCE instance.

    Args:
        ssh_obj: An Ssh object.
        base_instance_num: An integer or None, the instance number of the first
                           device.
        num_avds_per_instance: An integer or None, the number of devices.

    Returns:
        A list of report.LogFile objects.
    """
    runtime_dirs = _GetRemoteRuntimeDirs(
        ssh_obj, (base_instance_num or 1), (num_avds_per_instance or 1))
    logs = []
    for log_path in utils.FindRemoteFiles(ssh_obj, runtime_dirs):
        file_name = remote_path.basename(log_path)
        base, ext = remote_path.splitext(file_name)
        # The index of the runtime_dir containing log_path.
        index_str = ""
        for index, runtime_dir in enumerate(runtime_dirs):
            if log_path.startswith(runtime_dir + remote_path.sep):
                index_str = "." + str(index) if index else ""
        log_name = base + index_str + ext
        log_type = constants.LOG_TYPE_CUTTLEFISH_LOG

        if file_name == "kernel.log":
            log_type = constants.LOG_TYPE_KERNEL_LOG
        elif file_name == "logcat":
            log_type = constants.LOG_TYPE_LOGCAT
            log_name = "full_gce_logcat" + index_str
        elif not (file_name.endswith(".log") or
                  file_name == "cuttlefish_config.json"):
            continue
        logs.append(report.LogFile(log_path, log_type, log_name))

    logs.extend(_GetRemoteTombstone(runtime_dir,
                                    ("." + str(index) if index else ""))
                for index, runtime_dir in enumerate(runtime_dirs))
    return logs


def FindLocalLogs(runtime_dir, instance_num):
    """Find log objects in a local runtime directory.

    Args:
        runtime_dir: A string, the runtime directory path.
        instance_num: An integer, the instance number.

    Returns:
        A list of report.LogFile.
    """
    log_dir = _LOCAL_LOG_DIR_FORMAT % {"runtime_dir": runtime_dir,
                                       "num": instance_num}
    if not os.path.isdir(log_dir):
        log_dir = runtime_dir
    return [report.LogFile(os.path.join(log_dir, name), log_type)
            for name, log_type in [
                ("launcher.log", constants.LOG_TYPE_CUTTLEFISH_LOG),
                ("kernel.log", constants.LOG_TYPE_KERNEL_LOG),
                ("logcat", constants.LOG_TYPE_LOGCAT)]]


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
