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

import asyncio
from typing import ClassVar
# import mantid algorithms, numpy and matplotlib
#matplotlib.use("Qt5Agg")
#sys.path.append('/SNS/TOPAZ/shared/PythonPrograms/Python3Library')
#from SCDTools import recenter_peaks_workspace

class MantidWorkflow():
    def __init__(self)->None:
    #def set_up_mantid_info(self)->None:
        print("initializing mtd workflow")
        self.ipts=34069
        self.output_path = '/SNS/TOPAZ/IPTS-{:d}/shared/autoreduce/live_data/'.format(self.ipts)
        self.calib_fname = '/SNS/TOPAZ/IPTS-{:d}/shared/calibration/TOPAZ_2025A_AG_3-3BN.DetCal'.format(self.ipts)

        # Sample information
        self.min_d = 7   # shortest lattice parameter
        self.max_d = 22  # longest lattice parameter

        self.cell_type  = 'Monoclinic'
        self.centering  = 'P'

        self.tolerance = 0.12

        #Specify ellipse integration control parameters for satellite peaks
        self.satellite_peak_size             = '0.07'
        self.satellite_background_inner_size = '0.09'
        self.satellite_background_outer_size = '0.12'
        self.satellite_region_radius         = '0.13'

        #
        self.mod_vector1 = '0,0,0'
        self.mod_vector2 = '0,0,0'
        self.mod_vector3 = '0,0,0'
        #
        self.max_order = '1'
        self.cross_terms = False

        self.tolerance_satellite = 0.10
        #
        #User specified q-vector if save_mod_info is True
        self.save_mod_info = False
        #
        self.min_monitor_tof = 500
        self.max_monitor_tof = 13000
        self.use_monitor_counts = False


        #=================================================================================================
    #'''
    #def update_plot():
    #    """Update plot with current run data dynamically."""
    #    ax_intensity.clear()
    #    ax_rsig.clear()
    #    ax_intensity.plot(measure_times, intensity_ratios, '-o', label='Peak I/σ(I)')
    #    ax_rsig.plot(measure_times, rsigs, '-o', label='Rsig')
    #    ax_intensity.set_ylabel('Peak I/σ(I)')
    #    ax_rsig.set_ylabel('Rsig')
    #    ax_rsig.set_xlabel('Run time, seconds')
    #    ax_intensity.grid(True)
    #    ax_rsig.grid(True)
    #    plt.suptitle(f"Live Data Reduction - Run {current_run}")
    #    plt.draw()
    #    plt.pause(0.1)
    #'''

    #'''
    #def plot_data(x, y1, y2, xlabel, ylabel1, ylabel2):
    #    print('plot_data')
    #    plt.clf()  # Clear the figure to start a new plot
    #    plt.plot(x, y1, '-o', label=ylabel1)
    #    plt.plot(x, y2, '-o', label=ylabel2)
    #    plt.xlabel(xlabel)
    #    #plt.xlim(0,1000) 
    #    plt.grid(True)
    #    plt.suptitle(f"Live Data Reduction - TOPAZ_{current_run}")
    #    plt.legend()
    #    #plt.draw()  # Use draw() instead of show() to update the plot
    #    plt.show()  # Use draw() instead of show() to update the plot
    #'''

    #def init_measurement_data():
    #    """Initialize the plot with empty data."""

        self.proton_charges: list[float] = []
        self.intensity_ratios: list[float] = []
        self.rsigs: list[float] = []
        self.measure_times: list[float] = []
        self.sum = self.sig2 = self.sig3 = self.sig5 = self.sig10 = 0
        # Initialize arrays as empty lists
        self.sig2s = np.array([])
        self.sig3s = np.array([])
        self.sig5s = np.array([])
        self.sig10s = np.array([])
        self.missing_ub_number=0

        self.current_run_end_time = 0
        self.measure_time = 0
        self.proton_charge = 0       

    # Check if live data is already running

    def update_peak_output_filenames(self):
        if not self.cell_type is None:
            self.live_peaks_fname = 'live_topaz-ipts-%s_%s_%s_%s.integrate'%(str(self.ipts),str(self.current_run),self.cell_type,self.centering)
            self.live_peaks_ub_fname = 'live_topaz-ipts-%s_%s__%s_%s.mat'%(str(self.ipts), str(self.current_run),self.cell_type,self.centering)
        else:
            self.live_peaks_fname = 'live_topaz-ipts-%s_%s_Niggli.integrate'%(str(self.ipts),str(self.current_run))
            self.live_peaks_ub_fname = 'live_topaz-ipts-%s_%s_Niggli.mat'%(str(self.ipts), str(self.current_run))


    def start_live_data_collection_instances(self):

        """Start live data instances: worksapce mtd['live_event_wc], self.currentrun,self.run."""
        try:
            mtdapi.StartLiveData(
                    Instrument='TOPAZ',
                    Listener='SNSLiveEventDataListener',
                    UpdateEvery=10,
                    AccumulationMethod='Add',
                    PreserveEvents=True,
                    OutputWorkspace='live_event_ws')    
            self.monitor_start_time = mtdapi.mtd['live_event_ws'].getRun().startTime().totalNanoseconds() * 1e-9
            time.sleep(1)
            #time.sleep(60)
        except RuntimeError as e:
            if 'Another MonitorLiveData thread is running' in str(e):
                conflict_current_run=mtdapi.mtd['live_event_ws'].getRunNumber()
                print("Warning: Another MonitorLiveData thread is already running for TOPAZ run %s."%(str(conflict_current_run)),
                      "\nIt will continue with the current run unless you stop the existing instance manually or use a different OutputWorkspace.")
                sys.exit(1)
            else:
                print(f"Unexpected error occurred: {str(e)}")
                raise
        #self.run_start_time = mtdapi.mtd['live_event_ws'].getRun().startTime().totalNanoseconds() * 1e-9
            
        # Proceed with data processing
        if not mtdapi.mtd.doesExist('live_event_ws'):
            print("Live data workspace does not exist. Exiting.")
            exit(1)
        self.initial_run = mtdapi.mtd['live_event_ws'].getRunNumber()
        self.initial_run_start_time = mtdapi.mtd['live_event_ws'].getRun().startTime().totalNanoseconds() * 1e-9
        print(f"initial run: {self.initial_run}")

        # update the run number for live data reduction
        self.current_run = self.initial_run
        self.current_run_start_time = self.initial_run_start_time
        self.update_peak_output_filenames()


       # self.run = self.current_run

    ## Initialize the plot with two subplots
    #'''
    #def init_visualization():
    #    fig, (ax_intensity, ax_rsig) = plt.subplots(2, 1, sharex=True)
    #    ax_intensity.grid(True)
    #    ax_rsig.grid(True)
    #'''   


    def live_data_reduction(self):
        #while True:
        def get_and_update_run_info_of_current_run():
            #############################################################################################################################################################
            # ''' check if the run number has changed, if so, save the results and clear the existing data , and update the run infos'''
            #############################################################################################################################################################
            current_run=mtdapi.mtd['live_event_ws'].getRunNumber()
            current_run_start_time = mtdapi.mtd['live_event_ws'].getRun().startTime().totalNanoseconds() * 1e-9

            if current_run != self.current_run:
                # Save the results
                results = np.column_stack((self.measure_times, self.proton_charges, self.intensity_ratios, self.rsigs))
                np.savetxt(self.output_path + 'live_data_%s_results.csv'%(str(self.current_run)), results, delimiter=',', header='', comments='')
                # save results
                mtdapi.SaveIsawPeaks(Inputworkspace='live_predict_peaks_ws', 
                        Filename= self.output_path + self.live_peaks_fname )
                mtdapi.SaveIsawUB(Inputworkspace='live_predict_peaks_ws',  
                        Filename= self.output_path + self.live_peaks_fname )

                # Clear the existing data and plot if run changes
                self.current_run = current_run
                self.current_run_start_time = current_run_start_time
                self.proton_charges.clear()
                self.intensity_ratios.clear()
                self.rsigs.clear()
                self.measure_times.clear()
                time.sleep(1)
                #time.sleep(60)
                #plt.clf()  # Clear the plot

            self.update_peak_output_filenames()
       
        def load_config_of_current_run():
            #############################################################################################################################################################
            #''' Load the calibration file and monitor data, and integrate the peaks'''
            #############################################################################################################################################################
            mtdapi.LoadIsawDetCal(InputWorkspace='live_event_ws', Filename=self.calib_fname)
            monitor_ws=mtdapi.mtd['live_event_ws'].getMonitorWorkspace()
            integrated_monitor_ws = mtdapi.Integration( InputWorkspace=monitor_ws, 
                              RangeLower=self.min_monitor_tof, RangeUpper=self.max_monitor_tof, 
                              StartWorkspaceIndex=0, 
                              EndWorkspaceIndex=0 )
            monitor_count = integrated_monitor_ws.dataY(0)[0]
            print("\n", self.current_run, " has integrated monitor count", monitor_count, "\n")

            #
            mtdapi.SetGoniometer(Workspace='live_event_ws', Goniometers='Universal')

        def refine_ub_of_current_run():
            #############################################################################################################################################################
            #''' Refine the UB matrix'''
            #############################################################################################################################################################
            #TODO: why convert to md
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
                mtdapi.FindUBUsingFFT(PeaksWorkspace='live_peaks_ws', MinD=self.min_d, MaxD=self.max_d, Tolerance=0.12,Iterations=100)
            except ValueError as ub_error:
                print("Warning: FindUBUsingFFT error - Four or more indexed peaks needed to find UB")
                print("Error message: ", ub_error)
                #TODO: should use next two commands or not?
                #mtdapi.LoadIsawUB(InputWorkspace='live_peaks_ws',Filename='/SNS/TOPAZ/IPTS-33641/shared/S5-1_5K/S5-1_5K_Monoclinic_P.mat')
                #mtdapi.IndexPeaks(PeaksWorkspace='live_peaks_ws', Tolerance=0.12, ToleranceForSatellite=0.10000000000000001, RoundHKLs=False, CommonUBForAll=True)
                self.current_run_end_time = mtdapi.mtd['live_event_ws'].getRun().endTime().totalNanoseconds() * 1e-9  # Convert nanoseconds to seconds

                self.measure_time = self.current_run_end_time -self.initial_run_start_time
                if self.measure_time >100000: 
                    print("Please check if neutron beam is on, or if the crystal is diffracting.")
                    exit()
                #continue


        def integrate_peaks_of_current_run():
            #############################################################################################################################################################
            #''' Integrate the peaks and predict the peaks'''
            #############################################################################################################################################################

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
            #TODO: local variables to be taken out
            peak_radius = 0.08
            search_radius = 0.8*float(peak_radius)
            mtdapi.CentroidPeaksMD(InputWorkspace='live_event_md_Qsample', PeakRadius=search_radius, 
                PeaksWorkspace='live_predict_peaks_ws', OutputWorkspace='live_predict_peaks_ws')
            mtdapi.IndexPeaks(PeaksWorkspace='live_predict_peaks_ws', Tolerance=0.12, CommonUBForAll=True)
            mtdapi.FindUBUsingIndexedPeaks(PeaksWorkspace='live_predict_peaks_ws', Tolerance=0.12, CommonUBForAll=True)
            mtdapi.IndexPeaks(PeaksWorkspace='live_predict_peaks_ws', Tolerance=0.12, RoundHKLs=False, CommonUBForAll=True)

            self.proton_charge = mtdapi.mtd['live_event_ws'].getRun().getProtonCharge() * 0.0036
            print("\n", self.current_run, " has integrated proton charge x 0.0036 of", self.proton_charge, "C \n")

            self.current_run_end_time = mtdapi.mtd['live_event_ws'].getRun().endTime().totalNanoseconds() * 1e-9  # Convert nanoseconds to seconds

            self.measure_time = self.current_run_end_time -self.current_run_start_time
    
            mtdapi.IntegrateEllipsoids(InputWorkspace='live_event_ws', 
                PeaksWorkspace='live_predict_peaks_ws', 
                RegionRadius=0.2, SpecifySize=True, 
                PeakSize=0.09, BackgroundInnerSize=0.11, BackgroundOuterSize=0.14, 
                OutputWorkspace='live_predict_peaks_ws', 
                CutoffIsigI=5, 
                AdaptiveQBackground=True, 
                AdaptiveQMultiplier=0.001, UseOnePercentBackgroundCorrection=False)

            if not self.cell_type is None:
                mtdapi.SelectCellOfType(PeaksWorkspace='live_predict_peaks_ws', 
                    CellType=self.cell_type, Centering=self.centering, Tolerance = self.tolerance, Apply=True, )
                mtdapi.IndexPeaks(PeaksWorkspace='live_predict_peaks_ws', 
                    Tolerance=self.tolerance, ToleranceForSatellite=self.tolerance_satellite, RoundHKLs=False, CommonUBForAll=True)


        def check_peaks_of_current_run():
            live_predict_peaks_ws=mtdapi.mtd['live_predict_peaks_ws']

            #peaks_fname = 'live_%s_Niggli.integrate'%(str(current_run))
            #peaks_ub_fname = 'live_%s_Niggli.mat'%(str(current_run))

            # Set the monitor counts for all the peaks that will be integrated

            num_peaks = live_predict_peaks_ws.getNumberPeaks()
            for i in range(num_peaks):
              peak = live_predict_peaks_ws.getPeak(i)
              intI = peak.getIntensity()
              sigI = peak.getSigmaIntensity()
              self.sum = self.sum + 1
              if intI > (2.0 * sigI):
                self.sig2 = self.sig2 + 1
              if intI > (3.0 * sigI):
                self.sig3 = self.sig3 + 1
              if intI > (5.0 * sigI):
                self.sig5 = self.sig5 + 1
              if intI > (10.0 * sigI):
                self.sig10 = self.sig10 + 1

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
                Filename= self.output_path + self.live_peaks_fname)
            mtdapi.SaveIsawUB(Inputworkspace='live_predict_peaks_ws',  
                Filename= self.output_path + self.live_peaks_ub_fname)

            # Check the overall peak intensity in live_peaks_ws
            self.intensity_ratio =statistics['Mean ((I)/sd(I))']

            self.Rsig = 100.0/self.intensity_ratio
            print("Rsig = %.2f" % self.Rsig)

            if self.intensity_ratio is not None and self.Rsig is not None and self.proton_charge is not None:
                self.proton_charges.append(self.proton_charge)
                self.intensity_ratios.append(self.intensity_ratio)
                self.rsigs.append(self.Rsig)
                self.measure_times.append(self.measure_time)  # Only append if all other values exist
            else:
                print("Skipping entry due to missing data.")
            self.sig2s  = np.append(self.sig2s , self.sig2 )
            self.sig3s  = np.append(self.sig3s , self.sig3 )
            self.sig5s  = np.append(self.sig5s , self.sig5 )
            self.sig10s = np.append(self.sig10s, self.sig10)
            # Save the plot data
            print('measure_times, proton_charges, intensity_ratios, rsigs')
            print(self.measure_times, self.proton_charges, self.intensity_ratios, self.rsigs)
            results = np.column_stack((self.measure_times, self.proton_charges, self.intensity_ratios, self.rsigs))
            np.savetxt(self.output_path + 'live_data_%s_results.csv'%(str(self.current_run)), results, delimiter=',', header='', comments='')

            # Update the plots with new data points
            #plot_data(np.array(measure_times), np.array(intensity_ratios), np.array(rsigs), 'Run time, seconds', 'Peak I/\u03c3(I)', 'Rsig')
    
        def clear_data_after_data_saturation():
            #TODO: to be taken out
            self.cancel_threshold =30 

            if self.intensity_ratio > self.cancel_threshold:
                time.sleep(2)
                # This will cancel both algorithms
                #AlgorithmManager.cancelAll()
                # save results
                mtdapi.SaveIsawPeaks(Inputworkspace='live_predict_peaks_ws', 
                        Filename= self.output_path + self.live_peaks_fname )
                mtdapi.SaveIsawUB(Inputworkspace='live_predict_peaks_ws',  
                        Filename= self.output_path + self.live_peaks_fname )

                # Clear the lists to start plotting fresh data points
                self.proton_charges.clear()
                self.intensity_ratios.clear()
                self.rsigs.clear()
                self.measure_times.clear()

                # Pause briefly to let the plots be updated
                time.sleep(1)
                #print("Intensity ratio exceeds the cancel threshold. Exiting...")

            # Pause briefly to let the plots be updated
            #time.sleep(15)
        print("live data reduction started")
        get_and_update_run_info_of_current_run()
        load_config_of_current_run()
        refine_ub_of_current_run()
        integrate_peaks_of_current_run()
        check_peaks_of_current_run()




        
class TemporalAnalysisModel(BaseModel):
    headers: List[str] = Field(default=["Title", "Comment", "phi", "omega", "Wait For", "Value", "Or Time"])
    #headers: List[str] = Field(default=["Title", "Comment", "BL12:Mot:goniokm:phi", "BL12:Mot:goniokm:omega", "Wait For", "Value", "Or Time"])
    table_test: List[Dict] = Field(default=[{"title":"1","header":"h"}])
    prediction_model_type: str = Field(default="Linear Interpolation", title="Prediction Model")
    prediction_model_type_options: List[str] = ["Linear Interpolation", "Poisson Model"]
    time_steps: List[float] = Field(default=[0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0], title="Time Steps")
    intensity_data: List[float] = Field(default=[0.0, 1.0, 4.0, 9.0, 16.0, 25.0, 36.0, 49.0, 64.0, 81.0], title="Intensity Data")
    variance_data: List[float] = Field(default=[0.0, 0.1, 0.4, 0.9, 1.6, 2.5, 3.6, 4.9, 6.4, 8.1], title="Variance Data")
    uncertainty_data: List[float] = Field(default=[0.0, 0.2, 0.6, 1.2, 2.0, 3.0, 4.2, 5.6, 7.2, 9.0], title="Uncertainty Data")
    #prediction_figure: go.Figure = Field(default_factory=go.Figure, title="Prediction Figure")
    timestamp: float=Field(default=0.0,title="timestamp")
    #mtd_workflow: MantidWorkflow = Field(default=MantidWorkflow(), title="Mantid Workflow")
    mtd_workflow: ClassVar[MantidWorkflow] = MantidWorkflow()

    def get_figure_intensity(self) -> go.Figure:
        #self.timestamp = time.time()
        fig = go.Figure()
        self.time_steps=self.mtd_workflow.measure_times
        intensity_data = self.mtd_workflow.intensity_ratios
        #self.intensity_data = self.mtd_workflow.intensity_ratios

    #    ax_intensity.plot(measure_times, intensity_ratios, '-o', label='Peak I/σ(I)')
    #    ax_rsig.plot(measure_times, rsigs, '-o', label='Rsig')
    #    ax_intensity.set_ylabel('Peak I/σ(I)')
    #    ax_rsig.set_ylabel('Rsig')
    #    ax_rsig.set_xlabel('Run time, seconds')
    #    ax_intensity.grid(True)
        fig.add_trace(go.Scatter(x=self.time_steps, y=intensity_data, mode='lines+markers', name='Intensity Data'))
        #fig.add_trace(go.Scatter(x=self.time_steps, y=self.intensity_data, mode='lines+markers', name='Intensity Data'))
        fig.update_layout(title='Prediction of Intensity'+str(self.timestamp)+" "+str(time.time()), xaxis_title='Time Steps', yaxis_title='Intensity')
        #time.sleep(7)
        return fig
    def get_figure_uncertainty(self) -> go.Figure:
        #self.timestamp = time.time()
        fig = go.Figure()
        time_steps=self.mtd_workflow.measure_times
        uncertainty_data = self.mtd_workflow.rsigs
        #self.time_steps=self.mtd_workflow.measure_times
        #self.uncertainty_data = self.mtd_workflow.rsigs
        fig.add_trace(go.Scatter(x=time_steps, y=uncertainty_data, mode='lines+markers', name='Uncertainty Data'))
        #fig.add_trace(go.Scatter(x=self.time_steps, y=self.uncertainty_data, mode='lines+markers', name='Uncertainty Data'))
        fig.update_layout(title='Prediction of Uncertainty'+str(self.timestamp)+str(time.time()), xaxis_title='Time Steps', yaxis_title='Uncertainty')
        #time.sleep(7)
        return fig

    def get_live_data(self) -> None:
        pass
        
    def generate_prediction_figure(self) -> go.Figure:
        x_data = list(range(10))
        y_data = [i**2 for i in x_data]
        fig = make_subplots(rows=1, cols=2)
        return fig
    def start_reading_live_mtd_data(self) -> None:
    #def start_reading_live_mtd_data(self) -> MantidWorkflow:
        
        #mtd_workflow=MantidWorkflow()
        self.mtd_workflow.start_live_data_collection_instances()
        #self.mtd_workflow=mtd_workflow
        #return mtd_workflow
        #return mtd_workflow

    def get_live_mtd_data(self) -> None:
        while True:
            self.mtd_workflow.live_data_reduction()
            print("live data reduction")
            asyncio.sleep(10)
        