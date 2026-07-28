"""Beamline plug-in contract.

A concrete beamline populates a :class:`BeamlineSpec`. Everything downstream
(PV catalog, path resolver, agent prompt assembler, tab manifest) reads from
this single object so adding a new beamline never requires editing the
framework.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GoniometerSpec(BaseModel):
    """Sample-environment rotation stack."""

    type: Literal[
        "ambient_2axis",
        "cryo_1axis",
        "eulerian_4axis",
        "other",
    ] = "ambient_2axis"
    angle_pvs: dict[str, str] = Field(
        default_factory=dict,
        description='Axis name → EPICS PV. E.g. {"omega": "BL12:Mot:goniokm:omega"}',
    )
    ramp_pvs: dict[str, str] = Field(
        default_factory=dict,
        description="Temperature-ramp PVs (start/end/rate/soak/run); optional.",
    )
    charge_pv: str = Field(
        default="",
        description='Detector charge threshold PV used for "wait_for=PCharge" rows.',
    )
    angle_columns_order: list[str] = Field(
        default_factory=list,
        description="Display order of axes in the plan table.",
    )


class DetectorSpec(BaseModel):
    """Area-detector description shared across technique families.

    Cross-technique fields only — every neutron instrument has a detector
    layout and beam-monitor PVs. Single-crystal-specific operator-screen
    assets (the Phoebus ``.bob`` screen + extra-subscribe PVs) live on
    :class:`SingleCrystalConfig`, not here.
    """

    detector_layout: str = "generic"
    pixel_dims: tuple[int, int] | None = None
    monitor_pvs: dict[str, str] = Field(
        default_factory=dict,
        description="Named beam-monitor PVs for status widgets. "
        'Common keys: "proton_charge", "beam_power", "wavelength".',
    )


class MantidSpec(BaseModel):
    """Mantid-side defaults for live reduction and peak finding."""

    instrument_name: str = ""
    wavelength_min: float = 0.0
    wavelength_max: float = 0.0
    default_max_q: float = 10.0
    default_tolerance: float = 0.12
    default_num_peaks_to_find: int = 200


class PathsSpec(BaseModel):
    """File-system roots; everything is composed from these."""

    shared_root: str = ""
    eic_dropbox: str = ""
    autoreduce_subdir: str = "shared/autoreduce"
    live_monitor_subdir: str = "shared/CrystalPilot/live-data-monitoring"


class EICSpec(BaseModel):
    """Per-beamline EIC (Experiment Interface Controller) connection settings."""

    beamline_code: str = ""
    is_simulation_default: bool = False
    supports_simulation: bool = True
    write_scope: list[str] = Field(default_factory=lambda: ["EIC:write"])
    # Per-beamline EIC server base URL. Empty string means "let the vendored
    # EICClient derive the URL from ``beamline_code``" (e.g. bl12 ->
    # https://bl12-dassrv1.sns.gov:8443 in production, its dev URL otherwise).
    # A non-empty value is passed to EICClient as ``url_base`` and overrides
    # both that derivation and the token's embedded url_base — set it only for
    # a beamline on a non-standard EIC host.
    server_url: str = ""


class AgentSpec(BaseModel):
    """Per-beamline agent assets."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    context_prompt: Path | None = None
    knowledge_dir: Path | None = None
    presets: dict[str, dict[str, Any]] = Field(default_factory=dict)
    supported_tasks: list[str] = Field(default_factory=lambda: ["experiment_steering", "app_help"])


TabFactory = Callable[[Any], Any]
"""Factory protocol for a beamline-provided tab view.

Called with the active ``MainViewModel`` (or technique view-model in the
post-refactor world) and returns the constructed tab content. Conventionally
a lazy-import closure so spec.py stays import-cheap and per-tab code only
loads when the tab is first navigated to.
"""


class TabOverrides(BaseModel):
    """Plug-in points for per-tab content.

    Each attribute is either ``None`` (use the framework / technique default)
    or a :data:`TabFactory` callable that builds the tab's view. The expected
    usage idiom is the lazy-import closure pattern that
    ``beamlines/topaz/spec.py`` already uses for the ``status`` slot.

    The five slots are technique-neutral and aligned with
    :class:`~exphub.core.beamline.technique.TabKey` (IPTS / LIVE / STEERING /
    STATUS / ANALYSIS) — the framework carries no technique-specific tab
    vocabulary. Each technique manifest maps a ``TabKey`` to the slot name it
    reads via ``tab_override_slots``.

    Per the multi-technique plan (see ``MULTI_TECHNIQUE_PLAN.md``), tabs 1-3
    get a technique-level default when the override is ``None``; tabs 4-5
    fall through to a per-beamline placeholder with optional message +
    external links.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    ipts: Optional[TabFactory] = None
    steering: Optional[TabFactory] = None
    live: Optional[TabFactory] = None
    status: Optional[TabFactory] = None
    analysis: Optional[TabFactory] = None


class SingleCrystalConfig(BaseModel):
    """Technique payload for single-crystal diffraction beamlines.

    Carries everything that *every* single-crystal beamline needs but that has
    no meaning for other technique families (SANS, reflectometry, ...): the
    goniometer stack, Mantid peak-finding defaults, calibration/spectra files,
    the run-title PV, and the Phoebus operator-screen assets. Selected at read
    time through :attr:`BeamlineSpec.single_crystal`, which narrows the
    discriminated union.
    """

    kind: Literal["single_crystal"] = "single_crystal"
    goniometer: GoniometerSpec = Field(default_factory=GoniometerSpec)
    mantid: MantidSpec = Field(default_factory=MantidSpec)
    default_calibration: str = ""
    default_spectra: str = ""
    run_title_pv: str = Field(
        default="",
        description="PV the EIC writes the run title into (e.g. BL12:SMS:RunInfo:RunTitle).",
    )
    bob_screen_path: Path | None = Field(
        default=None,
        description="Phoebus .bob operator screen (relative to the beamline package).",
    )
    bob_macros_path: Path | None = Field(default=None)
    extra_subscribe_pvs: list[str] = Field(
        default_factory=list,
        description="PVs not in the .bob screen that still need a JS subscription.",
    )


class SansConfig(BaseModel):
    """Technique payload for small-angle neutron scattering beamlines.

    Minimal stub for shape parity in P0.5 — no USANS beamline ships yet (that
    lands in P5) and the real reduction/transmission parametrisation is
    specified when the SANS technique skeleton (P4) lands. Every field is an
    optional placeholder until then.
    """

    kind: Literal["sans"] = "sans"
    mantid_instrument_name: str | None = None
    default_q_range: tuple[float, float] | None = None
    transmission_monitor_pv: str | None = None
    live_stream_url: str | None = None
    # Default strategy-CSV path pre-filled into the steering tab's upload field.
    # Blank-safe: a missing path just makes Upload a no-op until the user picks one.
    default_plan_file: str = ""
    # Strategy-CSV column whose value groups rows into one EIC table scan per
    # group. Empty string means "keep the strategy model's default"
    # (``BL1A:sampleholder``). USANS groups by ``BL1A:Mot:Sample:X``: every
    # row sharing a sample-X position is one physical sample / one scan job.
    group_key: str = ""
    # Columns a strategy CSV for this beamline must contain; the pre-submission
    # guidance check reports any that are missing as blocking errors. Empty
    # tuple means "no beamline-specific required set" (only the group column is
    # enforced).
    required_columns: tuple[str, ...] = ()


TechniqueConfig = SingleCrystalConfig | SansConfig
"""Discriminated union of per-technique spec payloads, keyed on ``kind``."""


class BeamlineSpec(BaseModel):
    """One beamline's full description.

    Concrete beamlines live under ``src/exphub/beamlines/<id>/spec.py`` and
    register an instance of this class with :mod:`exphub.core.beamline.registry`.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str
    display_name: str
    facility: Literal["SNS", "HFIR", "ILL", "ISIS", "ESS", "other"] = "SNS"
    target_station: str | None = None
    package_path: Path | None = Field(
        default=None,
        description="Filesystem root of this beamline's plug-in package; resolved automatically when registered.",
    )
    technique: Literal["single_crystal", "sans"] = Field(
        default="single_crystal",
        description="Technique family this beamline belongs to. Kept in step "
        "with ``technique_config.kind`` by a validator; read it for cheap "
        "manifest lookup / selector gating without touching the union.",
    )
    detector: DetectorSpec = Field(default_factory=DetectorSpec)
    paths: PathsSpec = Field(default_factory=PathsSpec)
    eic: EICSpec = Field(default_factory=EICSpec)
    agent: AgentSpec = Field(default_factory=AgentSpec)
    tabs: TabOverrides = Field(default_factory=TabOverrides)
    external_links: dict[str, str] = Field(
        default_factory=dict,
        description='Named external URLs. Common keys: "data_reduction", "operator_screen".',
    )
    placeholder_messages: dict = Field(
        default_factory=dict,
        description="Per-tab fall-through message, keyed by TabKey. Shown by the "
        "PlaceholderTab when a slot has neither a technique default nor a "
        "beamline factory (typically STATUS / ANALYSIS).",
    )
    placeholder_links: dict = Field(
        default_factory=dict,
        description="Per-tab fall-through external links, keyed by TabKey, each a "
        "list of (label, url) pairs rendered as link buttons by PlaceholderTab.",
    )
    optional_tabs: set = Field(
        default_factory=set,
        description="TabKeys this beamline opts into the technique's "
        "``optional_tab_defaults`` for (tabs 4-5 'common-useful' defaults). "
        "A slot with no beamline override that is opted-in here renders the "
        "technique-supplied default instead of a placeholder. Untyped (set of "
        "TabKey) to keep core.beamline.spec free of a technique import cycle.",
    )
    tab_layout: Optional[tuple] = Field(
        default=None,
        description="Per-beamline tab strip shape: an ordered tuple of "
        "``core.beamline.tab_layout.TabGroup`` (each a VTab covering one or more "
        "TabKeys; several keys = one combined tab). ``None`` -> the technique's "
        "default five-tab layout, so beamlines that don't set it are unchanged. "
        "A beamline that merges tabs (e.g. USANS folding IPTS+LIVE+STEERING into "
        "one) sets this. Loosely typed (bare tuple) to keep core.beamline.spec "
        "free of a tab_layout/technique import cycle, mirroring ``optional_tabs``.",
    )
    technique_config: SingleCrystalConfig | SansConfig = Field(
        default_factory=SingleCrystalConfig,
        discriminator="kind",
        description="Per-technique payload. The discriminator narrows the union "
        "at every read site, so a new technique gets a clean config instead of "
        "a wall of Optional fields.",
    )

    @model_validator(mode="after")
    def _sync_technique(self) -> "BeamlineSpec":
        """Keep ``technique`` in step with ``technique_config``.

        ``technique_config.kind`` is authoritative — it is the Pydantic union
        discriminator and is baked into each config subclass — so ``technique``
        is derived from it. Plug-in authors only have to set ``technique_config``.
        """
        if self.technique != self.technique_config.kind:
            self.technique = self.technique_config.kind
        return self

    @property
    def single_crystal(self) -> SingleCrystalConfig:
        """Return the single-crystal technique payload, narrowing the union.

        Raises :class:`TypeError` when the active technique is not
        single-crystal — a clearer failure than an ``AttributeError`` surfacing
        deep in a call site that assumed a goniometer / Mantid config.
        """
        cfg = self.technique_config
        if not isinstance(cfg, SingleCrystalConfig):
            raise TypeError(
                f"Beamline {self.id!r} has technique {self.technique!r}; its "
                f"technique_config is {type(cfg).__name__}, not SingleCrystalConfig."
            )
        return cfg

    @property
    def mantid_instrument_name(self) -> str:
        """Mantid facility instrument name, resolved technique-neutrally.

        Each technique config stores the instrument name in its own field
        (single-crystal under ``mantid.instrument_name``, SANS under
        ``mantid_instrument_name``); this property hides that shape difference so
        framework code can map instruments without reaching into a specific
        technique. Returns ``""`` when unset.
        """
        cfg = self.technique_config
        if isinstance(cfg, SingleCrystalConfig):
            return cfg.mantid.instrument_name or ""
        if isinstance(cfg, SansConfig):
            return cfg.mantid_instrument_name or ""
        return ""

    def resolve(self, relative: Path) -> Path:
        """Resolve a path declared in this spec against the beamline package root."""
        if relative.is_absolute() or self.package_path is None:
            return relative
        return self.package_path / relative
