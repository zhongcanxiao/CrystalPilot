from pydantic import BaseModel, Field, computed_field, field_validator, model_validator
from typing import List, Dict
import plotly.graph_objects as go
from plotly.data import iris
from plotly.subplots import make_subplots

#from mantid.simpleapi import *
import mantid.simpleapi as mtdapi
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import time
import sys

# import mantid algorithms, numpy and matplotlib
#matplotlib.use("Qt5Agg")
#sys.path.append('/SNS/TOPAZ/shared/PythonPrograms/Python3Library')
#from SCDTools import recenter_peaks_workspace



ipts=34069
output_path = '/SNS/TOPAZ/IPTS-{:d}/shared/autoreduce/live_data/'.format(ipts)
calib_fname = '/SNS/TOPAZ/IPTS-{:d}/shared/calibration/TOPAZ_2025A_AG_3-3BN.DetCal'.format(ipts)

# Sample information
min_d = 7   # shortest lattice parameter
max_d = 22  # longest lattice parameter

cell_type  = 'Monoclinic'
centering  = 'P'

tolerance = 0.12

#Specify ellipse integration control parameters for satellite peaks
satellite_peak_size             = '0.07'
satellite_background_inner_size = '0.09'
satellite_background_outer_size = '0.12'
satellite_region_radius         = '0.13'

#
mod_vector1 = '0,0,0'
mod_vector2 = '0,0,0'
mod_vector3 = '0,0,0'
#
max_order = '1'
cross_terms = False

tolerance_satellite = 0.10
#
#User specified q-vector if save_mod_info is True
save_mod_info = False

#=================================================================================================

def update_plot():
    """Update plot with current run data dynamically."""
    ax_intensity.clear()
    ax_rsig.clear()
    ax_intensity.plot(measure_times, intensity_ratios, '-o', label='Peak I/σ(I)')
    ax_rsig.plot(measure_times, rsigs, '-o', label='Rsig')
    ax_intensity.set_ylabel('Peak I/σ(I)')
    ax_rsig.set_ylabel('Rsig')
    ax_rsig.set_xlabel('Run time, seconds')
    ax_intensity.grid(True)
    ax_rsig.grid(True)
    plt.suptitle(f"Live Data Reduction - Run {current_run}")
    plt.draw()
    plt.pause(0.1)


def plot_data(x, y1, y2, xlabel, ylabel1, ylabel2):
    print('plot_data')
    plt.clf()  # Clear the figure to start a new plot
    plt.plot(x, y1, '-o', label=ylabel1)
    plt.plot(x, y2, '-o', label=ylabel2)
    plt.xlabel(xlabel)
    #plt.xlim(0,1000) 
    plt.grid(True)
    plt.suptitle(f"Live Data Reduction - TOPAZ_{current_run}")
    plt.legend()
    #plt.draw()  # Use draw() instead of show() to update the plot
    plt.show()  # Use draw() instead of show() to update the plot

#
min_monitor_tof = 500
max_monitor_tof = 13000

proton_charges = []
intensity_ratios = []
rsigs = []
measure_times = []
sum = sig2 = sig3 = sig5 = sig10 = 0
# Initialize arrays as empty lists
sig2s = np.array([])
sig3s = np.array([])
sig5s = np.array([])
sig10s = np.array([])

use_monitor_counts = False

# Check if live data is already running

try:
    mtdapi.StartLiveData(
            Instrument='TOPAZ',
            Listener='SNSLiveEventDataListener',
            UpdateEvery=10,
            AccumulationMethod='Add',
            PreserveEvents=True,
            OutputWorkspace='live_event_ws')    
    run_start_time = mtdapi.mtd['live_event_ws'].getRun().startTime().totalNanoseconds() * 1e-9
    time.sleep(1)
    #time.sleep(60)
except RuntimeError as e:
    if 'Another MonitorLiveData thread is running' in str(e):
        current_run=mtd['live_event_ws'].getRunNumber()
        print("Warning: Another MonitorLiveData thread is already running for TOPAZ run %s."%(str(current_run)),
              "\nIt will continue with the current run unless you stop the existing instance manually or use a different OutputWorkspace.")
        sys.exit(1)
    else:
        print(f"Unexpected error occurred: {str(e)}")
        raise
    
# Proceed with data processing
if not mtdapi.mtd.doesExist('live_event_ws'):
    print("Live data workspace does not exist. Exiting.")
    exit(1)

current_run = mtdapi.mtd['live_event_ws'].getRunNumber()
print(f"Current run: {current_run}")

# update the run number for live data reduction
run = current_run

# Initialize the plot with two subplots
fig, (ax_intensity, ax_rsig) = plt.subplots(2, 1, sharex=True)
ax_intensity.grid(True)
ax_rsig.grid(True)



missing_ub_number=0
run_start_time = mtdapi.mtd['live_event_ws'].getRun().startTime().totalNanoseconds() * 1e-9
#while True:
def live_data_reduction():
    run=mtdapi.mtd['live_event_ws'].getRunNumber()
    start_time = mtdapi.mtd['live_event_ws'].getRun().startTime().totalNanoseconds() * 1e-9

    if run != current_run:
        # Save the results
        results = np.column_stack((measure_times, proton_charges, intensity_ratios, rsigs))
        np.savetxt(output_path + 'live_data_%s_results.csv'%(str(run)), results, delimiter=',', header='', comments='')
        # save results
        mtdapi.SaveIsawPeaks(Inputworkspace='live_predict_peaks_ws', 
                Filename= output_path + live_peaks_fname )
        mtdapi.SaveIsawUB(Inputworkspace='live_predict_peaks_ws',  
                Filename= output_path + live_peaks_fname )

        # Clear the existing data and plot if run changes
        current_run = run
        proton_charges.clear()
        intensity_ratios.clear()
        rsigs.clear()
        measure_times.clear()
        time.sleep(60)
        plt.clf()  # Clear the plot


    mtdapi.LoadIsawDetCal(InputWorkspace='live_event_ws', Filename=calib_fname)
    monitor_ws=mtdapi.mtd['live_event_ws'].getMonitorWorkspace()
    integrated_monitor_ws = mtdapi.Integration( InputWorkspace=monitor_ws, 
                      RangeLower=min_monitor_tof, RangeUpper=max_monitor_tof, 
                      StartWorkspaceIndex=0, 
                      EndWorkspaceIndex=0 )
    monitor_count = integrated_monitor_ws.dataY(0)[0]
    print("\n", current_run, " has integrated monitor count", monitor_count, "\n")

    #
    mtdapi.SetGoniometer(Workspace='live_event_ws', Goniometers='Universal')

    mtdapi.ConvertToMD(InputWorkspace='live_event_ws', 
        QDimensions="Q3D", dEAnalysisMode="Elastic", 
        Q3DFrames='Q_sample',
        QConversionScales="Q in A^-1", 
        LorentzCorrection='1',
        Uproj='1,0,0', Vproj='0,1,0', Wproj='0,0,1',
        OutputWorkspace='live_event_md_Qsample', MinValues='-12,-12,-12', MaxValues='12,12,12')
    mtdapi.FindPeaksMD(InputWorkspace='live_event_md_Qsample', PeakDistanceThreshold=0.6, 
        MaxPeaks=1000, DensityThresholdFactor=100, OutputWorkspace='live_peaks_ws', EdgePixels=18)

    try:
        mtdapi.FindUBUsingFFT(PeaksWorkspace='live_peaks_ws', MinD=min_d, MaxD=max_d, Tolerance=0.12,Iterations=100)
    except ValueError as ub_error:
        print("Warning: FindUBUsingFFT error - Four or more indexed peaks needed to find UB")
        #LoadIsawUB(InputWorkspace='live_peaks_ws',Filename='/SNS/TOPAZ/IPTS-33641/shared/S5-1_5K/S5-1_5K_Monoclinic_P.mat')
        #IndexPeaks(PeaksWorkspace='live_peaks_ws', Tolerance=0.12, ToleranceForSatellite=0.10000000000000001, RoundHKLs=False, CommonUBForAll=True)
        end_time = mtdapi.mtd['live_event_ws'].getRun().endTime().totalNanoseconds() * 1e-9  # Convert nanoseconds to seconds
        
        measure_time = end_time -run_start_time
        if measure_time >100000: 
            print("Please check if neutron beam is on, or if the crystal is diffracting.")
            exit()
        #continue
        

    mtdapi.IndexPeaks(PeaksWorkspace='live_peaks_ws', Tolerance=0.12, ToleranceForSatellite=0.10000000000000001, RoundHKLs=False, CommonUBForAll=True)
    mtdapi.IntegrateEllipsoids(InputWorkspace='live_event_ws', PeaksWorkspace='live_peaks_ws', 
        RegionRadius=0.18, SpecifySize=True, PeakSize=0.09, BackgroundInnerSize=0.11, BackgroundOuterSize=0.14, 
        OutputWorkspace='live_peaks_ws', CutoffIsigI=5, 
        AdaptiveQBackground=True, 
        AdaptiveQMultiplier=0.001, UseOnePercentBackgroundCorrection=False)
    mtdapi.PredictPeaks(InputWorkspace='live_peaks_ws', 
        WavelengthMin=0.4, 
        WavelengthMax=3.5, 
        MinDSpacing=0.6, 
        MaxDSpacing=11, 
        OutputWorkspace='live_predict_peaks_ws', EdgePixels=18)
    #
    peak_radius = 0.08
    search_radius = 0.8*float(peak_radius)
    mtdapi.CentroidPeaksMD(InputWorkspace='live_event_md_Qsample', PeakRadius=search_radius, 
        PeaksWorkspace='live_predict_peaks_ws', OutputWorkspace='live_predict_peaks_ws')
    mtdapi.IndexPeaks(PeaksWorkspace='live_predict_peaks_ws', Tolerance=0.12, CommonUBForAll=True)
    mtdapi.FindUBUsingIndexedPeaks(PeaksWorkspace='live_predict_peaks_ws', Tolerance=0.12, CommonUBForAll=True)
    mtdapi.IndexPeaks(PeaksWorkspace='live_predict_peaks_ws', Tolerance=0.12, RoundHKLs=False, CommonUBForAll=True)
    
    proton_charge = mtdapi.mtd['live_event_ws'].getRun().getProtonCharge() * 0.0036
    print("\n", current_run, " has integrated proton charge x 0.0036 of", proton_charge, "C \n")
    
    end_time = mtdapi.mtd['live_event_ws'].getRun().endTime().totalNanoseconds() * 1e-9  # Convert nanoseconds to seconds
    
    measure_time = end_time -start_time
  
    mtdapi.IntegrateEllipsoids(InputWorkspace='live_event_ws', 
        PeaksWorkspace='live_predict_peaks_ws', 
        RegionRadius=0.2, SpecifySize=True, 
        PeakSize=0.09, BackgroundInnerSize=0.11, BackgroundOuterSize=0.14, 
        OutputWorkspace='live_predict_peaks_ws', 
        CutoffIsigI=5, 
        AdaptiveQBackground=True, 
        AdaptiveQMultiplier=0.001, UseOnePercentBackgroundCorrection=False)
        
    if not cell_type is None:
        mtdapi.SelectCellOfType(PeaksWorkspace='live_predict_peaks_ws', 
            CellType=cell_type, Centering=centering, Tolerance = tolerance, Apply=True, )
        mtdapi.IndexPeaks(PeaksWorkspace='live_predict_peaks_ws', 
            Tolerance=tolerance, ToleranceForSatellite=tolerance_satellite, RoundHKLs=False, CommonUBForAll=True)


    live_predict_peaks_ws=mtdapi.mtd['live_predict_peaks_ws']

    if not cell_type is None:
        live_peaks_fname = 'live_topaz-ipts-%s_%s_%s_%s.integrate'%(str(ipts),str(current_run),cell_type,centering)
        live_peaks_ub_fname = 'live_topaz-ipts-%s_%s__%s_%s.mat'%(str(ipts), str(current_run),cell_type,centering)
    else:
        live_peaks_fname = 'live_topaz-ipts-%s_%s_Niggli.integrate'%(str(ipts),str(current_run))
        live_peaks_ub_fname = 'live_topaz-ipts-%s_%s_Niggli.mat'%(str(ipts), str(current_run))


    #peaks_fname = 'live_%s_Niggli.integrate'%(str(current_run))
    #peaks_ub_fname = 'live_%s_Niggli.mat'%(str(current_run))

    # Set the monitor counts for all the peaks that will be integrated

    num_peaks = live_predict_peaks_ws.getNumberPeaks()
    for i in range(num_peaks):
      peak = live_predict_peaks_ws.getPeak(i)
      intI = peak.getIntensity()
      sigI = peak.getSigmaIntensity()
      sum = sum + 1
      if intI > (2.0 * sigI):
        sig2 = sig2 + 1
      if intI > (3.0 * sigI):
        sig3 = sig3 + 1
      if intI > (5.0 * sigI):
        sig5 = sig5 + 1
      if intI > (10.0 * sigI):
        sig10 = sig10 + 1

    # Run the SortHKL algorithm

    sorted, statistics_table, equivI = mtdapi.StatisticsOfPeaksWorkspace(InputWorkspace='live_predict_peaks_ws', 
        PointGroup='2/m', LatticeCentering='P', SortBy='Overall', WeightedZScore=True)

    statistics = statistics_table.row(0)

    peak = sorted.getPeak(0)
    print("HKL of first peak in table {} {} {}".format(peak.getH(),peak.getK(),peak.getL()))
    print("Multiplicity = %.2f" % statistics['Multiplicity'])
    print("Resolution Min = %.2f" % statistics['Resolution Min'])
    print("Resolution Max = %.2f" % statistics['Resolution Max'])
    print("No. of Unique Reflections = %i" % statistics['No. of Unique Reflections'])
    print("Mean ((I)/sd(I)) = %.2f" % statistics['Mean ((I)/sd(I))'])
    print("Rmerge = %.2f" % statistics['Rmerge'])
    print("Rpim = %.2f" % statistics['Rpim'])

    mtdapi.SaveIsawPeaks(Inputworkspace='live_predict_peaks_ws', 
        Filename= output_path + live_peaks_fname)
    mtdapi.SaveIsawUB(Inputworkspace='live_predict_peaks_ws',  
        Filename= output_path + live_peaks_ub_fname)

    # Check the overall peak intensity in live_peaks_ws
    intensity_ratio =statistics['Mean ((I)/sd(I))']
    
    Rsig = 100.0/intensity_ratio
    print("Rsig = %.2f" % Rsig)

    if intensity_ratio is not None and Rsig is not None and proton_charge is not None:
        proton_charges.append(proton_charge)
        intensity_ratios.append(intensity_ratio)
        rsigs.append(Rsig)
        measure_times.append(measure_time)  # Only append if all other values exist
    else:
        print("Skipping entry due to missing data.")
    sig2s = np.append(sig2s, sig2)
    sig3s = np.append(sig3s, sig3)
    sig5s = np.append(sig5s, sig5)
    sig10s = np.append(sig10s, sig10)
    # Save the plot data
    print('measure_times, proton_charges, intensity_ratios, rsigs')
    print(measure_times, proton_charges, intensity_ratios, rsigs)
    results = np.column_stack((measure_times, proton_charges, intensity_ratios, rsigs))
    np.savetxt(output_path + 'live_data_%s_results.csv'%(str(current_run)), results, delimiter=',', header='', comments='')

    # Update the plots with new data points
    plot_data(np.array(measure_times), np.array(intensity_ratios), np.array(rsigs), 'Run time, seconds', 'Peak I/\u03c3(I)', 'Rsig')
   
    cancel_threshold =30 

    if intensity_ratio > cancel_threshold:
        time.sleep(2)
        # This will cancel both algorithms
        #AlgorithmManager.cancelAll()
        # save results
        mtdapi.SaveIsawPeaks(Inputworkspace='live_predict_peaks_ws', 
                Filename= output_path + live_peaks_fname )
        mtdapi.SaveIsawUB(Inputworkspace='live_predict_peaks_ws',  
                Filename= output_path + live_peaks_fname )

        # Clear the lists to start plotting fresh data points
        proton_charges.clear()
        intensity_ratios.clear()
        rsigs.clear()
        measure_times.clear()

        # Pause briefly to let the plots be updated
        time.sleep(1)
        #print("Intensity ratio exceeds the cancel threshold. Exiting...")

    # Pause briefly to let the plots be updated
    time.sleep(15)





class TemporalAnalysisModel(BaseModel):
    headers: List[str] = Field(default=["Title", "Comment", "phi", "omega", "Wait For", "Value", "Or Time"])
    #headers: List[str] = Field(default=["Title", "Comment", "BL12:Mot:goniokm:phi", "BL12:Mot:goniokm:omega", "Wait For", "Value", "Or Time"])
    table_test: List[Dict] = Field(default=[{"title":"1","header":"h"}])
    prediction_model_type: str = Field(default="Linear Interpolation", title="Prediction Model")
    prediction_model_type_options: List[str] = ["Linear Interpolation", "Poisson Model"]

    def get_live_data(self) -> List[Dict]:
        pass
        
    def generate_prediction_figure(self) -> go.Figure:
        x_data = list(range(10))
        y_data = [i**2 for i in x_data]
        fig = make_subplots(rows=1, cols=2)
        return fig