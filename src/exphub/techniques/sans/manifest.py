"""SANS technique manifest (P4.3).

Declares the tab shapes and agent contract shared by every SANS beamline,
mirroring :mod:`exphub.techniques.single_crystal.manifest`. Importing this
module (via ``exphub.techniques.sans``) registers the SANS
:class:`~exphub.core.beamline.technique.TechniqueManifest`, so
``get_technique("sans")`` discovers it through the lazy-import side effect.

The default tab factories lazy-import the SANS views from
``techniques/sans/views/`` and construct them from the SANS steering VM, exactly
as the single-crystal manifest does. Tabs 4-5 (STATUS, ANALYSIS) have no SANS
default and fall through to a beamline tab or a placeholder (the first real SANS
beamline / USANS ships those in P5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core.beamline.technique import (
    ActionTool,
    TabKey,
    TechniqueManifest,
    register_technique,
)
from .agent.eic_row_builder import SANS_EIC_ROW_BUILDER
from .agent.phases import SANS_PHASES
from .models.root import SansMainModel

# UI-action verbs the agent can trigger. ``vm_method`` is resolved against the
# live SANS steering view-model by the chat VM. SANS has no UB-driven optimizer,
# so there is no "initialize strategy" verb; the rest mirror the shared EIC
# submit/auth/stop surface plus the strategy-CSV upload.
_ACTION_TOOLS = (
    ActionTool(
        name="submit_strategy",
        vm_method="submit_strategy",
        description=(
            "Submit the current SANS strategy table to the EIC for execution. "
            "The table is grouped by the beamline's configured group column "
            "(the sample position BL1A:Mot:Sample:X on USANS; BL1A:sampleholder "
            "on legacy CSVs) and each group is submitted as one EIC table-scan "
            "carrying all of its steps. A "
            "pre-submission guidance check runs first: if it finds blocking "
            "errors the submission is refused and the issues are shown; warnings "
            "are surfaced but allow submission. Check that the strategy is "
            "complete and the EIC settings (token, simulation mode, beamline) are "
            "correct before calling this tool."
        ),
        success_message="SANS strategy submitted to EIC.",
        # Submitting drives the real instrument — route through the
        # propose -> user-confirms -> execute gate (matches the single-crystal
        # submit_angle_plan verb).
        requires_confirmation=True,
    ),
    ActionTool(
        name="export_strategy",
        vm_method="export_strategy",
        description=(
            "Export the current (edited) SANS strategy table to a CSV file at the "
            "path in the export_file field. Writes the columns in their original "
            "order. Set export_file before calling this tool."
        ),
        success_message="SANS strategy exported.",
    ),
    ActionTool(
        name="authenticate_eic",
        vm_method="call_load_token",
        description=(
            "Load the EIC authentication token from the configured token file. "
            "Must be called before submitting a strategy. The token file path "
            "is set in the EIC Control section."
        ),
        success_message="EIC token loaded successfully.",
    ),
    ActionTool(
        name="upload_strategy",
        vm_method="upload_strategy",
        description=(
            "Upload a SANS strategy from the configured CSV file. Reads the "
            "strategy file (set via the plan_file parameter) and populates the "
            "strategy table with the SANS instrument-configuration rows."
        ),
        success_message="Strategy file uploaded and loaded.",
    ),
    ActionTool(
        name="stop_current_run",
        vm_method="stoprun",
        description=(
            "Stop the currently executing EIC scan/run. IMPORTANT: this is a "
            "destructive operation that aborts a running scan — confirm with "
            "the user before calling it. Use when the user wants to stop data "
            "collection early."
        ),
        success_message="Current run stopped.",
        # Aborting a running scan is destructive — gate it exactly like the
        # single-crystal stop_current_run verb.
        requires_confirmation=True,
    ),
)

_TECHNIQUE_DIR = Path(__file__).resolve().parent

# --- default tab factories (lazy-import the SANS views) ---------------------
#
# Each factory takes the active SANS steering view-model and returns the
# constructed tab content, matching the ``TabFactory`` protocol and the same
# construction idiom the single-crystal manifest uses.


def _ipts_tab(view_model: Any) -> Any:
    from .views.ipts_info import SansIptsInfoView

    return SansIptsInfoView(view_model)


def _live_tab(view_model: Any) -> Any:
    from .views.iq_reduction import SansIQReductionView

    return SansIQReductionView(view_model)


def _steering_tab(view_model: Any) -> Any:
    from .views.strategy import SansStrategyView

    return SansStrategyView(view_model)


def _build_steering_vm(model: Any, binding: Any, notify_fn: Any = None) -> Any:
    """Lazy factory for the SANS steering VM (manifest stays import-cheap).

    Called by ``app/mvvm_factory.create_viewmodels`` so the app shell builds the
    SANS orchestration VM without naming any SANS class. Signature mirrors the
    single-crystal steering VM: ``(root_model, binding, notify_fn=...)``.
    """
    from .view_models.steering import SansSteeringViewModel

    return SansSteeringViewModel(model, binding, notify_fn=notify_fn)


SANS = register_technique(
    TechniqueManifest(
        id="sans",
        display_name="Small-Angle Neutron Scattering",
        # Tabs 1-3 are technique defaults; beamlines may override via
        # BeamlineSpec.tabs. Tabs 4-5 (STATUS, ANALYSIS) have no SANS default —
        # they fall through to a beamline tab or a placeholder (USANS ships its
        # own STATUS / ANALYSIS placeholders in P5).
        default_tabs={
            TabKey.IPTS: _ipts_tab,
            TabKey.LIVE: _live_tab,
            TabKey.STEERING: _steering_tab,
        },
        # No "common-useful" tab-4/5 default for SANS yet (the reduction /
        # analysis pipeline is TBD). Beamlines opt into their own or a
        # placeholder.
        optional_tab_defaults={},
        # Which BeamlineSpec.tabs (TabOverrides) field the dispatcher reads for a
        # per-beamline override of each slot. Uses the shared 5-slot
        # TabOverrides field names, which are technique-neutral and TabKey-aligned
        # (ipts/live/steering/status/analysis).
        tab_override_slots={
            TabKey.IPTS: "ipts",
            TabKey.LIVE: "live",
            TabKey.STEERING: "steering",
            TabKey.STATUS: "status",
            TabKey.ANALYSIS: "analysis",
        },
        tab_labels={
            TabKey.IPTS: "IPTS Info",
            TabKey.LIVE: "Live Data",
            TabKey.STEERING: "Experiment Steering",
            TabKey.STATUS: "Instrument Status",
            TabKey.ANALYSIS: "Data Analysis",
        },
        # Natural-language aliases the LLM may use → canonical tab key.
        tab_aliases={
            "ipts_info": TabKey.IPTS,
            "ipts": TabKey.IPTS,
            "iq_reduction": TabKey.LIVE,
            "i(q)_reduction": TabKey.LIVE,
            "reduction": TabKey.LIVE,
            "live_data": TabKey.LIVE,
            "experiment_steering": TabKey.STEERING,
            "strategy": TabKey.STEERING,
            "instrument_status": TabKey.STATUS,
            "data_analysis": TabKey.ANALYSIS,
        },
        # Sub-models the agent bridges onto the schema (the SANS root's sub-model
        # field names — the SANS analogues of the single-crystal set).
        bridged_submodels=("iptsinfo", "strategy", "iqreduction", "eiccontrol"),
        # Authoritative sub-model for fields that appear in more than one.
        field_owner={},
        # Technique-level prompt fragment, inserted between core identity and the
        # beamline context by the 3-layer composer.
        prompts_dir=_TECHNIQUE_DIR / "prompts",
        # SANS experiment phase sequence consumed by the agent's PhaseManager.
        phases=SANS_PHASES,
        # UI-action verbs the agent can trigger (submit/authenticate/upload/stop).
        action_tools=_ACTION_TOOLS,
        # Per-technique EIC row builder (P3a.2 seam): the submit path resolves
        # this via active_technique().eic_row_builder. SANS column layout is
        # provisional (TBD with the SANS scientist).
        eic_row_builder=SANS_EIC_ROW_BUILDER,
        # Contributes the SANS technique sub-model to the composite root.
        root_model_factory=SansMainModel,
        # Builds the SANS steering VM the app shell wires its tabs / chat to.
        steering_vm_factory=_build_steering_vm,
    )
)
