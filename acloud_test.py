#!/usr/bin/python
#
# Copyright 2018 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Main entry point for all of acloud's unittest."""

import logging
import pkgutil
import sys
import unittest


# Needed to silence oauth2client.
# This is a workaround to get rid of below warning message:
# 'No handlers could be found for logger "oauth2client.contrib.multistore_file'
# TODO(b/112803893): Remove this code once bug is fixed.
OAUTH2_LOGGER = logging.getLogger('oauth2client.contrib.multistore_file')
OAUTH2_LOGGER.setLevel(logging.CRITICAL)
OAUTH2_LOGGER.addHandler(logging.FileHandler("/dev/null"))

# Setup logging to be silent so unittests can pass through TF.
ACLOUD_LOGGER = "acloud"
logger = logging.getLogger(ACLOUD_LOGGER)
logger.setLevel(logging.CRITICAL)
logger.addHandler(logging.FileHandler("/dev/null"))


def main():
    """Main unittest entry.

    Args:
        argv: A list of system arguments. (unused)

    Returns:
        0 if success. None-zero if fails.
    """
    test_modules = [
        mod.name
        for mod in pkgutil.walk_packages()
        if mod.name.startswith('acloud') and mod.name.endswith('_test')
    ]

    loader = unittest.defaultTestLoader
    test_suite = loader.loadTestsFromNames(test_modules)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    sys.exit(not result.wasSuccessful())


if __name__ == '__main__':
    main()
