"""USANS beamline spec — ultra-small-angle neutron scattering at SNS BL-1A.

This is the first ``technique="sans"`` beamline plug-in shipped with ExpHub
(every other shipped beamline is single-crystal). Adding it required zero edits
to framework code (``core/``, ``app/``, ``agent/``): the beamline registry
auto-discovers this package via ``beamlines/__init__.py`` and the SANS technique
manifest (``techniques/sans/``) supplies the tab shapes, root model, steering
VM, agent phases, and action verbs. This spec only contributes per-instrument
parameters (paths, EIC server) plus the STATUS / ANALYSIS placeholder content,
since USANS ships no STATUS/ANALYSIS tab views yet.

PROVISIONAL VALUES — every real PV / URL below is a placeholder pending the BL-1A
beamline scientist. They are called out inline so they are easy to find and
replace when integrating against the live BL-1A IOC / EIC server:

  - ``eic.server_url`` — empty: the EIC client derives the standard BL-1A
    endpoint from ``beamline_code`` (``https://bl1a-dassrv1.sns.gov:8443`` in
    production). Set it only if BL-1A uses a non-standard EIC host.
  - ``technique_config`` (``SansConfig``) — ``mantid_instrument_name`` is the
    Mantid USANS facility name; reduction/transmission PVs and the live-stream
    URL are ``None`` (unknown, documented as provisional).
  - No real run-control / detector PVs are wired: USANS has no operator ``.bob``
    screen here and no ``extra_subscribe_pvs``, so the app subscribes to nothing
    extra. Add them when the BL-1A PV catalog is known.
"""

from __future__ import annotations

from pathlib import Path

from ...core.beamline import (
    AgentSpec,
    BeamlineSpec,
    DetectorSpec,
    EICSpec,
    PathsSpec,
    SansConfig,
    TabGroup,
    TabKey,
    register,
)

USANS = BeamlineSpec(
    id="usans",
    display_name="USANS (BL-1A)",
    facility="SNS",
    target_station="TS-1",
    # technique is derived from technique_config.kind ("sans") by the spec
    # validator; set here for readability.
    technique="sans",
    detector=DetectorSpec(
        # USANS is a Bonse-Hart double-crystal instrument, not an area detector;
        # "usans_bonse_hart" is a descriptive layout tag. Monitor PVs unknown
        # (provisional) — left empty until the BL-1A PV catalog is available.
        detector_layout="usans_bonse_hart",
        pixel_dims=None,
        monitor_pvs={},
    ),
    paths=PathsSpec(
        # Shared analysis root per DECISION DEFAULTS.
        shared_root="/SNS/USANS",
        # EIC dropbox path unknown for USANS (provisional) — left empty; the EIC
        # submit path only needs it for single-crystal-style dropbox writes.
        eic_dropbox="",
    ),
    eic=EICSpec(
        # beamline_code "bl1a" is known to the vendored EICClient's SNS beamline
        # table, so an empty server_url lets it derive the standard endpoint
        # (https://bl1a-dassrv1.sns.gov:8443 in production, the dev URL
        # otherwise). Set server_url only if BL-1A turns out to sit on a
        # non-standard EIC host.
        beamline_code="bl1a",
        is_simulation_default=False,
        server_url="",
    ),
    external_links={
        # Mantid USANS reduction documentation (web). Provisional pointer.
        "data_reduction": "https://docs.mantidproject.org/nightly/techniques/USANS.html",
    },
    # USANS folds the three workflow tabs (IPTS info, I(Q) reduction, experiment
    # steering) into one scrollable "Experiment Setup & Steering" tab; STATUS and
    # ANALYSIS stay as their own (placeholder) tabs. The combined tab keeps id 1,
    # so agent / SANS-phase navigation to IPTS / LIVE / STEERING all land on it.
    # Other beamlines leave tab_layout=None and keep the default five-tab layout
    # (see core/beamline/tab_layout.py).
    tab_layout=(
        TabGroup(id=1, label="Experiment Setup & Steering", covers=(TabKey.IPTS, TabKey.LIVE, TabKey.STEERING)),
        TabGroup(id=5, label="Instrument Status", covers=(TabKey.STATUS,)),
        TabGroup(id=6, label="Data Analysis", covers=(TabKey.ANALYSIS,)),
    ),
    technique_config=SansConfig(
        # Mantid facility instrument name for USANS at SNS.
        mantid_instrument_name="USANS",
        # Reduction Q-range, transmission monitor PV, and live-stream URL are
        # unknown for USANS — left as None (provisional) per DECISION DEFAULTS.
        default_q_range=None,
        transmission_monitor_pv=None,
        live_stream_url=None,
        # Pre-fill the strategy-upload field with the USANS example plan. Blank-safe
        # if the path is absent (Upload just no-ops until the user picks a file).
        default_plan_file="/SNS/TOPAZ/shared/CrystalPilot/code/usans/strategy.csv",
        # USANS strategy CSVs group rows by Title: every row sharing a Title is
        # one EIC table scan (the scan's headers/rows are the CSV verbatim).
        group_key="Title",
        # The BL-1A strategy-CSV column set (instrument-scientist specified).
        # Missing columns are blocking guidance errors at upload/submit time.
        required_columns=(
            "Title",
            "Comment",
            "BL1A:Mot:Sample:X",
            "BL1A:Mot:ARN",
            "BL1A:CS:Scan:USANS1:Counts",
        ),
    ),
    agent=AgentSpec(
        context_prompt=Path("prompts/context.md"),
        knowledge_dir=Path("knowledge"),
        # No SANS Mantid pipeline yet, so no peak-finding-style presets; the
        # I(Q) reduction model exposes a "TBD" prediction dropdown (DECISION
        # DEFAULTS). Tasks: USANS users steer the instrument and (eventually)
        # process I(Q) — app_help is always relevant.
        presets={},
        supported_tasks=["experiment_steering", "app_help"],
    ),
    # USANS ships no STATUS / ANALYSIS tab views yet, and the SANS technique has
    # no default for those slots, so both fall through to a PlaceholderTab. The
    # message + links below drive that placeholder, pointing users at the
    # appropriate Mantid GUI / web reduction tools until real tabs land.
    placeholder_messages={
        TabKey.STATUS: (
            "Instrument Status is not yet wired for USANS (BL-1A). Monitor the "
            "beamline through the SNS status dashboard or the Mantid live-data "
            "tools below. (Real BL-1A status PVs are TBD.)"
        ),
        TabKey.ANALYSIS: (
            "USANS data analysis is not yet integrated into CrystalPilot. Reduce "
            "and analyse USANS data in MantidWorkbench (TOF-SANS / USANS "
            "reduction) or via the documentation below. (A real Data Analysis "
            "tab is TBD.)"
        ),
    },
    placeholder_links={
        TabKey.STATUS: [
            ("SNS Status", "https://status.sns.ornl.gov"),
            ("Mantid Live Data", "https://docs.mantidproject.org/nightly/concepts/LiveData.html"),
        ],
        TabKey.ANALYSIS: [
            ("MantidWorkbench", "https://www.mantidproject.org/installation/index"),
            ("USANS Reduction Docs", "https://docs.mantidproject.org/nightly/techniques/USANS.html"),
        ],
    },
)

register(USANS)
