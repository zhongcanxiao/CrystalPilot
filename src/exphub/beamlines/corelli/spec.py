"""CORELLI beamline spec — elastic diffuse-scattering spectrometer at SNS BL-9.

This is the second beamline plug-in shipped with ExpHub. Adding it required
zero edits to framework code (``core/``, ``app/``, ``agent/``) — the registry
auto-discovers this package via ``beamlines/__init__.py``.

PV strings and file paths are placeholders modelled on the TOPAZ layout; swap
in the real values when integrating against the live BL-9 IOC.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core.beamline import (
    AgentSpec,
    BeamlineSpec,
    DetectorSpec,
    EICSpec,
    GoniometerSpec,
    MantidSpec,
    PathsSpec,
    SingleCrystalConfig,
    TabOverrides,
    register,
)


def _build_data_analysis(view_model: Any) -> Any:
    """Lazy factory — avoids importing the app/view layer during registration."""
    from .tabs.data_analysis import build_data_analysis

    return build_data_analysis(view_model)


# A small selection of CORELLI run-info / status PVs that aren't in the main
# .bob screen (analogous to TOPAZ_USER_PANEL_PVS). Placeholders.
CORELLI_USER_PANEL_PVS: tuple[str, ...] = (
    "BL9:CS:IPTS",
    "BL9:CS:IPTS:Title",
    "BL9:SMS:RunInfo:RunTitle",
    "BL9:CS:RunControl:LastRunNumber",
    "BL9:CS:RunControl:StateEnum",
    "BL9:CS:RunControl:RunTimer",
    "BL9:Det:TH:BL:Lambda",
    "BL9:Det:TH:BL:Frequency",
    "PPS_BMLN:BL9:ShtrOpen",
)


CORELLI = BeamlineSpec(
    id="corelli",
    display_name="CORELLI (SNS BL-9)",
    facility="SNS",
    target_station="TS-1",
    technique="single_crystal",
    detector=DetectorSpec(
        detector_layout="corelli_array",
        pixel_dims=None,
        monitor_pvs={
            "proton_charge": "BL9:Det:PCharge:C",
            "beam_power": "BL9:Det:rtdl:BeamPowerAvg",
            "wavelength": "BL9:Det:TH:BL:Lambda",
        },
    ),
    paths=PathsSpec(
        shared_root="/SNS/CORELLI",
        eic_dropbox="/SNS/groups/corelli/bl_9",
    ),
    eic=EICSpec(
        beamline_code="bl9",
        is_simulation_default=False,
        # Empty: EICClient derives the CORELLI URL from beamline_code
        # (https://bl9-dassrv1.sns.gov:8443 in production, the dev URL
        # otherwise). A non-empty value here overrides that derivation AND the
        # token's embedded url_base — set only for a non-standard host.
        server_url="",
    ),
    external_links={},
    technique_config=SingleCrystalConfig(
        goniometer=GoniometerSpec(
            type="ambient_2axis",
            angle_pvs={
                "omega": "BL9:Mot:Sample:omega",
                "phi": "BL9:Mot:Sample:phi",
            },
            ramp_pvs={
                "start": "BL9:SE:Ramp:Start",
                "end": "BL9:SE:Ramp:End",
                "rate": "BL9:SE:Ramp:Rate",
                "soak": "BL9:SE:Ramp:Soak",
                "run": "BL9:SE:Ramp:Run",
            },
            charge_pv="BL9:Det:PCharge:C",
            angle_columns_order=["omega", "phi"],
        ),
        mantid=MantidSpec(
            instrument_name="CORELLI",
            wavelength_min=0.7,
            wavelength_max=2.89,
            default_max_q=14.0,
            default_tolerance=0.15,
            default_num_peaks_to_find=300,
        ),
        default_calibration="",  # set per cycle
        default_spectra="",
        run_title_pv="BL9:SMS:RunInfo:RunTitle",
        bob_screen_path=None,  # No CORELLI .bob shipped yet
        bob_macros_path=None,
        extra_subscribe_pvs=list(CORELLI_USER_PANEL_PVS),
    ),
    agent=AgentSpec(
        context_prompt=Path("prompts/context.md"),
        knowledge_dir=Path("knowledge"),
        presets={
            "corelli_standard": {
                "instrument": "CORELLI",
                "max_q": 14.0,
                "num_peaks_to_find": 300,
                "tolerance": 0.15,
                "predict_peaks": True,
                "peak_radius": 0.13,
                "bkg_inner_radius": 0.135,
                "bkg_outer_radius": 0.16,
                "pred_min_dspacing": 0.5,
                "pred_max_dspacing": 10.0,
                "pred_min_wavelength": 0.7,
                "pred_max_wavelength": 2.89,
            },
        },
        supported_tasks=["experiment_steering", "data_processing", "app_help"],
    ),
    tabs=TabOverrides(
        # CORELLI ships its own Data Analysis (tab 6 / ANALYSIS) factory so the
        # slot renders the real single-crystal launcher instead of regressing to
        # the placeholder. The ANALYSIS slot has no unconditional technique
        # default — only an optional one — so a beamline that wants it must
        # supply this override or opt in via ``optional_tabs``. The status (tab
        # 5 / STATUS) slot is still None → that slot renders the "not configured"
        # placeholder until someone writes beamlines/corelli/tabs/css_status.py.
        analysis=_build_data_analysis,
    ),
)

register(CORELLI)
