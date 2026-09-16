# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Helpers for tools that merge several operations behind one name.

Several former tools that differed only by verb (``add_cell_comment``,
``delete_cell_comment``, ``list_cell_comments``) collapse into one tool
taking an ``action``. The implementations are kept as classes with
``name = None`` — invisible to discovery — and a thin dispatcher routes
to them, so the merge never rewrites working logic.
"""


def merged_parameters(impl_map, action_description, extra=None,
                      default_action=None):
    """Build the dispatcher's JSON Schema from its implementations.

    The union of every implementation's properties, plus the ``action``
    selector. Only ``action`` is required: which of the other parameters
    are needed depends on the action chosen, which JSON Schema cannot
    express without oneOf/if-then, so each implementation keeps checking
    its own arguments and returns a plain error when one is missing.
    """
    action = {
        "type": "string",
        "enum": list(impl_map),
        "description": action_description,
    }
    props = {"action": action}
    for cls in impl_map.values():
        schema = getattr(cls, "parameters", None) or {}
        for key, spec in (schema.get("properties") or {}).items():
            props.setdefault(key, spec)
    if extra:
        props.update(extra)
    return {
        "type": "object",
        "properties": props,
        "required": [] if default_action else ["action"],
    }


def dispatch(impl_map, ctx, action, kwargs):
    """Run the implementation registered for *action*."""
    impl = impl_map.get(action)
    if impl is None:
        return {
            "status": "error",
            "code": "invalid_params",
            "message": "Unknown action '%s'. Expected one of: %s"
                       % (action, ", ".join(impl_map)),
            "retryable": False,
        }
    accepted = set(((getattr(impl, "parameters", None) or {})
                    .get("properties") or {}))
    foreign = sorted(k for k in kwargs if k not in accepted
                     and not k.startswith("_"))
    if foreign:
        # The merged schema advertises every action's parameters, so a
        # parameter of another action passed validation and was silently
        # dropped (has_legend on calc_chart create, #2641).
        owners = {}
        for name, other in impl_map.items():
            props = (getattr(other, "parameters", None) or {}).get(
                "properties") or {}
            for key in foreign:
                if key in props:
                    owners.setdefault(key, []).append(name)
        detail = "; ".join(
            "%s belongs to %s" % (k, ", ".join(owners[k])) if k in owners
            else "%s is not a parameter of any action" % k
            for k in foreign)
        return {
            "status": "error",
            "code": "invalid_params",
            "message": "Not a parameter of action '%s': %s (%s). It accepts: "
                       "%s." % (action, ", ".join(foreign), detail,
                                ", ".join(sorted(accepted)) or "nothing"),
            "retryable": False,
        }
    return impl().execute(ctx, **kwargs)
