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
"""Tests for host_setup_runner."""
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest

from unittest import mock

from acloud.internal.lib import driver_test_lib
from acloud.internal.lib import utils
from acloud.setup import setup_common
from acloud.setup.host_setup_runner import AvdPkgInstaller
from acloud.setup.host_setup_runner import CuttlefishCommonPkgInstaller
from acloud.setup.host_setup_runner import CuttlefishHostSetup
from acloud.setup.host_setup_runner import MkcertPkgInstaller


class CuttlefishHostSetupTest(driver_test_lib.BaseDriverTest):
    """Test CuttlsfishHostSetup."""

    LSMOD_OUTPUT = """nvidia_modeset        860160  6 nvidia_drm
module1                12312  1
module2                12312  1
ghash_clmulni_intel    16384  0
aesni_intel           167936  3
aes_x86_64             20480  1 aesni_intel
lrw                    16384  1 aesni_intel"""

    # pylint: disable=invalid-name
    def setUp(self):
        """Set up the test."""
        super().setUp()
        self.CuttlefishHostSetup = CuttlefishHostSetup()

    def testShouldRunFalse(self):
        """Test ShouldRun returns False."""
        self.Patch(CuttlefishHostSetup, "_IsSupportedKvm", return_value=True)
        self.Patch(utils, "CheckUserInGroups", return_value=True)
        self.Patch(CuttlefishHostSetup, "_CheckLoadedModules", return_value=True)
        self.assertFalse(self.CuttlefishHostSetup.ShouldRun())

    def testShouldRunTrue(self):
        """Test ShouldRun returns True."""
        self.Patch(CuttlefishHostSetup, "_IsSupportedKvm", return_value=True)
        # 1. Checking groups fails.
        self.Patch(
            utils, "CheckUserInGroups", return_value=False)
        self.Patch(CuttlefishHostSetup, "_CheckLoadedModules", return_value=True)
        self.assertTrue(self.CuttlefishHostSetup.ShouldRun())

        # 2. Checking modules fails.
        self.Patch(utils, "CheckUserInGroups", return_value=True)
        self.Patch(
            CuttlefishHostSetup, "_CheckLoadedModules", return_value=False)
        self.assertTrue(self.CuttlefishHostSetup.ShouldRun())

        self.Patch(platform, "system", return_value="Mac")
        self.assertFalse(self.CuttlefishHostSetup.ShouldRun())

    # pylint: disable=no-member
    def testRun(self):
        """Test Run."""
        self.Patch(CuttlefishHostSetup, "_IsSupportedKvm", return_value=True)
        self.Patch(CuttlefishHostSetup, "ShouldRun", return_value=True)
        self.Patch(utils, "InteractWithQuestion", return_value="y")
        self.Patch(setup_common, "CheckCmdOutput")
        self.CuttlefishHostSetup.Run()
        setup_common.CheckCmdOutput.assert_called()
        setup_common.CheckCmdOutput.reset_mock()

        self.Patch(utils, "InteractWithQuestion", return_value="n")
        self.CuttlefishHostSetup.Run()
        setup_common.CheckCmdOutput.assert_not_called()

        self.Patch(CuttlefishHostSetup, "_IsSupportedKvm", return_value=False)
        self.Patch(utils, "InteractWithQuestion")
        self.CuttlefishHostSetup.Run()
        utils.InteractWithQuestion.assert_not_called()


    # pylint: disable=protected-access
    def testIsSupportedKvm(self):
        """Test _IsSupportedKvm."""
        fake_success_message = (
            "  QEMU: Checking for hardware virtualization                                 : PASS\n"
            "  QEMU: Checking if device /dev/kvm exists                                   : PASS\n"
            "  QEMU: Checking if device /dev/kvm is accessible                            : PASS\n")
        fake_fail_message = (
            "  QEMU: Checking for hardware virtualization                                 : FAIL"
            "(Only emulated CPUs are available, performance will be significantly limited)\n"
            "  QEMU: Checking if device /dev/vhost-net exists                             : PASS\n"
            "  QEMU: Checking if device /dev/net/tun exists                               : PASS\n")
        popen = mock.Mock(returncode=None)
        popen.poll.return_value = None
        popen.communicate.return_value = (fake_success_message, "stderr")
        self.Patch(subprocess, "Popen", return_value=popen)
        self.assertTrue(self.CuttlefishHostSetup._IsSupportedKvm())

        popen.communicate.return_value = (fake_fail_message, "stderr")
        self.Patch(subprocess, "Popen", return_value=popen)
        self.assertFalse(self.CuttlefishHostSetup._IsSupportedKvm())

    # pylint: disable=protected-access
    def testCheckLoadedModules(self):
        """Test _CheckLoadedModules."""
        self.Patch(
            setup_common, "CheckCmdOutput", return_value=self.LSMOD_OUTPUT)

        # Required modules are all in lsmod should return True.
        self.assertTrue(
            self.CuttlefishHostSetup._CheckLoadedModules(["module1", "module2"]))
        # Required modules are not all in lsmod should return False.
        self.assertFalse(
            self.CuttlefishHostSetup._CheckLoadedModules(["module1", "module3"]))


class AvdPkgInstallerTest(driver_test_lib.BaseDriverTest):
    """Test AvdPkgInstallerTest."""

    # pylint: disable=invalid-name
    def setUp(self):
        """Set up the test."""
        super().setUp()
        self.AvdPkgInstaller = AvdPkgInstaller()

    def testShouldRun(self):
        """Test ShouldRun."""
        self.Patch(platform, "system", return_value="Linux")
        self.assertFalse(self.AvdPkgInstaller.ShouldRun())

    def testShouldNotRun(self):
        """Test ShouldRun should raise error in non-linux os."""
        self.Patch(platform, "system", return_value="Mac")
        self.assertFalse(self.AvdPkgInstaller.ShouldRun())

    # pylint: disable=no-member
    def testRun(self):
        """Test Run."""
        self.Patch(platform, "system", return_value="Linux")
        self.AvdPkgInstaller.PACKAGES = ["pkg1", "pkg2"]
        self.Patch(setup_common, "PackageInstalled", return_value=False)
        self.Patch(utils, "GetUserAnswerYes", return_value=True)
        self.Patch(setup_common, "CheckCmdOutput")
        self.Patch(setup_common, "InstallPackage")
        self.AvdPkgInstaller.Run()
        setup_common.InstallPackage.assert_called()

        self.Patch(utils, "GetUserAnswerYes", return_value=False)
        self.Patch(sys, "exit")
        self.AvdPkgInstaller.Run()
        sys.exit.assert_called_once()


class CuttlefishCommonPkgInstallerTest(driver_test_lib.BaseDriverTest):
    """Test CuttlefishCommonPkgInstallerTest."""

    # pylint: disable=invalid-name
    def setUp(self):
        """Set up the test."""
        super().setUp()
        self.CuttlefishCommonPkgInstaller = CuttlefishCommonPkgInstaller()

    def testShouldRun(self):
        """Test ShouldRun."""
        self.Patch(platform, "system", return_value="Linux")
        self.Patch(setup_common, "PackageInstalled", return_value=False)
        self.assertTrue(self.CuttlefishCommonPkgInstaller.ShouldRun())

        self.Patch(setup_common, "PackageInstalled", return_value=True)
        self.assertFalse(self.CuttlefishCommonPkgInstaller.ShouldRun())

        self.Patch(platform, "system", return_value="Mac")
        self.assertFalse(self.CuttlefishCommonPkgInstaller.ShouldRun())

    # pylint: disable=no-member
    @mock.patch.object(shutil, "rmtree")
    @mock.patch.object(setup_common, "CheckCmdOutput")
    def testRun(self, mock_cmd, mock_rmtree):
        """Test Run."""
        fake_tmp_folder = "/tmp/cf-common"
        self.Patch(tempfile, "mkdtemp", return_value=fake_tmp_folder)
        self.Patch(utils, "GetUserAnswerYes", return_value=True)
        self.Patch(CuttlefishCommonPkgInstaller, "ShouldRun", return_value=True)
        self.CuttlefishCommonPkgInstaller.Run()
        self.assertEqual(mock_cmd.call_count, 1)
        mock_rmtree.assert_called_once_with(fake_tmp_folder)

        self.Patch(utils, "GetUserAnswerYes", return_value=False)
        self.Patch(sys, "exit")
        self.CuttlefishCommonPkgInstaller.Run()
        sys.exit.assert_called_once()


class MkcertPkgInstallerTest(driver_test_lib.BaseDriverTest):
    """Test MkcertPkgInstallerTest."""

    # pylint: disable=invalid-name
    def setUp(self):
        """Set up the test."""
        super().setUp()
        self.MkcertPkgInstaller = MkcertPkgInstaller()

    def testShouldRun(self):
        """Test ShouldRun."""
        self.Patch(platform, "system", return_value="Linux")
        self.Patch(os.path, "exists", return_value=False)
        self.assertTrue(self.MkcertPkgInstaller.ShouldRun())

        self.Patch(os.path, "exists", return_value=True)
        self.assertFalse(self.MkcertPkgInstaller.ShouldRun())

        self.Patch(platform, "system", return_value="Mac")
        self.Patch(os.path, "exists", return_value=False)
        self.assertFalse(self.MkcertPkgInstaller.ShouldRun())

    # pylint: disable=no-member
    @mock.patch.object(setup_common, "CheckCmdOutput")
    def testRun(self, mock_cmd):
        """Test Run."""
        self.Patch(utils, "GetUserAnswerYes", return_value=True)
        self.Patch(MkcertPkgInstaller, "ShouldRun", return_value=True)
        self.Patch(os.path, "isdir", return_value=True)
        self.Patch(os, "mkdir")
        self.Patch(utils, "SetExecutable")
        self.Patch(utils, "CheckOutput")
        self.MkcertPkgInstaller.Run()
        mock_cmd.assert_called_once()

        self.Patch(os.path, "isdir", return_value=False)
        self.MkcertPkgInstaller.Run()
        os.mkdir.assert_called_once()

        self.Patch(utils, "GetUserAnswerYes", return_value=False)
        self.Patch(sys, "exit")
        self.MkcertPkgInstaller.Run()
        sys.exit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
