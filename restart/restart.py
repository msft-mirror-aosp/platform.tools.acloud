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
r"""Restart entry point.

This command will restart the CF AVD from a remote instance.
"""

from __future__ import print_function

from acloud import errors
from acloud.list import list as list_instances
from acloud.public import config
from acloud.public import report


def RestartFromInstance(instance, instance_id):
    """Restart AVD from remote CF instance.

    Args:
        instance: list.Instance() object.
        instance_id: Integer of the instance id.

    Returns:
        A Report instance.
    """
    # TODO(162382338): rewrite this function to restart AVD from the remote instance.
    print("We will restart AVD id (%s) from the instance: %s."
          % (instance_id, instance.name))
    return report.Report(command="restart")


def Run(args):
    """Run restart.

    After restart command executed, tool will return one Report instance.

    Args:
        args: Namespace object from argparse.parse_args.

    Returns:
        A Report instance.

    Raises:
        errors.CommandArgError: Lack the instance_name in args.
    """
    cfg = config.GetAcloudConfig(args)
    if args.instance_name:
        instance = list_instances.GetInstancesFromInstanceNames(
            cfg, [args.instance_name])
        return RestartFromInstance(instance[0], args.instance_id)
    raise errors.CommandArgError("Please assign the '--instance-name' in your command.")
