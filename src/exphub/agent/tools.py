"""LangChain tools for the CrystalPilot agent.

Tools are created via ``make_tools(schema_props)`` which closes over the
schema dict — no global mutable state.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Callable, Sequence

from langchain_core.tools import tool

if TYPE_CHECKING:
    from ..core.beamline import ActionTool
    from .confirmation import ConfirmationGate

from .constants import TAB_MAP, TAB_NAMES, get_experiment_presets
from .schema_gen import enrich_schema_with_options
from .utils import coerce_type

logger = logging.getLogger(__name__)


def resolve_param_name(name: str, schema_props: dict[str, dict]) -> tuple[str, dict | None]:
    """Resolve a parameter name with fuzzy matching against schema_props."""
    info = schema_props.get(name)
    if info:
        return name, info
    norm = name.lower().replace(" ", "").replace("-", "").replace("_", "")
    # Exact normalized match
    for prop_key, prop_info in schema_props.items():
        if prop_key.lower().replace("_", "") == norm:
            return prop_key, prop_info
        title = prop_info.get("title", "")
        if title.lower().replace(" ", "").replace("-", "").replace("_", "") == norm:
            return prop_key, prop_info
    # Unique prefix/substring fallback (only if exactly one candidate)
    candidates = [
        (k, v)
        for k, v in schema_props.items()
        if norm in k.lower().replace("_", "") or norm in v.get("title", "").lower().replace(" ", "").replace("_", "")
    ]
    if len(candidates) == 1:
        return candidates[0]
    return name, None


def _make_action_tool(
    spec: "ActionTool",
    fn: "Callable[[], Any] | None",
    gate: "ConfirmationGate | None" = None,
) -> Any:
    """Build a no-arg LangChain tool for a technique :class:`ActionTool` spec.

    *fn* is the live callable (a view-model method) or ``None`` if unavailable.
    The tool's name + description come from the manifest spec.

    When ``spec.requires_confirmation`` is set and a *gate* is supplied, the tool
    never runs *fn* directly: it only proposes the action through the gate and
    returns a ``confirmation_required`` result. The destructive call then runs
    solely from the gate on an explicit user "yes" — the model has no path to
    execute it. Non-confirmation verbs (or no gate) execute immediately.
    """

    def _run() -> dict:
        if spec.requires_confirmation and gate is not None:
            return gate.propose(spec.name, fn, spec.success_message)
        if fn is None:
            return {"error": f"{spec.name} action is not available in this session."}
        try:
            result = fn()
        except Exception as exc:
            return {"error": str(exc)}
        # An action that returns a non-empty string reports its real outcome
        # (e.g. a guidance-blocked submit) instead of the canned success line.
        if isinstance(result, str) and result:
            return {"status": "ok", "message": result}
        return {"status": "ok", "message": spec.success_message or f"{spec.name} completed."}

    _run.__name__ = spec.name
    _run.__doc__ = spec.description or f"Run the {spec.name} action."
    return tool(_run)


def make_tools(
    schema_props: dict[str, dict],
    snapshot_fn: "Callable[[], dict] | None" = None,
    nav_fn: "Callable[[int], Any] | None" = None,
    rag: Any = None,
    action_fns: dict | None = None,
    action_tools: "Sequence[ActionTool] | None" = None,
    confirmation_gate: "ConfirmationGate | None" = None,
) -> list:
    """Return a list of LangChain tools bound to *schema_props*.

    Parameters
    ----------
    schema_props:
        Flat ``{field_name: schema_info}`` dict generated from the Pydantic models.
    snapshot_fn:
        Optional zero-argument callable that returns the current flat config dict
        (i.e. ``bridge.snapshot_models`` partially applied with the live model).
        Required for the ``get_parameter`` tool to work at runtime.
    action_tools:
        Optional sequence of :class:`~exphub.core.beamline.technique.ActionTool`
        specs declared by the active technique. One LLM tool is generated per
        spec; its callable is looked up in *action_fns* by ``spec.name``.
    action_fns:
        Optional dict of ``{action_name: callable}`` providing the live callable
        for each technique action tool (resolved by the chat view-model against
        the view-model's methods).
    """
    _actions = action_fns or {}

    @tool
    def set_parameter(parameter_name: str, parameter_value: Any) -> dict:
        """Record a configuration value provided by the user.

        Call this tool whenever the user provides a value for ANY CrystalPilot
        configuration field (experiment info, angle plan, EIC control, etc.).
        """
        logger.debug("set_parameter called: %s = %s", parameter_name, parameter_value)
        return {"parameter_name": parameter_name, "parameter_value": parameter_value}

    @tool
    def get_default_value(parameter_name: str) -> str:
        """Return the schema default for a parameter as a JSON string."""
        resolved, info = resolve_param_name(parameter_name, schema_props)
        return json.dumps({"parameter_name": resolved, "default": (info or {}).get("default")})

    @tool
    def explain_parameter(parameter_name: str) -> str:
        """Return the human-readable description of a parameter from its schema."""
        resolved, info = resolve_param_name(parameter_name, schema_props)
        if info and "description" in info:
            return info["description"]
        if info and "title" in info:
            return f"{info['title']} (no additional description available)."
        return f"Sorry, I don't have a description for '{resolved}'."

    @tool
    def get_parameter(parameter_name: str) -> str:
        """Return the current live value of a configuration parameter from the UI.

        Use this to confirm what is already set before asking the user, or to
        read back a value after setting it.  The response also includes
        ``valid_options`` when the field has a known set of choices.
        """
        if snapshot_fn is None:
            return json.dumps({"parameter_name": parameter_name, "value": None, "error": "snapshot not available"})
        resolved, _ = resolve_param_name(parameter_name, schema_props)
        current = snapshot_fn()
        if resolved not in current:
            known = resolved in schema_props
            msg = "parameter exists in schema but has no bridged value" if known else "unknown parameter"
            return json.dumps({"parameter_name": resolved, "value": None, "error": msg})
        result: dict = {"parameter_name": resolved, "value": current[resolved]}
        # Attach valid choices when available (schema enum or live option list)
        info = schema_props.get(resolved, {})
        if info.get("enum"):
            result["valid_options"] = info["enum"]
        else:
            for suffix in ("_list", "_options"):
                opt_key = resolved + suffix
                opt_val = current.get(opt_key)
                if isinstance(opt_val, list) and opt_val and all(isinstance(v, str) for v in opt_val):
                    result["valid_options"] = opt_val
                    break
        return json.dumps(result, default=str)

    @tool
    def list_parameters(group: str = "") -> str:
        """List all settable configuration parameters.

        Returns a JSON array of objects with ``name``, ``title``, ``type``,
        optional ``description``, and optional ``options`` (valid choices for
        dropdown/select fields).

        Pass a keyword in *group* to filter results by field name or title
        (case-insensitive substring match).  Leave empty to list everything.

        Use this before setting a value to discover valid field names and
        allowed choices.
        """
        # Re-enrich with live option lists so the result reflects current state
        live_props: dict = {}
        for key, info in schema_props.items():
            live_props[key] = dict(info)

        if snapshot_fn is not None:
            snap = snapshot_fn()
            for key, value in snap.items():
                if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
                    continue
                if key.endswith("_list"):
                    field = key[:-5]
                elif key.endswith("_options"):
                    field = key[:-8]
                else:
                    continue
                if field in live_props:
                    live_props[field] = {**live_props[field], "enum": value}

        params = []
        for key, info in live_props.items():
            entry: dict = {
                "name": key,
                "title": info.get("title", key),
                "type": info.get("type", "string"),
            }
            if info.get("enum"):
                entry["options"] = info["enum"]
            if info.get("description"):
                entry["description"] = info["description"]
            params.append(entry)

        if group:
            gl = group.lower()
            params = [p for p in params if gl in p["name"].lower() or gl in p["title"].lower()]

        return json.dumps(params, default=str)

    # ------------------------------------------------------------------ schema refresh

    @tool
    def refresh_schema() -> str:
        """Refresh the agent's knowledge of valid options for dropdown fields.

        Call this after the user changes a field that affects available choices
        (e.g. changing ``crystalsystem`` updates ``centering_list`` and
        ``point_group_list``).

        The agent's in-memory schema is updated in-place so subsequent
        ``set_parameter`` calls immediately validate against the new options.
        Returns a JSON summary listing which fields had their options updated.
        """
        if snapshot_fn is None:
            return json.dumps({"error": "snapshot not available"})
        snap = snapshot_fn()
        enriched = enrich_schema_with_options(schema_props, snap)

        # Update schema_props in-place — same dict reference used by all tools
        # and by Agent.schema_properties, so the change is visible everywhere.
        updated_fields: list[str] = []
        for key, new_info in enriched.items():
            if new_info.get("enum") != schema_props.get(key, {}).get("enum"):
                updated_fields.append(key)
            schema_props[key] = new_info

        return json.dumps({"refreshed_fields": updated_fields, "total_fields": len(schema_props)})

    # ------------------------------------------------------------------ multi-set / presets

    def _validate_multi(params: dict) -> tuple[dict, dict]:
        """Validate a {field: value} dict against schema_props.

        Returns (validated, errors) dicts.  Enum matching is case-insensitive.
        """
        validated: dict = {}
        errors: dict = {}
        for key, raw_value in params.items():
            info = schema_props.get(key)
            if not info:
                errors[key] = "unknown parameter"
                continue
            try:
                value = coerce_type(raw_value, info)
                if info.get("enum") and isinstance(value, str):
                    lc = value.strip().lower()
                    match = next((c for c in info["enum"] if str(c).lower() == lc), None)
                    if match is None:
                        opts = ", ".join(str(c) for c in info["enum"])
                        errors[key] = f"invalid value — choose from: {opts}"
                        continue
                    value = match
                validated[key] = value
            except (ValueError, TypeError) as err:
                errors[key] = str(err)
        return validated, errors

    @tool
    def set_multiple_parameters(parameters: dict) -> dict:
        """Set several configuration parameters in a single call.

        *parameters* is a ``{field_name: value}`` dict.  Each value is
        validated against its schema type and allowed enum values before
        being accepted.  Use this instead of calling ``set_parameter``
        repeatedly when configuring several fields at once.

        Returns ``{"validated": {...}, "errors": {...}}``.
        """
        validated, errors = _validate_multi(parameters)
        return {"validated": validated, "errors": errors}

    @tool
    def apply_preset(preset_name: str) -> dict:
        """Apply a named experiment preset — sets many parameters at once.

        Use ``list_presets`` to discover available preset names.
        Returns ``{"preset_name": ..., "validated": {...}, "errors": {...}}``.
        """
        key = preset_name.strip().lower().replace(" ", "_")
        presets = get_experiment_presets()
        preset = presets.get(key)
        if preset is None:
            available = ", ".join(presets.keys())
            return {"error": f"Unknown preset '{preset_name}'. Available: {available}"}
        validated, errors = _validate_multi(preset)
        return {"preset_name": preset_name, "validated": validated, "errors": errors}

    @tool
    def list_presets() -> str:
        """List all available experiment presets with their parameter values.

        Returns a JSON array of ``{"name": ..., "parameters": {...}}`` objects.
        Use ``apply_preset(name)`` to apply one.
        """
        result = [{"name": name, "parameters": params} for name, params in get_experiment_presets().items()]
        return json.dumps(result, default=str)

    # ------------------------------------------------------------------ angle plan

    @tool
    def get_angle_plan() -> str:
        """Return the current angle plan as a JSON array of runs.

        Each element has: title, comment, phi, omega, wait_for, value, or_time.
        The ``_index`` field gives the 0-based row position; pass it to
        ``delete_run`` to remove that row.
        """
        if snapshot_fn is None:
            return json.dumps({"error": "snapshot not available"})
        current = snapshot_fn()
        rows = current.get("angle_list_pd", [])
        serialized = []
        for i, row in enumerate(rows):
            d = row.model_dump() if hasattr(row, "model_dump") else dict(row)
            d["_index"] = i
            serialized.append(d)
        return json.dumps(serialized, default=str)

    @tool
    def append_run(
        phi: float,
        omega: float,
        title: str = "",
        comment: str = "",
        wait_for: str = "PCharge",
        value: float = 10.0,
        or_time: float = 0.0,
    ) -> dict:
        """Append a new run to the angle plan table.

        *phi* and *omega* are required goniometer angles in degrees.
        The current table is read from the live UI, the new row is appended,
        and the whole updated table is returned for storage.
        """
        current = snapshot_fn() if snapshot_fn is not None else {}
        rows = current.get("angle_list_pd", [])
        serialized = [r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in rows]
        serialized.append(
            {
                "title": title,
                "comment": comment,
                "phi": phi,
                "omega": omega,
                "wait_for": wait_for,
                "value": value,
                "or_time": or_time,
            }
        )
        return {"parameter_name": "angle_list_pd", "parameter_value": serialized}

    @tool
    def edit_run(
        row_index: int,
        phi: float | None = None,
        omega: float | None = None,
        title: str | None = None,
        comment: str | None = None,
        wait_for: str | None = None,
        value: float | None = None,
        or_time: float | None = None,
    ) -> dict:
        """Edit an existing run in the angle plan by its 0-based index.

        Only the fields you provide are updated; omitted fields keep their
        current value.  Use ``get_angle_plan`` first to find the correct
        ``_index`` value and verify current field values.

        Returns the updated full table (or an error dict if the index is out
        of range).
        """
        current = snapshot_fn() if snapshot_fn is not None else {}
        rows = current.get("angle_list_pd", [])
        if row_index < 0 or row_index >= len(rows):
            return {
                "error": f"Row index {row_index} is out of range "
                f"(table has {len(rows)} rows, indices 0–{len(rows) - 1})."
            }

        serialized = []
        for i, row in enumerate(rows):
            d = row.model_dump() if hasattr(row, "model_dump") else dict(row)
            if i == row_index:
                if phi is not None:
                    d["phi"] = phi
                if omega is not None:
                    d["omega"] = omega
                if title is not None:
                    d["title"] = title
                if comment is not None:
                    d["comment"] = comment
                if wait_for is not None:
                    d["wait_for"] = wait_for
                if value is not None:
                    d["value"] = value
                if or_time is not None:
                    d["or_time"] = or_time
            serialized.append(d)
        return {"parameter_name": "angle_list_pd", "parameter_value": serialized}

    @tool
    def delete_run(row_index: int) -> dict:
        """Delete a run from the angle plan by its 0-based index.

        **IMPORTANT:** This is a destructive operation.  Before calling this
        tool, you MUST confirm with the user that they want to delete the
        run.  Show them which run will be deleted (title, phi, omega) and
        ask for explicit confirmation.

        Use ``get_angle_plan`` first to find the correct ``_index`` value.
        Returns the updated table (or an error dict if the index is out of range).
        """
        current = snapshot_fn() if snapshot_fn is not None else {}
        rows = current.get("angle_list_pd", [])
        if row_index < 0 or row_index >= len(rows):
            return {
                "error": f"Row index {row_index} is out of range "
                f"(table has {len(rows)} rows, indices 0–{len(rows) - 1})."
            }
        serialized = []
        for i, row in enumerate(rows):
            if i == row_index:
                continue
            serialized.append(row.model_dump() if hasattr(row, "model_dump") else dict(row))
        return {"parameter_name": "angle_list_pd", "parameter_value": serialized}

    # ------------------------------------------------------------------ tab navigation

    @tool
    def navigate_to_tab(tab_name: str) -> dict:
        """Switch the active tab in the CrystalPilot UI.

        Accepted tab names (case-insensitive; spaces and dashes treated as
        underscores): ``ipts_info`` (1), ``live_data_processing`` (2),
        ``experiment_steering`` (3), ``instrument_status`` (5),
        ``data_analysis`` (6).

        Returns ``{"tab": <number>, "name": <label>}`` on success, or
        ``{"error": ...}`` if the name is not recognised.
        """
        if nav_fn is None:
            return {"error": "Tab navigation is not available in this session."}
        key = tab_name.strip().lower().replace("-", "_").replace(" ", "_")
        tab_number = TAB_MAP.get(key)
        if tab_number is None:
            try:
                tab_number = int(tab_name)
                if tab_number not in TAB_NAMES:
                    raise ValueError
            except ValueError:
                valid = ", ".join(f"{v}={k}" for k, v in TAB_NAMES.items())
                return {"error": f"Unknown tab '{tab_name}'. Valid: {valid}"}
        nav_fn(tab_number)
        return {"tab": tab_number, "name": TAB_NAMES.get(tab_number, f"tab {tab_number}")}

    # ------------------------------------------------------------------ RAG retrieval

    @tool
    def retrieve_docs(query: str) -> str:
        """Answer a general knowledge question from the CrystalPilot knowledge base.

        Call this tool whenever the user asks a question that is NOT about
        setting or reading a configuration parameter.  This includes questions
        about crystallography, neutron diffraction, beamline instruments,
        data reduction concepts, experiment workflow, troubleshooting, or
        any other scientific / procedural topic.

        When in doubt whether a question needs the knowledge base, call this
        tool — it is better to search and find nothing than to guess.

        Returns a synthesized answer from the knowledge base, or a message
        if nothing is found.
        """
        if rag is None:
            return "Knowledge base is not available in this session."
        answer = rag.answer(query)
        return answer

    # ------------------------------------------------------------------ tools

    all_tools = [
        set_parameter,
        get_default_value,
        explain_parameter,
        get_parameter,
        list_parameters,
        refresh_schema,
        set_multiple_parameters,
        apply_preset,
        list_presets,
        get_angle_plan,
        append_run,
        edit_run,
        delete_run,
        navigate_to_tab,
        retrieve_docs,
    ]

    # Technique-specific UI-action tools (submit/authenticate/...): generated
    # from the active technique's manifest rather than hardcoded here, so a new
    # technique declares its own verbs without editing tools.py.
    for spec in action_tools or []:
        all_tools.append(_make_action_tool(spec, _actions.get(spec.name), confirmation_gate))

    return all_tools
