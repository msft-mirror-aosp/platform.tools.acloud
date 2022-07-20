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

"""This module implements the classes and functions needed for the common
creation flow."""

from acloud.internal.lib import ssh
from acloud.public import config


# Report keys
_VERSION = "version"


class RemoteHostClient:
    """A client that manages an instance on a remote host.

    Attributes:
        ip_addr: A string, the IP address of the host.
    """

    def __init__(self, ip_addr):
        """Initialize the attribtues."""
        self._ip_addr = ip_addr

    def GetInstanceIP(self, _instance_name):
        """Return the IP address of the host."""
        return ssh.IP(ip=self._ip_addr)

    @staticmethod
    def WaitForBoot(_instance_name, _boot_timeout_secs):
        """Should not be called in the common creation flow."""
        raise NotImplementedError("The common creation flow should call "
                                  "GetFailures instead of this method.")

    @staticmethod
    def GetSerialPortOutput():
        """Remote hosts do not support serial log."""
        return ""

    @property
    def dict_report(self):
        """Return the key-value pairs to be written to the report."""
        return {_VERSION: config.GetVersion()}
