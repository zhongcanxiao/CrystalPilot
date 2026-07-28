"""Technique-family plug-in contract.

A *technique* (single-crystal diffraction, SANS, reflectometry, ...) owns the
*shape* of an experiment: which tabs exist and what they look like, the agent's
phase machine and action verbs, the prompt/RAG corpus, and the root data model.
A *beamline* plugs into exactly one technique and only supplies per-instrument
parameters (PVs, paths) plus optional tab overrides.

This module is the technique-side mirror of :mod:`exphub.core.beamline.spec` /
:mod:`exphub.core.beamline.registry`:

- :class:`TechniqueManifest` — the data a technique package populates.
- :class:`TabKey` — string tab identifiers (replaces the legacy 1/2/3/5/6 ints
  at the manifest + agent layers; the trame dispatcher keeps using ints).
- :class:`PhaseDefinition`, :class:`ActionTool` — the agent-side contract a
  technique declares (consumed once the agent is parametrised in P1.b).
- :func:`register_technique`, :func:`get_technique`, :func:`active_technique` —
  the registry surface, with lazy ``importlib`` discovery of
  ``exphub.techniques.<id>`` on first access.

Per ``MULTI_TECHNIQUE_PLAN.md`` this layer is introduced additively in P1: no
single-crystal code has moved yet, so the single-crystal manifest lazy-imports
the existing views from ``app/views/``.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol

from pydantic import BaseModel, ConfigDict, Field

from ..eic.row_builder import EICRowBuilder
from .spec import TabFactory


class SteeringViewModel(Protocol):
    """Structural contract for a technique steering VM as the app shell sees it.

    The shell never names a technique class: the VM instance comes from the
    manifest's ``steering_vm_factory``, tab content resolves through the
    manifest's tab factories, and agent verbs resolve by ``vm_method`` name.
    The only method the shell itself calls is the deactivation hook.
    """

    def on_deactivate(self) -> None:
        """Quiesce the VM before an inside-technique beamline switch."""


logger = logging.getLogger(__name__)


class TabKey(str, Enum):
    """Stable string identifiers for the five tab slots.

    Replaces the legacy integer tab numbers (1, 2, 3, 5, 6 — note the gap at 4)
    at the manifest and agent layers. The trame ``v_if``/``v_show`` predicates
    in the dispatcher keep addressing tabs by int; translation happens there.
    """

    IPTS = "ipts"
    LIVE = "live"
    STEERING = "steering"
    STATUS = "status"
    ANALYSIS = "analysis"


@dataclass(frozen=True)
class PhaseDefinition:
    """One step of a technique's experiment workflow (for the PhaseManager).

    The agent's ``PhaseManager`` is parametrised from a technique's phase list.
    ``tab`` is the :class:`TabKey` the phase lives on; ``label`` is the phase's
    user-facing name (which may differ from the tab's label — e.g. a "submit"
    phase on the steering tab). ``field_prefixes`` scopes which schema fields
    are relevant while the user is in this phase.
    """

    name: str
    tab: TabKey
    label: str
    description: str
    field_prefixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionTool:
    """A technique-specific agent verb (a UI-action tool exposed to the LLM).

    The manifest declares the verb's LLM-facing ``name``, the ``description``
    shown to the model, the ``vm_method`` attribute resolved against the live
    technique/main view-model at wiring time (the manifest stays import-cheap),
    and the ``success_message`` returned to the agent when the action runs.

    ``requires_confirmation`` marks a verb whose effect is destructive or
    hard-to-reverse (aborting a running scan, submitting to the beamline). Such
    a verb is run through a code-level propose -> user-confirms -> execute gate
    (:class:`exphub.agent.confirmation.ConfirmationGate`) the model cannot
    bypass, rather than executing the moment the model calls it.
    """

    name: str
    vm_method: str
    description: str
    success_message: str = ""
    requires_confirmation: bool = False


class TechniqueManifest(BaseModel):
    """Everything a technique family contributes to the app.

    The single plug-in point for a technique. Beamlines never re-declare any of
    this; they select a technique via :attr:`BeamlineSpec.technique` and, at
    most, override individual tabs through :class:`BeamlineSpec.tabs`.

    Fields populated in P1.a: ``id``, ``display_name``, ``default_tabs`` (tabs
    1-3), ``tab_labels``, ``tab_aliases``, ``bridged_submodels``. The remaining
    agent-side fields are part of the locked contract but are wired to their
    consumers in P1.b (phases → PhaseManager, action_tools → chat VM,
    prompts_dir → composer, root_model_factory / eic_row_builder → P1.b/P3a).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    id: str
    display_name: str
    default_tabs: dict[TabKey, TabFactory] = Field(default_factory=dict)
    optional_tab_defaults: dict[TabKey, TabFactory] = Field(default_factory=dict)
    # Maps each TabKey to the BeamlineSpec.tabs (TabOverrides) attribute the
    # dispatcher consults for a per-beamline override of that slot. Lives on the
    # manifest so the app-shell dispatcher never names technique-shaped slots.
    tab_override_slots: dict[TabKey, str] = Field(default_factory=dict)
    tab_labels: dict[TabKey, str] = Field(default_factory=dict)
    tab_aliases: dict[str, TabKey] = Field(default_factory=dict)
    bridged_submodels: tuple[str, ...] = ()
    field_owner: dict[str, str] = Field(default_factory=dict)
    phases: tuple[PhaseDefinition, ...] = ()
    action_tools: tuple[ActionTool, ...] = ()
    prompts_dir: Path | None = None
    knowledge_dir: Path | None = None
    # Per-technique EIC row builder (P3a.2). Translates the technique's
    # strategy-table rows into EIC table-scan submission payloads; the submit
    # path resolves it via ``active_technique().eic_row_builder`` so core/eic
    # stays technique-agnostic. Typed as ``EICRowBuilder`` (a runtime
    # ``Protocol``); ``arbitrary_types_allowed`` lets pydantic hold the
    # builder instance without validating its method signatures.
    eic_row_builder: EICRowBuilder | None = None
    root_model_factory: Callable[[], Any] | None = None
    # Per-technique steering view-model factory (P5 composition seam). Called by
    # ``app/mvvm_factory.create_viewmodels`` as ``factory(root_model, binding,
    # notify_fn=...)`` to build the technique's orchestration VM — the object
    # whose ``*_bind`` attributes back the technique's tabs and whose
    # ``on_deactivate`` the shell calls on an inside-technique switch (see
    # :class:`SteeringViewModel`). Every shipped manifest must set it: the app
    # shell fails fast on ``None`` rather than guessing a technique's VM.
    steering_vm_factory: Callable[..., Any] | None = None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_TECHNIQUE_REGISTRY: dict[str, TechniqueManifest] = {}


def register_technique(manifest: TechniqueManifest) -> TechniqueManifest:
    """Register a technique manifest. Idempotent: re-registering replaces."""
    _TECHNIQUE_REGISTRY[manifest.id] = manifest
    logger.info("Registered technique %r", manifest.id)
    return manifest


def get_technique(technique_id: str) -> TechniqueManifest:
    """Look up a technique manifest, lazily importing its package on first use.

    Discovery model mirrors the beamline registry: importing
    ``exphub.techniques.<id>`` triggers that package's ``register_technique``
    call. Raises :class:`KeyError` if the package is missing or doesn't register.
    """
    if technique_id not in _TECHNIQUE_REGISTRY:
        try:
            importlib.import_module(f"exphub.techniques.{technique_id}")
        except ModuleNotFoundError as exc:
            raise KeyError(
                f"Technique {technique_id!r} not registered and exphub.techniques.{technique_id} is not importable."
            ) from exc
    if technique_id not in _TECHNIQUE_REGISTRY:
        raise KeyError(
            f"Importing exphub.techniques.{technique_id} did not register a "
            f"manifest. Known: {sorted(_TECHNIQUE_REGISTRY)}"
        )
    return _TECHNIQUE_REGISTRY[technique_id]


def list_technique_ids() -> list[str]:
    """Return the ids of every already-registered technique (no discovery)."""
    return list(_TECHNIQUE_REGISTRY)


def active_technique() -> TechniqueManifest:
    """Return the manifest for the active beamline's technique family."""
    from .registry import active

    return get_technique(active().technique)


def _reset_for_tests() -> None:
    """Test-only helper. Clear registry state and drop cached technique modules.

    Registration happens as a side effect of importing ``exphub.techniques.<id>``.
    Python caches that module in ``sys.modules``, so clearing the registry alone
    would leave lazy re-discovery broken (a re-import returns the cached module
    without re-running its ``register_technique`` call). Evicting the cached
    modules makes the next :func:`get_technique` import re-register cleanly.
    """
    import sys

    _TECHNIQUE_REGISTRY.clear()
    for name in [m for m in sys.modules if m.startswith("exphub.techniques.")]:
        del sys.modules[name]


__all__ = [
    "ActionTool",
    "PhaseDefinition",
    "TabKey",
    "TechniqueManifest",
    "active_technique",
    "get_technique",
    "list_technique_ids",
    "register_technique",
]
