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

"""A client that talks to Oxygen proxy APIs."""

import logging
import subprocess


logger = logging.getLogger(__name__)


class OxygenClient():
    """Client that manages Oxygen proxy api."""

    @staticmethod
    def LeaseDevice(build_target, build_id, oxygen_client):
        """Lease one cuttlefish device.

        Args:
            build_target: Target name, e.g. "aosp_cf_x86_64_phone-userdebug"
            build_id: Build ID, a string, e.g. "2263051", "P2804227"
            oxygen_client: String of oxygen client path.

        Returns:
            The response of calling oxygen proxy client.
        """
        try:
            response = subprocess.check_output([
                oxygen_client, "-lease", "-build_id", build_id, "-build_target",
                build_target], stderr=subprocess.STDOUT, encoding='utf-8')
            logger.debug("The response from oxygen client: %s", response)
            return response
        except subprocess.CalledProcessError as e:
            logger.error("Failed to lease device from Oxygen, error: %s",
                         e.output)
            raise e

    @staticmethod
    def ReleaseDevice(session_id, server_url, oxygen_client):
        """Release one cuttlefish device.

        Args:
            session_id: String of session id.
            server_url: String of server url.
            oxygen_client: String of oxygen client path.
        """
        try:
            response = subprocess.check_output([
                oxygen_client, "-release", "-session_id", session_id,
                "-server_url", server_url
            ], stderr=subprocess.STDOUT, encoding='utf-8')
            logger.debug("The response from oxygen client: %s", response)
        except subprocess.CalledProcessError as e:
            logger.error("Failed to release device from Oxygen, error: %s",
                         e.output)
            raise e
