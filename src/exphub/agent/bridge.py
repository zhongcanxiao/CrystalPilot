"""Bidirectional parameter bridge between the Agent and CrystalPilot models.

Agent → UI:  ``apply_agent_config`` takes the agent's flat config_state dict
             and writes matching fields into the Pydantic sub-models, then
             pushes the updated models into the Trame view via their bindings.

UI → Agent:  ``snapshot_models`` reads current Pydantic model values and
             returns a flat dict the agent can use as its config_state.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, get_args, get_origin

from pydantic import BaseModel

from ..core.beamline import active_technique

logger = logging.getLogger(__name__)


def bridged_submodels() -> tuple[str, ...]:
    """Sub-model attribute names on MainModel the agent reads and writes.

    Sourced from the active technique's manifest (was a module-level constant).
    Call this in mvvm_factory / view_models.chat instead of re-listing names.
    Returns an empty tuple if no technique is resolvable (e.g. very early in
    startup, or in isolated unit tests that register no beamline).
    """
    try:
        return active_technique().bridged_submodels
    except Exception:
        return ()


def field_owner() -> dict[str, str]:
    """Authoritative sub-model for fields that appear in several sub-models.

    Sourced from the active technique's manifest. The listed sub-model is the
    authoritative source: it wins during snapshot and is written first.
    """
    try:
        return active_technique().field_owner
    except Exception:
        return {}


def _coerce_list_field(model_cls: type[BaseModel], field_name: str, value: Any) -> Any:
    """Coerce *value* to ``List[T]`` if the field annotation requires it.

    When the agent sets a ``List[BaseModel]`` field (e.g. ``angle_list_pd``)
    via a list of plain dicts, Pydantic won't auto-convert without
    ``validate_assignment=True``.  This helper converts each dict element to
    the declared item type explicitly.
    """
    if not isinstance(value, list):
        return value
    field = model_cls.model_fields.get(field_name)
    if field is None or get_origin(field.annotation) is not list:
        return value
    args = get_args(field.annotation)
    if not args:
        return value
    item_cls = args[0]
    if not (isinstance(item_cls, type) and issubclass(item_cls, BaseModel)):
        return value
    return [item_cls(**item) if isinstance(item, dict) else item for item in value]


def snapshot_models(main_model: BaseModel) -> Dict[str, Any]:
    """Return a flat dict of all bridged fields from the current model state.

    Field names are kept as-is (e.g. ``ipts_number``, ``crystalsystem``).

    When a field name appears in multiple sub-models, ``FIELD_OWNER``
    determines which sub-model is authoritative.  For any other
    collision the first sub-model in ``BRIDGED_SUBMODELS`` wins and a
    warning is logged.
    """
    flat: Dict[str, Any] = {}
    # Track which sub-model contributed each field (for collision detection)
    _source: Dict[str, str] = {}
    owners = field_owner()

    for attr_name in bridged_submodels():
        sub = getattr(main_model, attr_name, None)
        if sub is None:
            continue
        for field_name in type(sub).model_fields:
            val = getattr(sub, field_name, None)
            if isinstance(val, BaseModel):
                # Expand the `options` sub-model so option lists are visible
                # in the snapshot (e.g. instrument_list, crystalsystem_list).
                if field_name == "options":
                    for opt_field in type(val).model_fields:
                        flat[opt_field] = getattr(val, opt_field, None)
                continue

            if field_name in flat:
                # Collision: field already set by an earlier sub-model.
                owner = owners.get(field_name)
                if owner and owner == attr_name:
                    # This sub-model is the explicit owner — overwrite.
                    flat[field_name] = val
                    _source[field_name] = attr_name
                elif owner:
                    # Another sub-model is the explicit owner — skip.
                    pass
                else:
                    # No explicit owner — first-write wins; log warning.
                    logger.debug(
                        "snapshot: field %r exists in both %s and %s — keeping value from %s",
                        field_name,
                        _source[field_name],
                        attr_name,
                        _source[field_name],
                    )
            else:
                flat[field_name] = val
                _source[field_name] = attr_name
    return flat


def apply_agent_config(
    config_state: Dict[str, Any],
    main_model: BaseModel,
    bindings: Dict[str, Any],
) -> tuple[list[str], dict[str, str]]:
    """Write agent config_state values into the matching Pydantic sub-models.

    Parameters
    ----------
    config_state
        Flat dict from the agent (``{field_name: value}``).
    main_model
        The ``MainModel`` instance.
    bindings
        Mapping of sub-model attribute name → its ``TrameBinding``.

    Returns
    -------
    updated : list[str]
        Names of fields that were successfully written to the model.
    errors : dict[str, str]
        Mapping of ``field_name → error message`` for fields that failed
        Pydantic validation. The caller should surface these to the agent.
    """
    updated: list[str] = []
    errors: dict[str, str] = {}

    for attr_name in bridged_submodels():
        sub = getattr(main_model, attr_name, None)
        if sub is None:
            continue
        bind = bindings.get(attr_name)
        dirty = False

        for field_name in type(sub).model_fields:
            if field_name not in config_state:
                continue
            new_val = config_state[field_name]
            old_val = getattr(sub, field_name, None)
            if new_val == old_val:
                continue
            try:
                new_val = _coerce_list_field(type(sub), field_name, new_val)
                setattr(sub, field_name, new_val)
                updated.append(field_name)
                dirty = True
                logger.debug(f"[Bridge] SET {attr_name}.{field_name} = {new_val!r} (was {old_val!r})")
            except Exception as exc:
                errors[field_name] = str(exc)
                logger.warning(f"[Bridge] FAIL {attr_name}.{field_name}: {exc}")
                logger.warning("bridge: failed to set %s.%s: %s", attr_name, field_name, exc)

        if dirty and bind is not None:
            try:
                bind.update_in_view(sub)
                logger.debug(f"[Bridge] Pushed {attr_name} to view")
            except Exception as exc:
                logger.warning(f"[Bridge] PUSH FAILED {attr_name}: {exc}")
                logger.warning("bridge: failed to push %s to view: %s", attr_name, exc)

    return updated, errors


def write_single_field(
    field_name: str,
    value: Any,
    main_model: BaseModel,
    bindings: Dict[str, Any],
) -> tuple[bool, str]:
    """Write a single field to the live Pydantic model and push to view.

    Returns ``(True, "")`` on success, ``(False, error_message)`` on failure.
    Used as the ``write_through_fn`` callback so the agent's writes are
    immediately visible to subsequent tool calls within the same turn.

    Respects ``FIELD_OWNER``: if the field has an explicit owner, only
    that sub-model is written to.
    """
    owner = field_owner().get(field_name)
    search_order = bridged_submodels()
    if owner:
        # Put the owner first so it gets written to preferentially
        search_order = (owner,) + tuple(n for n in search_order if n != owner)

    for attr_name in search_order:
        sub = getattr(main_model, attr_name, None)
        if sub is None:
            continue
        if field_name not in type(sub).model_fields:
            continue
        try:
            new_val = _coerce_list_field(type(sub), field_name, value)
            setattr(sub, field_name, new_val)
        except Exception as exc:
            return False, str(exc)

        bind = bindings.get(attr_name)
        if bind is not None:
            try:
                bind.update_in_view(sub)
            except Exception as exc:
                logger.warning("write_single_field: push failed for %s: %s", attr_name, exc)
        return True, ""

    # Field not found in any bridged sub-model
    return True, ""
