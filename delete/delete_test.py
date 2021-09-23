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
"""Tests for delete."""

import subprocess
import unittest

from unittest import mock

from acloud import errors
from acloud.delete import delete
from acloud.internal.lib import driver_test_lib
from acloud.internal.lib import oxygen_client
from acloud.list import list as list_instances
from acloud.public import report


# pylint: disable=invalid-name,protected-access,unused-argument,no-member
class DeleteTest(driver_test_lib.BaseDriverTest):
    """Test delete functions."""

    def testDeleteLocalCuttlefishInstanceSuccess(self):
        """Test DeleteLocalCuttlefishInstance."""
        instance_object = mock.MagicMock()
        instance_object.name = "local-instance"
        mock_lock = mock.Mock()
        mock_lock.Lock.return_value = True
        instance_object.GetLock.return_value = mock_lock

        delete_report = report.Report(command="delete")
        delete.DeleteLocalCuttlefishInstance(instance_object, delete_report)
        self.assertEqual(delete_report.data, {
            "deleted": [
                {
                    "type": "instance",
                    "name": "local-instance",
                },
            ],
        })
        self.assertEqual(delete_report.status, "SUCCESS")
        mock_lock.SetInUse.assert_called_once_with(False)
        mock_lock.Unlock.assert_called_once()

    def testDeleteLocalCuttlefishInstanceFailure(self):
        """Test DeleteLocalCuttlefishInstance with command failure."""
        instance_object = mock.MagicMock()
        instance_object.name = "local-instance"
        instance_object.Delete.side_effect = subprocess.CalledProcessError(
            1, "cmd")
        mock_lock = mock.Mock()
        mock_lock.Lock.return_value = True
        instance_object.GetLock.return_value = mock_lock

        delete_report = report.Report(command="delete")
        delete.DeleteLocalCuttlefishInstance(instance_object, delete_report)

        self.assertEqual(delete_report.status, "FAIL")
        mock_lock.SetInUse.assert_called_once_with(False)
        mock_lock.Unlock.assert_called_once()

    def testDeleteLocalGoldfishInstanceSuccess(self):
        """Test DeleteLocalGoldfishInstance."""
        mock_adb_tools = mock.Mock()
        mock_adb_tools.EmuCommand.return_value = 0
        mock_instance = mock.Mock(adb=mock_adb_tools,
                                  adb_port=5555,
                                  device_serial="serial",
                                  instance_dir="/unit/test")
        # name is a positional argument of Mock().
        mock_instance.name = "unittest"
        mock_lock = mock.Mock()
        mock_lock.Lock.return_value = True
        mock_instance.GetLock.return_value = mock_lock

        delete_report = report.Report(command="delete")
        delete.DeleteLocalGoldfishInstance(mock_instance, delete_report)

        mock_adb_tools.EmuCommand.assert_called_with("kill")
        self.assertEqual(delete_report.data, {
            "deleted": [
                {
                    "type": "instance",
                    "name": "unittest",
                },
            ],
        })
        self.assertEqual(delete_report.status, "SUCCESS")
        mock_lock.SetInUse.assert_called_once_with(False)
        mock_lock.Unlock.assert_called_once()

    def testDeleteLocalGoldfishInstanceFailure(self):
        """Test DeleteLocalGoldfishInstance with adb command failure."""
        mock_adb_tools = mock.Mock()
        mock_adb_tools.EmuCommand.return_value = 1
        mock_instance = mock.Mock(adb=mock_adb_tools,
                                  adb_port=5555,
                                  device_serial="serial",
                                  instance_dir="/unit/test")
        # name is a positional argument of Mock().
        mock_instance.name = "unittest"
        mock_lock = mock.Mock()
        mock_lock.Lock.return_value = True
        mock_instance.GetLock.return_value = mock_lock

        delete_report = report.Report(command="delete")
        delete.DeleteLocalGoldfishInstance(mock_instance, delete_report)

        mock_adb_tools.EmuCommand.assert_called_with("kill")
        self.assertTrue(len(delete_report.errors) > 0)
        self.assertEqual(delete_report.status, "FAIL")
        mock_lock.SetInUse.assert_called_once_with(False)
        mock_lock.Unlock.assert_called_once()

    def testResetLocalInstanceLockByName(self):
        """test ResetLocalInstanceLockByName."""
        mock_lock = mock.Mock()
        mock_lock.Lock.return_value = True
        self.Patch(list_instances, "GetLocalInstanceLockByName",
                   return_value=mock_lock)
        delete_report = report.Report(command="delete")
        delete.ResetLocalInstanceLockByName("unittest", delete_report)

        self.assertEqual(delete_report.data, {
            "deleted": [
                {
                    "type": "instance",
                    "name": "unittest",
                },
            ],
        })
        mock_lock.Lock.assert_called_once()
        mock_lock.SetInUse.assert_called_once_with(False)
        mock_lock.Unlock.assert_called_once()

    def testResetLocalInstanceLockByNameFailure(self):
        """test ResetLocalInstanceLockByName with an invalid name."""
        self.Patch(list_instances, "GetLocalInstanceLockByName",
                   return_value=None)
        delete_report = report.Report(command="delete")
        delete.ResetLocalInstanceLockByName("unittest", delete_report)

        self.assertTrue(len(delete_report.errors) > 0)
        self.assertEqual(delete_report.status, "FAIL")

    @mock.patch("acloud.delete.delete.emulator_console.RemoteEmulatorConsole")
    def testDeleteHostGoldfishInstance(self, mock_console):
        """test DeleteHostGoldfishInstance."""
        mock_console_obj = mock.MagicMock()
        mock_console.return_value = mock_console_obj
        mock_console_obj.__enter__.return_value = mock_console_obj

        cfg_attrs = {"ssh_private_key_path": "cfg_key_path",
                     "extra_args_ssh_tunnel": "extra args"}
        mock_cfg = mock.Mock(spec_set=list(cfg_attrs.keys()), **cfg_attrs)
        instance_name = "host-goldfish-192.0.2.1-5554-123456-sdk_x86_64-sdk"
        delete_report = report.Report(command="delete")

        delete.DeleteHostGoldfishInstance(mock_cfg, instance_name,
                                          None, None, delete_report)
        mock_console.assert_called_with("192.0.2.1", 5554, "vsoc-01",
                                        "cfg_key_path", "extra args")
        mock_console_obj.Kill.assert_called()
        self.assertEqual(delete_report.status, "SUCCESS")
        self.assertEqual(delete_report.data, {
            "deleted": [
                {
                    "type": "instance",
                    "name": instance_name,
                },
            ],
        })

        mock_console_obj.reset_mock()
        mock_console_obj.Kill.side_effect = errors.DeviceConnectionError
        delete_report = report.Report(command="delete")

        delete.DeleteHostGoldfishInstance(mock_cfg, instance_name,
                                          "user", "key_path", delete_report)
        mock_console.assert_called_with("192.0.2.1", 5554, "user",
                                        "key_path", "extra args")
        self.assertEqual(delete_report.status, "FAIL")
        self.assertEqual(len(delete_report.errors), 1)

    @mock.patch.object(delete, "DeleteInstances", return_value="")
    @mock.patch.object(delete, "ResetLocalInstanceLockByName")
    @mock.patch.object(delete, "DeleteHostGoldfishInstance")
    @mock.patch.object(delete, "DeleteRemoteInstances", return_value="")
    def testDeleteInstanceByNames(self, mock_delete_remote_ins,
                                  mock_delete_remote_host_gf, mock_reset_lock,
                                  mock_delete_local_ins):
        """test DeleteInstanceByNames."""
        cfg = mock.Mock()
        # Test delete local instances.
        instances = ["local-instance-1", "local-instance-2"]
        mock_local_ins = mock.Mock()
        mock_local_ins.name = "local-instance-1"
        self.Patch(list_instances, "GetLocalInstancesByNames",
                   return_value=[mock_local_ins])
        delete.DeleteInstanceByNames(cfg, instances, None, None)
        mock_delete_local_ins.assert_called_with(cfg, [mock_local_ins])
        mock_reset_lock.assert_called_with("local-instance-2", mock.ANY)

        # Test delete remote host instances.
        instances = ["host-goldfish-192.0.2.1-5554-123456-sdk_x86_64-sdk"]
        delete.DeleteInstanceByNames(cfg, instances, "user", "key")
        mock_delete_remote_host_gf.assert_called_with(
            cfg, instances[0], "user", "key", mock.ANY)

        # Test delete remote instances.
        instances = ["ins-id1-cf-x86-phone-userdebug",
                     "ins-id2-cf-x86-phone-userdebug"]
        delete.DeleteInstanceByNames(cfg, instances, None, None)
        mock_delete_remote_ins.assert_called()

    @mock.patch.object(oxygen_client.OxygenClient, "ReleaseDevice")
    def testReleaseOxygenDevice(self, mock_release):
        """test ReleaseOxygenDevice"""
        cfg = mock.Mock()
        cfg.oxygen_client = "oxygen_client"
        ip = "0.0.0.0"
        # Raise exception for multiple instances
        instances = ["local-instance-1", "local-instance-2"]
        self.assertRaises(errors.CommandArgError, delete._ReleaseOxygenDevice, cfg, instances, ip)

        # Test release device with oxygen client
        instances = ["local-instance-1"]
        delete._ReleaseOxygenDevice(cfg, instances, ip)
        mock_release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
