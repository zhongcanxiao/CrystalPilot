"""Per-cycle Mantid pipeline for the live-data tab.

Each function here is one phase of the live reduction loop that used to
live as an inner closure of ``MantidWorkflow.live_data_reduction``. They
mutate the ``wf`` (:class:`MantidWorkflow`) instance in-place — same
external behavior as the closures, just easier to read, test, and slot
new behavior into.

Phases run in strict order:

    run_change_checkpoint     save + clear when run number rolls over
    load_config               LoadIsawDetCal + monitor integration
    refine_ub                 ConvertToMD + FindPeaksMD + FindUBUsingFFT
    integrate_and_predict     IntegrateEllipsoids + PredictPeaks + IndexPeaks
    check_peaks               tally + statistics + selector + append + save
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import mantid.simpleapi as mtdapi
import numpy as np

from ._debug import trace
from .selectors import make_selector

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .workflow import MantidWorkflow


def run_change_checkpoint(wf: "MantidWorkflow") -> None:
    """If the run number changed, save the old run's series + peaks and clear buffers."""
    current_run = mtdapi.mtd["live_event_ws"].getRunNumber()

    trace("=" * 60)
    trace("Getting the first event list")
    current_run_start_time = mtdapi.mtd["live_event_ws"].getRun().startTime().totalNanoseconds() * 1e-9

    if current_run != wf.current_run:
        results = np.column_stack((wf.measure_times, wf.proton_charges, wf.intensity_ratios, wf.rsigs))
        np.savetxt(
            wf.output_path + "live_data_%s_results.csv" % (str(wf.current_run)),
            results,
            delimiter=",",
            header="",
            comments="",
        )
        mtdapi.SaveIsawPeaks(Inputworkspace="live_predict_peaks_ws", Filename=wf.output_path + wf.live_peaks_fname)
        mtdapi.SaveIsawUB(Inputworkspace="live_predict_peaks_ws", Filename=wf.output_path + wf.live_peaks_fname)

        wf.current_run = current_run
        wf.current_run_start_time = current_run_start_time
        wf.proton_charges.clear()
        wf.intensity_ratios.clear()
        wf.rsigs.clear()
        wf.measure_times.clear()
        wf.timeseries_plt = []
        wf.timeseries_data_plt = []
        time.sleep(1)

    wf.update_peak_output_filenames()


def load_config(wf: "MantidWorkflow") -> None:
    """Load the calibration file and integrate the monitor counts."""
    trace("=" * 60)
    trace("Loading the calibration file and monitor data, and integrating the peaks")
    trace("first filterbytime")
    trace("=" * 60)
    mtdapi.LoadIsawDetCal(InputWorkspace="live_event_ws", Filename=wf.calib_fname)
    trace("load isaw detcal", wf.calib_fname)
    trace("second filterbytime")
    trace("=" * 60)
    monitor_ws = mtdapi.mtd["live_event_ws"].getMonitorWorkspace()
    trace("monitorws")
    trace("=" * 60)
    integrated_monitor_ws = mtdapi.Integration(
        InputWorkspace=monitor_ws,
        RangeLower=wf.min_monitor_tof,
        RangeUpper=wf.max_monitor_tof,
        StartWorkspaceIndex=0,
        EndWorkspaceIndex=0,
    )
    trace("int filterbytime")
    trace("=" * 60)
    monitor_count = integrated_monitor_ws.dataY(0)[0]
    logger.debug("%s %s %s %s %s", "\n", wf.current_run, " has integrated monitor count", monitor_count, "\n")

    mtdapi.SetGoniometer(Workspace="live_event_ws", Goniometers="Universal")
    trace("getgonio filterbytime")
    trace("=" * 60)
    trace("3rd filterbytime")
    trace("=" * 60)


def refine_ub(wf: "MantidWorkflow") -> None:
    """Convert events to MD, find peaks, find UB by FFT."""
    mtdapi.CloneWorkspace(InputWorkspace="live_event_ws", OutputWorkspace="live_event_ws_peak")
    mtdapi.ConvertToMD(
        InputWorkspace="live_event_ws_peak",
        QDimensions="Q3D",
        dEAnalysisMode="Elastic",
        Q3DFrames="Q_sample",
        QConversionScales="Q in A^-1",
        LorentzCorrection="1",
        Uproj="1,0,0",
        Vproj="0,1,0",
        Wproj="0,0,1",
        OutputWorkspace="live_event_md_Qsample",
        MinValues="-12,-12,-12",
        MaxValues="12,12,12",
    )
    trace("4 filterbytime")
    trace("=" * 60)

    mtdapi.FindPeaksMD(
        InputWorkspace="live_event_md_Qsample",
        PeakDistanceThreshold=0.6,
        MaxPeaks=1000,
        DensityThresholdFactor=100,
        OutputWorkspace="live_peaks_ws",
        EdgePixels=18,
    )
    trace("5 filterbytime")
    trace("=" * 60)

    try:
        mtdapi.FindUBUsingFFT(
            PeaksWorkspace="live_peaks_ws",
            MinD=wf.min_d,
            MaxD=wf.max_d,
            Tolerance=0.12,
            Iterations=100,
        )
    except ValueError as ub_error:
        logger.warning("Warning: FindUBUsingFFT error - Four or more indexed peaks needed to find UB")
        logger.warning("%s %s", "Error message: ", ub_error)
        wf.current_run_end_time = mtdapi.mtd["live_event_ws"].getRun().endTime().totalNanoseconds() * 1e-9
        wf.measure_time = wf.current_run_end_time - wf.initial_run_start_time
        if wf.measure_time > 100000:
            logger.debug("Please check if neutron beam is on, or if the crystal is diffracting.")
    trace("6 filterbytime")
    trace("=" * 60)


def integrate_and_predict(wf: "MantidWorkflow") -> None:
    """Index peaks, integrate ellipsoids, predict + centroid + re-index."""
    mtdapi.CloneWorkspace(InputWorkspace="live_event_ws", OutputWorkspace="live_event_ws_peak")
    trace("7.0 filterbytime")
    trace("=" * 60)

    mtdapi.IndexPeaks(
        PeaksWorkspace="live_peaks_ws",
        Tolerance=0.12,
        ToleranceForSatellite=0.10000000000000001,
        RoundHKLs=False,
        CommonUBForAll=True,
    )
    trace("7.1 filterbytime")
    trace("=" * 60)

    mtdapi.IntegrateEllipsoids(
        InputWorkspace="live_event_ws_peak",
        PeaksWorkspace="live_peaks_ws",
        RegionRadius=0.18,
        SpecifySize=True,
        PeakSize=0.09,
        BackgroundInnerSize=0.11,
        BackgroundOuterSize=0.14,
        OutputWorkspace="live_peaks_ws",
        CutoffIsigI=5,
        AdaptiveQBackground=True,
        AdaptiveQMultiplier=0.001,
        UseOnePercentBackgroundCorrection=False,
    )
    trace("7.2 filterbytime")
    trace("=" * 60)

    mtdapi.PredictPeaks(
        InputWorkspace="live_peaks_ws",
        WavelengthMin=0.4,
        WavelengthMax=3.5,
        MinDSpacing=0.6,
        MaxDSpacing=11,
        OutputWorkspace="live_predict_peaks_ws",
        EdgePixels=18,
    )
    trace("7 filterbytime")
    trace("=" * 60)

    peak_radius = 0.08
    search_radius = 0.8 * float(peak_radius)
    mtdapi.CentroidPeaksMD(
        InputWorkspace="live_event_md_Qsample",
        PeakRadius=search_radius,
        PeaksWorkspace="live_predict_peaks_ws",
        OutputWorkspace="live_predict_peaks_ws",
    )
    mtdapi.IndexPeaks(PeaksWorkspace="live_predict_peaks_ws", Tolerance=0.12, CommonUBForAll=True)
    mtdapi.FindUBUsingIndexedPeaks(PeaksWorkspace="live_predict_peaks_ws", Tolerance=0.12, CommonUBForAll=True)
    mtdapi.IndexPeaks(
        PeaksWorkspace="live_predict_peaks_ws",
        Tolerance=0.12,
        RoundHKLs=False,
        CommonUBForAll=True,
    )

    wf.proton_charge = mtdapi.mtd["live_event_ws"].getRun().getProtonCharge() * 0.0036
    logger.debug(
        "%s %s %s %s %s", "\n", wf.current_run, " has integrated proton charge x 0.0036 of", wf.proton_charge, "C \n"
    )

    wf.current_run_end_time = mtdapi.mtd["live_event_ws"].getRun().endTime().totalNanoseconds() * 1e-9
    wf.measure_time = wf.current_run_end_time - wf.current_run_start_time
    trace("8 filterbytime")
    trace("=" * 60)

    mtdapi.IntegrateEllipsoids(
        InputWorkspace="live_event_ws_peak",
        PeaksWorkspace="live_predict_peaks_ws",
        RegionRadius=0.2,
        SpecifySize=True,
        PeakSize=0.09,
        BackgroundInnerSize=0.11,
        BackgroundOuterSize=0.14,
        OutputWorkspace="live_predict_peaks_ws",
        CutoffIsigI=5,
        AdaptiveQBackground=True,
        AdaptiveQMultiplier=0.001,
        UseOnePercentBackgroundCorrection=False,
    )

    if wf.cell_type is not None:
        mtdapi.SelectCellOfType(
            PeaksWorkspace="live_predict_peaks_ws",
            CellType=wf.cell_type,
            Centering=wf.centering,
            Tolerance=wf.tolerance,
            Apply=True,
        )
        mtdapi.IndexPeaks(
            PeaksWorkspace="live_predict_peaks_ws",
            Tolerance=wf.tolerance,
            ToleranceForSatellite=wf.tolerance_satellite,
            RoundHKLs=False,
            CommonUBForAll=True,
        )
    trace("9 filterbytime")
    trace("=" * 60)


def check_peaks(wf: "MantidWorkflow") -> None:
    """Tally + statistics + selector dispatch + per-cycle append + save CSV."""
    live_predict_peaks_ws = mtdapi.mtd["live_predict_peaks_ws"]

    num_peaks = live_predict_peaks_ws.getNumberPeaks()
    int_ilist = np.zeros(num_peaks)
    sig_ilist = np.zeros(num_peaks)
    for i in range(num_peaks):
        peak = live_predict_peaks_ws.getPeak(i)
        int_i = peak.getIntensity()
        int_ilist[i] = int_i
        sig_i = peak.getSigmaIntensity()
        sig_ilist[i] = sig_i
        wf.sum = wf.sum + 1
        if int_i > (2.0 * sig_i):
            wf.sig2 = wf.sig2 + 1
        if int_i > (3.0 * sig_i):
            wf.sig3 = wf.sig3 + 1
        if int_i > (5.0 * sig_i):
            wf.sig5 = wf.sig5 + 1
        if int_i > (10.0 * sig_i):
            wf.sig10 = wf.sig10 + 1

    if wf.maxpeak_idx > -1 and wf.maxpeak_idx != np.argmax(int_ilist):
        logger.warning(
            "%s %s %s %s", "Warning: Max peak index has changed from ", wf.maxpeak_idx, " to ", np.argmax(int_ilist)
        )
        wf.maxpeak_idx = int(np.argmax(int_ilist))

    if wf.maxpeak_idx == -1:
        wf.maxpeak_idx = int(np.argmax(int_ilist))

    wf.maxpeak_int_i = int_ilist[wf.maxpeak_idx]
    peak = live_predict_peaks_ws.getPeak(int(wf.maxpeak_idx))
    wf.hkl = peak.getHKL()

    sorted_ws, statistics_table, _equiv = mtdapi.StatisticsOfPeaksWorkspace(
        InputWorkspace="live_predict_peaks_ws",
        PointGroup=wf.point_group,
        LatticeCentering=wf.centering,
        SortBy="Overall",
        WeightedZScore=True,
    )
    statistics = statistics_table.row(0)

    first_peak = sorted_ws.getPeak(0)
    logger.debug("HKL of first peak in table {} {} {}".format(first_peak.getH(), first_peak.getK(), first_peak.getL()))
    logger.debug("Multiplicity = %.2f" % statistics["Multiplicity"])
    logger.debug("Resolution Min = %.2f" % statistics["Resolution Min"])
    logger.debug("Resolution Max = %.2f" % statistics["Resolution Max"])
    logger.debug("No. of Unique Reflections = %i" % statistics["No. of Unique Reflections"])
    logger.debug("Mean ((I)/sd(I)) = %.2f" % statistics["Mean ((I)/sd(I))"])
    logger.debug("Rmerge = %.2f" % statistics["Rmerge"])
    logger.debug("Rpim = %.2f" % statistics["Rpim"])

    mtdapi.SaveIsawPeaks(Inputworkspace="live_predict_peaks_ws", Filename=wf.output_path + wf.live_peaks_fname)
    mtdapi.SaveIsawUB(Inputworkspace="live_predict_peaks_ws", Filename=wf.output_path + wf.live_peaks_ub_fname)

    wf.latest_ub = wf.get_latest_ub("live_predict_peaks_ws")
    wf.latest_lattice = wf.get_latest_lattice("live_predict_peaks_ws")
    wf.latest_ub_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    wf.latest_ub_saved_path = wf.save_latest_ub("live_predict_peaks_ws") or ""

    # Selector dispatch. Unknown dropdown picks return None and leave
    # ``intensity_ratio`` at its previous value, matching the legacy
    # fall-through behavior. A selector that returns None signals "skip
    # this cycle" — no append, no Rsig recomputation.
    wf.skip_this_cycle = False
    selector = make_selector(wf.selection, **getattr(wf, "selector_params", {}))
    if selector is not None:
        result = selector.select(
            peaks_ws=live_predict_peaks_ws,
            int_array=int_ilist,
            sig_array=sig_ilist,
            max_peak_idx=wf.maxpeak_idx,
            statistics=statistics,
        )
        if result is None:
            wf.skip_this_cycle = True
            wf.skip_reason = getattr(selector, "last_skip_reason", "") or (
                f"Selector '{wf.selection}' returned no data this cycle"
            )
        else:
            wf.skip_reason = ""
            wf.intensity_ratio = result.intensity_ratio
            wf.Rsig = result.rsig
            wf.selection_aux = result.aux
            wf.current_labels = {
                "intensity_title": result.intensity_title,
                "intensity_yaxis": result.intensity_yaxis,
                "uncertainty_title": result.uncertainty_title,
                "uncertainty_yaxis": result.uncertainty_yaxis,
            }
    else:
        wf.skip_this_cycle = True
        wf.skip_reason = f"No selector registered for mode '{wf.selection}'"

    if not wf.skip_this_cycle:
        logger.debug("Rsig = %.2f" % wf.Rsig)
    if (
        not wf.skip_this_cycle
        and getattr(wf, "intensity_ratio", None) is not None
        and getattr(wf, "Rsig", None) is not None
        and wf.proton_charge is not None
    ):
        wf.proton_charges.append(wf.proton_charge)
        wf.intensity_ratios.append(wf.intensity_ratio)
        wf.rsigs.append(wf.Rsig)
        wf.measure_times.append(wf.measure_time)
    else:
        logger.warning("Skipping entry due to missing data or placeholder mode.")
    wf.sig2s.append(wf.sig2)
    wf.sig3s.append(wf.sig3)
    wf.sig5s.append(wf.sig5)
    wf.sig10s.append(wf.sig10)
    logger.debug("measure_times, proton_charges, intensity_ratios, rsigs")
    logger.debug("%s %s %s %s", wf.measure_times, wf.proton_charges, wf.intensity_ratios, wf.rsigs)
    results = np.column_stack((wf.measure_times, wf.proton_charges, wf.intensity_ratios, wf.rsigs))
    np.savetxt(
        wf.output_path + "live_data_%s_results.csv" % (str(wf.current_run)),
        results,
        delimiter=",",
        header="",
        comments="",
    )
