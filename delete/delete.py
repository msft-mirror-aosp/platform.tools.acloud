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
r"""Delete entry point.

Delete will handle all the logic related to deleting a local/remote instance
of an Android Virtual Device.
"""

from __future__ import print_function

import logging
import os
import re
import subprocess

from acloud import errors
from acloud.internal import constants
from acloud.internal.lib import auth
from acloud.internal.lib import adb_tools
from acloud.internal.lib import cvd_compute_client_multi_stage
from acloud.internal.lib import utils
from acloud.internal.lib import ssh as ssh_object
from acloud.list import list as list_instances
from acloud.public import config
from acloud.public import device_driver
from acloud.public import report


logger = logging.getLogger(__name__)

_COMMAND_GET_PROCESS_ID = ["pgrep", "run_cvd"]
_COMMAND_GET_PROCESS_COMMAND = ["ps", "-o", "command", "-p"]
_RE_RUN_CVD = re.compile(r"^(?P<run_cvd>.+run_cvd)")
_SSVNC_VIEWER_PATTERN = "vnc://127.0.0.1:%(vnc_port)d"
_LOCAL_INSTANCE_PREFIX = "local-"


def _GetStopCvd():
    """Get stop_cvd path.

    "stop_cvd" and "run_cvd" are in the same folder(host package folder).
    Try to get directory of "run_cvd" by "ps -o command -p <pid>." command.
    For example: "/tmp/bin/run_cvd"

    Returns:
        String of stop_cvd file path.

    Raises:
        errors.NoExecuteCmd: Can't find stop_cvd.
    """
    process_id = subprocess.check_output(_COMMAND_GET_PROCESS_ID)
    process_info = subprocess.check_output(
        _COMMAND_GET_PROCESS_COMMAND + process_id.splitlines())
    for process in process_info.splitlines():
        match = _RE_RUN_CVD.match(process)
        if match:
            run_cvd_path = match.group("run_cvd")
            stop_cvd_cmd = os.path.join(os.path.dirname(run_cvd_path),
                                        constants.CMD_STOP_CVD)
            if os.path.exists(stop_cvd_cmd):
                logger.debug("stop_cvd command: %s", stop_cvd_cmd)
                return stop_cvd_cmd

    default_stop_cvd = utils.FindExecutable(constants.CMD_STOP_CVD)
    if default_stop_cvd:
        return default_stop_cvd

    raise errors.NoExecuteCmd("Cannot find stop_cvd binary.")


def CleanupSSVncviewer(vnc_port):
    """Cleanup the old disconnected ssvnc viewer.

    Args:
        vnc_port: Integer, port number of vnc.
    """
    ssvnc_viewer_pattern = _SSVNC_VIEWER_PATTERN % {"vnc_port":vnc_port}
    utils.CleanupProcess(ssvnc_viewer_pattern)


def DeleteInstances(cfg, instances_to_delete):
    """Delete instances according to instances_to_delete.

    Args:
        cfg: AcloudConfig object.
        instances_to_delete: List of list.Instance() object.

    Returns:
        Report instance if there are instances to delete, None otherwise.
    """
    if not instances_to_delete:
        print("No instances to delete")
        return None

    delete_report = report.Report(command="delete")
    remote_instance_list = []
    for instance in instances_to_delete:
        if instance.islocal:
            if instance.avd_type == constants.TYPE_GF:
                DeleteLocalGoldfishInstance(instance, delete_report)
            elif instance.avd_type == constants.TYPE_CF:
                DeleteLocalCuttlefishInstance(instance, delete_report)
            else:
                delete_report.AddError("Deleting %s is not supported." %
                                       instance.avd_type)
                delete_report.SetStatus(report.Status.FAIL)
        else:
            remote_instance_list.append(instance.name)
        # Delete ssvnc viewer
        if instance.forwarding_vnc_port:
            CleanupSSVncviewer(instance.forwarding_vnc_port)

    if remote_instance_list:
        # TODO(119283708): We should move DeleteAndroidVirtualDevices into
        # delete.py after gce is deprecated.
        # Stop remote instances.
        return DeleteRemoteInstances(cfg, remote_instance_list, delete_report)

    return delete_report


@utils.TimeExecute(function_description="Deleting remote instances",
                   result_evaluator=utils.ReportEvaluator,
                   display_waiting_dots=False)
def DeleteRemoteInstances(cfg, instances_to_delete, delete_report=None):
    """Delete remote instances.

    Args:
        cfg: AcloudConfig object.
        instances_to_delete: List of instance names(string).
        delete_report: Report object.

    Returns:
        Report instance if there are instances to delete, None otherwise.
    """
    utils.PrintColorString("")
    for instance in instances_to_delete:
        utils.PrintColorString(" - %s" % instance, utils.TextColors.WARNING)
    utils.PrintColorString("")
    utils.PrintColorString("status: waiting...", end="")

    # TODO(119283708): We should move DeleteAndroidVirtualDevices into
    # delete.py after gce is deprecated.
    # Stop remote instances.
    delete_report = device_driver.DeleteAndroidVirtualDevices(
        cfg, instances_to_delete, delete_report)

    return delete_report


@utils.TimeExecute(function_description="Deleting local cuttlefish instances",
                   result_evaluator=utils.ReportEvaluator)
def DeleteLocalCuttlefishInstance(instance, delete_report):
    """Delete a local cuttlefish instance.

    Delete local instance with stop_cvd command and write delete instance
    information to report.

    Args:
        instance: instance.LocalInstance object.
        delete_report: Report object.

    Returns:
        delete_report.
    """
    try:
        with open(os.devnull, "w") as dev_null:
            cvd_env = os.environ.copy()
            if instance.instance_dir:
                cvd_env[constants.ENV_CUTTLEFISH_CONFIG_FILE] = os.path.join(
                    instance.instance_dir, constants.CUTTLEFISH_CONFIG_FILE)
            subprocess.check_call(
                utils.AddUserGroupsToCmd(_GetStopCvd(),
                                         constants.LIST_CF_USER_GROUPS),
                stderr=dev_null, stdout=dev_null, shell=True, env=cvd_env)
            delete_report.SetStatus(report.Status.SUCCESS)
            device_driver.AddDeletionResultToReport(
                delete_report, [instance.name], failed=[],
                error_msgs=[],
                resource_name="instance")
            CleanupSSVncviewer(instance.vnc_port)
    except subprocess.CalledProcessError as e:
        delete_report.AddError(str(e))
        delete_report.SetStatus(report.Status.FAIL)

    return delete_report


@utils.TimeExecute(function_description="Deleting local goldfish instances",
                   result_evaluator=utils.ReportEvaluator)
def DeleteLocalGoldfishInstance(instance, delete_report):
    """Delete a local goldfish instance.

    Args:
        instance: LocalGoldfishInstance object.
        delete_report: Report object.

    Returns:
        delete_report.
    """
    adb = adb_tools.AdbTools(adb_port=instance.adb_port,
                             device_serial=instance.device_serial)
    if adb.EmuCommand("kill") == 0:
        delete_report.SetStatus(report.Status.SUCCESS)
        device_driver.AddDeletionResultToReport(
            delete_report, [instance.name], failed=[],
            error_msgs=[],
            resource_name="instance")
    else:
        delete_report.AddError("Cannot kill %s." % instance.device_serial)
        delete_report.SetStatus(report.Status.FAIL)

    instance.DeleteCreationTimestamp(ignore_errors=True)
    return delete_report


def CleanUpRemoteHost(cfg, remote_host, host_user,
                      host_ssh_private_key_path=None):
    """Clean up the remote host.

    Args:
        cfg: An AcloudConfig instance.
        remote_host : String, ip address or host name of the remote host.
        host_user: String of user login into the instance.
        host_ssh_private_key_path: String of host key for logging in to the
                                   host.

    Returns:
        A Report instance.
    """
    delete_report = report.Report(command="delete")
    credentials = auth.CreateCredentials(cfg)
    compute_client = cvd_compute_client_multi_stage.CvdComputeClient(
        acloud_config=cfg,
        oauth2_credentials=credentials)
    ssh = ssh_object.Ssh(
        ip=ssh_object.IP(ip=remote_host),
        user=host_user,
        ssh_private_key_path=(
            host_ssh_private_key_path or cfg.ssh_private_key_path))
    try:
        compute_client.InitRemoteHost(ssh, remote_host, host_user)
        delete_report.SetStatus(report.Status.SUCCESS)
        device_driver.AddDeletionResultToReport(
            delete_report, [remote_host], failed=[],
            error_msgs=[],
            resource_name="remote host")
    except subprocess.CalledProcessError as e:
        delete_report.AddError(str(e))
        delete_report.SetStatus(report.Status.FAIL)

    return delete_report


def DeleteInstanceByNames(cfg, instances):
    """Delete instances by the names of these instances.

    Args:
        cfg: AcloudConfig object.
        instances: List of instance name.

    Returns:
        A Report instance.
    """
    delete_report = report.Report(command="delete")
    local_instances = [
        ins for ins in instances if ins.startswith(_LOCAL_INSTANCE_PREFIX)
    ]
    remote_instances = list(set(instances) - set(local_instances))
    if local_instances:
        utils.PrintColorString("Deleting local instances")
        delete_report = DeleteInstances(cfg, list_instances.FilterInstancesByNames(
            list_instances.GetLocalInstances(), local_instances))
    if remote_instances:
        delete_report = DeleteRemoteInstances(cfg,
                                              remote_instances,
                                              delete_report)
    return delete_report


def Run(args):
    """Run delete.

    After delete command executed, tool will return one Report instance.
    If there is no instance to delete, just reutrn empty Report.

    Args:
        args: Namespace object from argparse.parse_args.

    Returns:
        A Report instance.
    """
    # Prioritize delete instances by names without query all instance info from
    # GCP project.
    if args.instance_names:
        return DeleteInstanceByNames(config.GetAcloudConfig(args),
                                     args.instance_names)
    if args.remote_host:
        cfg = config.GetAcloudConfig(args)
        return CleanUpRemoteHost(cfg, args.remote_host, args.host_user,
                                 args.host_ssh_private_key_path)

    instances = list_instances.GetLocalInstances()
    if args.local_only:
        cfg = None
    else:
        cfg = config.GetAcloudConfig(args)
        instances.extend(list_instances.GetRemoteInstances(cfg))

    if args.adb_port:
        instances = list_instances.FilterInstancesByAdbPort(instances,
                                                            args.adb_port)
    elif not args.all:
        # Provide instances list to user and let user choose what to delete if
        # user didn't specify instances in args.
        instances = list_instances.ChooseInstancesFromList(instances)

    return DeleteInstances(cfg, instances)
