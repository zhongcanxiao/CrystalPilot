"""TOPAZ beamline spec — single-crystal diffractometer at SNS BL-12.

Values consolidated from the pre-refactor codebase:
  - PVs from former ``app/models/gonio_pvs.py`` and ``views/main_view.py``
  - File paths from former ``models/temporal_analysis.py`` and ``experiment_info.py``
  - Mantid defaults from former ``agent/constants.py:EXPERIMENT_PRESETS["topaz_standard"]``
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...core.beamline import (
    AgentSpec,
    BeamlineSpec,
    DetectorSpec,
    EICSpec,
    GoniometerSpec,
    MantidSpec,
    PathsSpec,
    SingleCrystalConfig,
    TabKey,
    TabOverrides,
    register,
)

if TYPE_CHECKING:
    from .tabs.css_status import CSSStatusView


def _build_css_status(view_model: Any) -> CSSStatusView:
    """Lazy factory — avoids importing the app layer during spec registration."""
    from .tabs.css_status import CSSStatusView

    return CSSStatusView(view_model)


TOPAZ_USER_PANEL_PVS: tuple[str, ...] = (
    "BL12:CS:IPTS",
    "BL12:CS:IPTS:Title",
    "BL12:CS:ITEMS",
    "BL12:CS:ITEMS:Name",
    "BL12:SMS:RunInfo:RunTitle",
    "BL12:AR:Sequence:Name",
    "BL12:CS:RunControl:LastRunNumber",
    "BL12:CS:RunControl:StateEnum",
    "BL12:CS:RunControl:RunTimer",
    "BL12:CS:RunControl:Pause",
    "BL12:CS:Scan:Active",
    "BL12:CS:Scan:Status",
    "BL12:CS:Scan:Progress",
    "BL12:CS:Scan:Finish",
    "BL12:CS:Scan:State",
    "BL12:CS:Scan:Alarm",
    "BL12:Det:TH:BL:Lambda",
    "BL12:Det:TH:BL:Frequency",
    "PPS_BMLN:BL12:ShtrOpen",
)


TOPAZ = BeamlineSpec(
    id="topaz",
    display_name="TOPAZ (SNS BL-12)",
    facility="SNS",
    target_station="TS-1",
    technique="single_crystal",
    detector=DetectorSpec(
        detector_layout="adned_2d_4x4",
        pixel_dims=(1105, 1105),
        monitor_pvs={
            "proton_charge": "BL12:Det:PCharge:C",
            "beam_power": "BL12:Det:rtdl:BeamPowerAvg",
            "wavelength": "BL12:Det:TH:BL:Lambda",
        },
    ),
    paths=PathsSpec(
        shared_root="/SNS/TOPAZ",
        eic_dropbox="/SNS/groups/topaz/bl_12",
    ),
    eic=EICSpec(
        beamline_code="bl12",
        is_simulation_default=False,
        # Empty: EICClient derives the TOPAZ URL from beamline_code
        # (https://bl12-dassrv1.sns.gov:8443 in production, the dev URL
        # otherwise). A non-empty value here overrides that derivation AND the
        # token's embedded url_base — set only for a non-standard host.
        server_url="",
    ),
    external_links={
        "data_reduction": "https://nova.ornl.gov/launch/nova-neutrons-trame-topaz",
    },
    technique_config=SingleCrystalConfig(
        goniometer=GoniometerSpec(
            type="ambient_2axis",
            angle_pvs={
                "omega": "BL12:Mot:goniokm:omega",
                "phi": "BL12:Mot:goniokm:phi",
            },
            ramp_pvs={
                "start": "BL12:SE:Ramp:Start",
                "end": "BL12:SE:Ramp:End",
                "rate": "BL12:SE:Ramp:Rate",
                "soak": "BL12:SE:Ramp:Soak",
                "run": "BL12:SE:Ramp:Run",
            },
            charge_pv="BL12:Det:PCharge:C",
            angle_columns_order=["omega", "phi"],
        ),
        mantid=MantidSpec(
            instrument_name="TOPAZ",
            wavelength_min=0.4,
            wavelength_max=3.45,
            default_max_q=17.0,
            default_tolerance=0.12,
            default_num_peaks_to_find=500,
        ),
        default_calibration="/SNS/TOPAZ/shared/calibration/2026A_CG/calibration.DetCal",
        default_spectra="/SNS/TOPAZ/shared/calibrations/2019A/Calibration/Spectrum_32751_32758.dat",
        run_title_pv="BL12:SMS:RunInfo:RunTitle",
        bob_screen_path=Path("screens/BL12_ADnED_2D_4x4.bob"),
        bob_macros_path=Path("screens/BL12_ADnED_2D_4x4.macros"),
        extra_subscribe_pvs=list(TOPAZ_USER_PANEL_PVS),
    ),
    agent=AgentSpec(
        context_prompt=Path("prompts/context.md"),
        knowledge_dir=Path("knowledge"),
        presets={
            "topaz_standard": {
                "instrument": "TOPAZ",
                "max_q": 17.0,
                "num_peaks_to_find": 500,
                "tolerance": 0.12,
                "predict_peaks": True,
                "peak_radius": 0.11,
                "bkg_inner_radius": 0.115,
                "bkg_outer_radius": 0.14,
                "pred_min_dspacing": 0.499,
                "pred_max_dspacing": 11.0,
                "pred_min_wavelength": 0.4,
                "pred_max_wavelength": 3.45,
            },
        },
        supported_tasks=["experiment_steering", "data_processing", "app_help"],
    ),
    tabs=TabOverrides(
        status=_build_css_status,
    ),
    # Opt into the single-crystal technique's data-analysis launcher for the
    # ANALYSIS tab (tab 6). Without this the slot falls through to a placeholder.
    optional_tabs={TabKey.ANALYSIS},
)

register(TOPAZ)
