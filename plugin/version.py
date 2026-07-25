# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Single source of truth for extension version."""

EXTENSION_VERSION = "0.12.0"
# Optional build tag for patch releases (e.g. "-2", "-rc1").
# Appended to the .oxt filename but NOT to description.xml (LO needs strict semver).
BUILD_TAG = ""
