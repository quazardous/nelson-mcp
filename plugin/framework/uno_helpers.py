# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Shared UNO UI helpers for dialogs and sidebar."""


def get_optional(root_window, name):
    """Return control by name or None if missing."""
    try:
        return root_window.getControl(name)
    except Exception:
        return None


def is_checkbox_control(ctrl):
    """Return True if the control is a checkbox."""
    if not ctrl:
        return False
    try:
        if ctrl.supportsService("com.sun.star.awt.UnoControlCheckBox"):
            return True
        if hasattr(ctrl, "setState") or hasattr(ctrl, "getState"):
            return True
        if hasattr(ctrl.getModel(), "State"):
            return True
    except Exception:
        pass
    return False


def get_checkbox_state(ctrl):
    """Return checkbox state 0 or 1."""
    if not ctrl:
        return 0
    try:
        if hasattr(ctrl, "getState"):
            return ctrl.getState()
        if hasattr(ctrl.getModel(), "State"):
            return ctrl.getModel().State
    except Exception:
        pass
    return 0


def set_checkbox_state(ctrl, value):
    """Set checkbox state to 0 or 1."""
    if not ctrl:
        return
    try:
        if hasattr(ctrl, "setState"):
            ctrl.setState(value)
        elif hasattr(ctrl.getModel(), "State"):
            ctrl.getModel().State = value
    except Exception:
        pass
