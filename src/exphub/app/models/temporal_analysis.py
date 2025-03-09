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
from sklearn.linear_model import LinearRegression
# import mantid algorithms, numpy and matplotlib
#matplotlib.use("Qt5Agg")
#sys.path.append('/SNS/TOPAZ/shared/PythonPrograms/Python3Library')
#from SCDTools import recenter_peaks_workspace

class MantidWorkflow():
    def __init__(self)->None:
    #def set_up_mantid_info(self)->None:
        print("initializing mtd workflow")
        self.ipts=34069
        self.ipts=35078
        self.ipts=35036
        self.ub_failsafe="/SNS/TOPAZ/IPTS-35078/shared/CrystalPlan/SCO_295K_auto_Orthorhombic_P.mat"
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
        self.maxpeak_idx = -1
        self.timeseries = np.array([])
        self.timeseries_data = np.array([])
    # Check if live data is already running

        self.maxpeak_intI=0

        self.time_interval=1
        self.total_time_of_run=0
        self.total_numberof_time_intervals=1
            # Run the SortHKL algorithm
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

            # Get the first event list
            print("====================================================================================================")
            print("Getting the first event list")
            evList = mtdapi.mtd['live_event_ws'].getSpectrum(0)

            # Add an offset to the pulsetime (wall-clock time) of each event in the list.
            print("First pulse time before addPulsetime: {}".format(evList.getPulseTimes()[0]))
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
            #        exit()
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

            #TODO: protoncharge not updated for live ws
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
            intIlist=np.zeros(num_peaks)
            for i in range(num_peaks):
              peak = live_predict_peaks_ws.getPeak(i)
              intI = peak.getIntensity()
              intIlist[i]=intI
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
            #TODO peaks update
            if self.maxpeak_idx >-1 and self.maxpeak_idx != np.argmax(intIlist):
              print("Warning: Max peak index has changed from ", self.maxpeak_idx, " to ", np.argmax(intIlist))
            if self.maxpeak_idx==-1:
              self.maxpeak_idx=np.argmax(intIlist)
            #self.maxpeak_idx=np.argmax(intIlist)

            self.maxpeak_intI=intIlist[self.maxpeak_idx]

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


            ##############################################################################################
            # time series data
            ##############################################################################################
            print("self.time_interval",self.time_interval)
            print("self.measure_time",self.measure_time)
            print("self.total_time_of_run",self.total_time_of_run)
            print("self.total_numberof_time_intervals",self.total_numberof_time_intervals)
            print("self.timeseries",self.timeseries)    
            self.time_interval=1
            self.total_time_of_run=self.measure_time*1e-0
            self.total_numberof_time_intervals=int(self.total_time_of_run/self.time_interval)
            self.timeseries = np.linspace(start=0, stop= self.total_time_of_run,num=self.total_numberof_time_intervals,endpoint=True)
#            self.timeseries_data = 

            q_frame = 'lab' 
            Q_box = 'Q_' + q_frame            

            ## get hkl limits
            #cell = peaks_ws.mutableSample().getOrientedLattice()

            #max_h = math.ceil(cell.a()*(float(Qmax)/2.0/math.pi))
            #max_k = math.ceil(cell.b()*(float(Qmax)/2.0/math.pi))
            #max_l = math.ceil(cell.c()*(float(Qmax)/2.0/math.pi))
            #max_HKL ='%s,%s,%s'%(max_h,max_k,max_l)
            #min_HKL ='-%s,-%s,-%s'%(max_h,max_k,max_l)

            bin_size = [32, 32, 32]
            bin_size = [2, 2, 2]
            box_size_inhkl=[0.03,0.03,0.03]
            h_box_len,k_box_len,l_box_len = box_size_inhkl
            
            h_bin_num =bin_size[0]
            k_bin_num = bin_size[1]
            l_bin_num = bin_size[2]
        
            print("self.maxpeak_idx",self.maxpeak_idx)
            peak = live_predict_peaks_ws.getPeak(int(self.maxpeak_idx))
            h,k,l=peak.getHKL()


            max_h = 20           
            max_k = 20
            max_l = 20
            max_HKL ='%s,%s,%s'%(max_h,max_k,max_l)
            min_HKL ='-%s,-%s,-%s'%(max_h,max_k,max_l)
            self.timeseries_data   = np.array([])
            for i in range(len(self.timeseries)-1):
                start_time = self.timeseries[i]*1.0
                stop_time = self.timeseries[i+1]*1.0
                mtdapi.FilterByTime(InputWorkspace='live_event_ws', OutputWorkspace='timestep_event_ws',
                                StartTime=start_time, StopTime=stop_time)
                mtdapi.ConvertToMD(InputWorkspace='timestep_event_ws', 
                                QDimensions='Q3D', dEAnalysisMode='Elastic', 
                                Q3DFrames=Q_box, QConversionScales='HKL', 
                                Uproj='1,0,0', Vproj='0,1,0', Wproj='0,0,1',
                                MinValues=min_HKL, MaxValues=max_HKL)
                #mtdapi.BinMD(InputWorkspace='timestep_event_ws', AlignedDim0='Q_sample_x,-0.5,0.5,1',
                #    AlignedDim1='Q_sample_y,-0.5,0.5,1', AlignedDim2='Q_sample_z,-0.5,0.5,1',
                #    OutputWorkspace='timestep_HKL_ws')


                mtdapi.BinMD(InputWorkspace='timestep_event_ws', AlignedDim0='[H,0,0],{},{},{}'.format(h-h_box_len,h+h_box_len,h_bin_num), 
                                             AlignedDim1='[0,K,0],{},{},{}'.format(k-k_box_len,k+k_box_len,k_bin_num),
                                             AlignedDim2='[0,0,L],{},{},{}'.format(l-l_box_len,l+l_box_len,l_bin_num),
                                            OutputWorkspace='timestep_HKL_ws')
                    #                         OutputWorkspace='HKL=({:.2f},{:.2f},{:.2f})_binslice'.format(h,k,l))

                data = mtdapi.mtd['timestep_HKL_ws']
                signal_array = data.getSignalArray().copy()
                self.timeseries_data = np.append(self.timeseries_data,signal_array)
                #print(signal_array)
                #print(signal_array.shape)
            print("self.timeseries_data") 
            print(self.timeseries_data.shape)
            print(self.timeseries_data)
            


        def get_time_series_data()->np.array:
            

            peaks_ws=mtdapi.LoadIsawPeaks(Filename=peaks_filename)
            mtdapi.LoadIsawUB(InputWorkspace='peaks_ws', Filename=UB_filename)
            mtdapi.IndexPeaks(PeaksWorkspace='peaks_ws', Tolerance=tolerance, ToleranceForSatellite=tolerance_satellite, 
                    RoundHKLs=False, CommonUBForAll=True)

            MDEW=mtdapi.ConvertToMD(InputWorkspace='event_ws', 
                            QDimensions='Q3D', dEAnalysisMode='Elastic', 
                            Q3DFrames=Q_box, QConversionScales='HKL', 
                            Uproj='1,0,0', Vproj='0,1,0', Wproj='0,0,1',
                            MinValues=min_HKL, MaxValues=max_HKL)

            # if not os.path.exists(plot_folder):
            #     os.makedirs(plot_folder)

            UB = peaks_ws.sample().getOrientedLattice().getUB()
            banks = mtd['peaks_ws'].column(13)

            peak_numbers = [1]
            #peak_numbers = [167,168,169,170,171,172,173,174,175,176]
            print(len(peak_numbers))

            for i in peak_numbers:
            #for i in range(peaks_ws.getNumberPeaks()):
                signal_array = []
                H_array = []
                K_array = []
                L_array = []

                peak =peaks_ws.getPeak(i)
                peak_index=peak.getPeakNumber()
                h,k,l=peak.getHKL()
                col=peak.getCol()
                row=peak.getRow()
                dn = int(banks[i].strip('bank'))

                # l_min = l-fracHKL[2]
                # l_max = l+fracHKL[2]

                # l_step = (l_max-l_min)/(l_bins-1)

                # BinMD(InputWorkspace='MDEW', AlignedDim0='[H,0,0],{},{},{}'.format(h-0.5,h+0.5,h_bin_num), 
                #                              AlignedDim1='[0,K,0],{},{},{}'.format(k-0.5,k+0.5,k_bin_num),
                #                              AlignedDim2='[0,0,L],{},{},1'.format(l-l_step,l+l_step), 
                #                              OutputWorkspace='HKL=({:.2f},{:.2f},{:.2f})_binslice'.format(h,k,l)) 

                BinMD(InputWorkspace='MDEW', AlignedDim0='[H,0,0],{},{},{}'.format(h-0.5,h+0.5,h_bin_num), 
                                             AlignedDim1='[0,K,0],{},{},{}'.format(k-0.5,k+0.5,k_bin_num),
                                             AlignedDim2='[0,0,L],{},{},{}'.format(l-0.5,l+0.5,l_bin_num),
                                             OutputWorkspace='HKL=({:.2f},{:.2f},{:.2f})_binslice'.format(h,k,l))

                data = mtd['HKL=({:.2f},{:.2f},{:.2f})_binslice'.format(h,k,l)]

                signal_array = data.getSignalArray().copy()
            return signal_array

    
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
        print("============================================================================================")
        print("live data reduction started")
        print("============================================================================================")
        get_and_update_run_info_of_current_run()
        load_config_of_current_run()
        refine_ub_of_current_run()
        integrate_peaks_of_current_run()
        check_peaks_of_current_run()

#class TemporalData(BaseModel):
#    time: float
#    intensity: float
#    variance: float
#    uncertainty: float
#
#import math
'''
class PoissonModelAnalysis(BaseModel):

    # Load the monitor data and get the counting time in seconds
    event_ws = mtdapi.LoadNexusMonitors( Filename=data_filename  )
    total_time = event_ws.run()['duration'].value
    print('data collection time {:0.0f} seconds'.format(total_time))
    MultiplierBase=1.0
    time_interval=1
    if total_time >=time_interval:
        if MultiplierBase<=1:
            number_of_steps = ( total_time - time_interval ) /time_interval
        else:
            number_of_steps = ( math.log(total_time) - math.log(time_interval) ) / math.log(MultiplierBase)
        number_of_steps = int(number_of_steps) + 1
        print('\nnumber_of_steps = ', number_of_steps)
        print('')
    else:
        print('\data collection time is less than the time interval of {:0f} seconds'.format(time_interval))

    peaks_ws=mtdapi.LoadIsawPeaks(Filename=peaks_filename)
    mtdapi.LoadIsawUB(InputWorkspace='peaks_ws', Filename=UB_filename)
    mtdapi.IndexPeaks(PeaksWorkspace='peaks_ws', Tolerance=tolerance, ToleranceForSatellite=tolerance_satellite, 
            RoundHKLs=False, CommonUBForAll=True)

    # Begin loop to integrate peaks and analyze statistics
    #

    print(f'Total time: {total_time}')

    n_step = 1                
    while True:
        #time_stop = time_interval * MultiplierBase**n_step
        time_stop = time_interval * MultiplierBase * n_step
        print('--- time_stop: {}, time_interval: {}, MultiplierBase: {}, n_step: {}, total_time: {}'
            .format(time_stop, time_interval, MultiplierBase, n_step, total_time))
        if time_stop <= total_time:
            event_ws = mtdapi.Load( Filename=data_filename, 
                               FilterByTofMin=min_tof, FilterByTofMax=max_tof,
                               FilterByTimeStop = time_stop
                            )
            event_ws = mtdapi.FilterBadPulses(InputWorkspace=event_ws, LowerCutoff = 85)
            proton_charge = event_ws.getRun().getProtonCharge() * 1000.0  # proton charge scaled up to match detector counts
            mtdapi.LoadIsawDetCal(event_ws, Filename=calibration_file) 
            mtdapi.LoadIsawUB(InputWorkspace=event_ws, Filename=UB_filename)

            #MDEW=ConvertToMD(InputWorkspace=event_ws, QDimensions='Q3D', 
            #    dEAnalysisMode='Elastic', Q3DFrames='Q_sample', LorentzCorrection=True, 
            #    MinValues=minQ, MaxValues=maxQ, SplitInto='2', 
            #    SplitThreshold=60, MaxRecursionDepth=13, MinRecursionDepth=7)

            #peaks_ws=LoadIsawPeaks(Filename=peaks_filename)
            #LoadIsawUB(InputWorkspace='peaks_ws', Filename=UB_filename)
            #IndexPeaks(PeaksWorkspace='peaks_ws', Tolerance=tolerance, ToleranceForSatellite=tolerance_satellite, RoundHKLs=False, CommonUBForAll=True)

            #FindUBUsingIndexedPeaks(PeaksWorkspace=peaks_ws, 
            #                Tolerance=tolerance,
            #                ToleranceForSatellite=tolerance_satellite, CommonUBForAll=True)
            #SelectCellOfType(PeaksWorkspace=peaks_ws, CellType='Hexagonal', Apply=True, AllowPermutations=True)
            #IndexPeaks(PeaksWorkspace=peaks_ws, Tolerance=tolerance, ToleranceForSatellite=tolerance_satellite, 
            #    RoundHKLs=False, 
            #    ModVector1='0,0,0.5', 
            #    MaxOrder=1, 
            #    CrossTerms=False, 
            #    SaveModulationInfo=True,
            #    CommonUBForAll=True)
            #peaks_ws=FilterPeaks(InputWorkspace=peaks_ws, FilterVariable='h^2+k^2+l^2', FilterValue=0, Operator='>')
            #FindUBUsingIndexedPeaks(PeaksWorkspace=peaks_ws, 
            #                Tolerance=tolerance,
            #                ToleranceForSatellite=tolerance_satellite,CommonUBForAll=True)
            #IndexPeaks(PeaksWorkspace=peaks_ws, Tolerance=tolerance, ToleranceForSatellite=tolerance_satellite, RoundHKLs=False, CommonUBForAll=True)
            #OptimizeLatticeForCellType(PeaksWorkspace=peaks_ws, CellType='Hexagonal', Apply=True, Tolerance=0.06, EdgePixels=19, OutputDirectory='/SNS/TOPAZ/shared/test/Integrate_satellite_peaks')
            #IndexPeaks(PeaksWorkspace=peaks_ws, Tolerance=tolerance, ToleranceForSatellite=tolerance_satellite, RoundHKLs=False, CommonUBForAll=True)

            mtdapi.CopySample(InputWorkspace=peaks_ws, 
                    OutputWorkspace='event_ws', CopyName=False, CopyMaterial=False, CopyEnvironment=False, CopyShape=False)
            if q_frame == ('lab' or 'sample'):
                Q_box = 'Q_' + q_frame
                MDEW = mtdapi.ConvertToMD(InputWorkspace=event_ws, QDimensions='Q3D', 
                        dEAnalysisMode='Elastic', Q3DFrames=Q_box, 
                        LorentzCorrection=False,
                        MinValues=minQ, MaxValues=maxQ)

            elif q_frame==('HKL' or 'hkl'):
                Q_box='HKL'
            if peaks_ws.sample().hasOrientedLattice():
                # get hkl limits
                cell = peaks_ws.mutableSample().getOrientedLattice()
                max_h = math.ceil(cell.a()*(float(Qmax)/2.0/math.pi))
                max_k = math.ceil(cell.b()*(float(Qmax)/2.0/math.pi))
                max_l = math.ceil(cell.c()*(float(Qmax)/2.0/math.pi))
                max_HKL ='%s,%s,%s'%(max_h,max_k,max_l)
                min_HKL ='-%s,-%s,-%s'%(max_h,max_k,max_l)
            else:
                print('Error: No UB matrix')
                #break
            print('\nReducing data in HKL space ...')
            MDEW=mtdapi.ConvertToMD(InputWorkspace='event_ws', 
                            QDimensions='Q3D', dEAnalysisMode='Elastic', 
                            Q3DFrames=Q_box, QConversionScales='HKL', 
                            Uproj='1,0,0', Vproj='0,1,0', Wproj='0,0,1',
                            MinValues=min_HKL, MaxValues=max_HKL)

            # if not os.path.exists(plot_folder):
            #     os.makedirs(plot_folder)

            UB = peaks_ws.sample().getOrientedLattice().getUB()
            banks = mtd['peaks_ws'].column(13)

            peak_numbers = [167,168,169,170,171,172,173,174,175,176]
            print(len(peak_numbers))

            for i in peak_numbers:
            #for i in range(peaks_ws.getNumberPeaks()):
                signal_array = []
                H_array = []
                K_array = []
                L_array = []

                peak =peaks_ws.getPeak(i)
                peak_index=peak.getPeakNumber()
                h,k,l=peak.getHKL()
                col=peak.getCol()
                row=peak.getRow()
                dn = int(banks[i].strip('bank'))

                # l_min = l-fracHKL[2]
                # l_max = l+fracHKL[2]

                # l_step = (l_max-l_min)/(l_bins-1)

                # BinMD(InputWorkspace='MDEW', AlignedDim0='[H,0,0],{},{},{}'.format(h-0.5,h+0.5,h_bin_num), 
                #                              AlignedDim1='[0,K,0],{},{},{}'.format(k-0.5,k+0.5,k_bin_num),
                #                              AlignedDim2='[0,0,L],{},{},1'.format(l-l_step,l+l_step), 
                #                              OutputWorkspace='HKL=({:.2f},{:.2f},{:.2f})_binslice'.format(h,k,l)) 

                BinMD(InputWorkspace='MDEW', AlignedDim0='[H,0,0],{},{},{}'.format(h-0.5,h+0.5,h_bin_num), 
                                             AlignedDim1='[0,K,0],{},{},{}'.format(k-0.5,k+0.5,k_bin_num),
                                             AlignedDim2='[0,0,L],{},{},{}'.format(l-0.5,l+0.5,l_bin_num),
                                             OutputWorkspace='HKL=({:.2f},{:.2f},{:.2f})_binslice'.format(h,k,l))

                data = mtd['HKL=({:.2f},{:.2f},{:.2f})_binslice'.format(h,k,l)]

                signal_array = data.getSignalArray().copy()
                # H, K, L = np.meshgrid(*[np.linspace(data.getDimension(i).getMinimum(),data.getDimension(i).getMaximum(),data.getDimension(i).getNBins()) for i in range(data.getNumDims())])


                #####  save 3D slices (md nexus files)
                # print('--- Saving SaveMD for .nxs for step: {}.....'.format(time_stop))
                # SaveMD(data, output_directory + '/' + 'TOPAZ_{0:d}_peak_{1:d}_step_{2:d}_ORIGINAL.nxs'.format(run, i, n_step))


                peakdir=output_directory+'npy/peak_{0:d}_res_{1:d}/'.format(i, bin_size[0])
                peakfilename='run_{0:d}_peak_number_{1:d}_time_step_{2:d}_data.npy'.format( run,i,n_step)
                if not os.path.exists(peakdir): os.makedirs(peakdir) 
                np.save(peakdir+peakfilename, signal_array)
                # np.save(output_directory+'/npy/peak_{0:d}/run_{1:d}_peak_number_{2:d}_time_step_{3:d}_grid_H.npy'.format(i, run,i,n_step), H_array)
                # np.save(output_directory+'/npy/peak_{0:d}/run_{1:d}_peak_number_{2:d}_time_step_{3:d}_grid_K.npy'.format(i, run,i,n_step), K_array)
                # np.save(output_directory+'/npy/peak_{0:d}/run_{1:d}_peak_number_{2:d}_time_step_{3:d}_grid_L.npy'.format(i, run,i,n_step), L_array)

                ####### tmp commented ##############
        if time_stop >= total_time: break
        print(time_stop)
        print(total_time)
        n_step = n_step + 1

        #plt.close('all')
'''
        
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
    all_time: List[float] = Field(default=[0.0, 10000], title="All Time")
    #mtd_workflow: MantidWorkflow = Field(default=MantidWorkflow(), title="Mantid Workflow")
    mtd_workflow: ClassVar[MantidWorkflow] = MantidWorkflow()

    def get_figure_intensity(self) -> go.Figure:
        #self.timestamp = time.time()
        fig = go.Figure()
        #self.time_steps=self.mtd_workflow.measure_times
        time_steps=self.mtd_workflow.measure_times
        intensity_data = self.mtd_workflow.intensity_ratios
        print("============================================================================================")
        print("time_steps = self.mtd_workflow.measure_times")
        print(time_steps , self.mtd_workflow.measure_times )
        print("intensity_data = self.mtd_workflow.intensity_ratios")
        print(intensity_data , self.mtd_workflow.intensity_ratios )
        print("============================================================================================")
        #self.intensity_data = self.mtd_workflow.intensity_ratios
        # Reshape the data for sklearn
        X = np.array(time_steps).reshape(-1, 1)
        y = np.array(intensity_data)

        # Create and fit the model
        model = LinearRegression()
        model.fit(X, y)

        # Get the slope (coefficient) and intercept
        slope = model.coef_[0]
        intercept = model.intercept_

        print(f"Slope: {slope}, Intercept: {intercept}")

    #    ax_intensity.plot(measure_times, intensity_ratios, '-o', label='Peak I/σ(I)')
    #    ax_rsig.plot(measure_times, rsigs, '-o', label='Rsig')
    #    ax_intensity.set_ylabel('Peak I/σ(I)')
    #    ax_rsig.set_ylabel('Rsig')
    #    ax_rsig.set_xlabel('Run time, seconds')
    #    ax_intensity.grid(True)
    # Add a dashed line with the slope and intercept
        x_range = np.linspace(min(time_steps), max(time_steps), 100)
        y_range = slope * x_range + intercept
        fig.add_trace(go.Scatter(x=x_range, y=y_range, mode='lines', name='Fitted Line', line=dict(dash='dash')))
        fig.add_trace(go.Scatter(x=time_steps, y=intensity_data, mode='lines+markers', name='Intensity Data'))
        #fig.add_trace(go.Scatter(x=self.time_steps, y=intensity_data, mode='lines+markers', name='Intensity Data'))
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
        # Fit the data with 1/x
        X = np.array(time_steps).reshape(-1, 1)
        y = np.array(uncertainty_data)

        # Transform X to 1/X
        X_transformed = 1 / X

        # Create and fit the model
        model = LinearRegression()
        model.fit(X_transformed, y)

        # Get the slope (coefficient) and intercept
        slope = model.coef_[0]
        intercept = model.intercept_

        print(f"Slope: {slope}, Intercept: {intercept}")

        # Add a dashed line with the slope and intercept
        x_range = np.linspace(min(time_steps), max(time_steps), 100)
        y_range = slope * (1 / x_range) + intercept
        fig.add_trace(go.Scatter(x=x_range, y=y_range, mode='lines', name='Fitted Line', line=dict(dash='dash')))
        print("============================================================================================")
        print("time_steps = self.mtd_workflow.measure_times")
        print(time_steps , self.mtd_workflow.measure_times )
        print("uncertainty_data = self.mtd_workflow.rsigs")
        print(uncertainty_data , self.mtd_workflow.rsigs )
        print("============================================================================================")
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
        