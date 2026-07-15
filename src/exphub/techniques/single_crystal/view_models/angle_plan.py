"""View model for angle plan."""

import logging
from typing import List

from ....core.beamline import active
from .steering import SingleCrystalSteeringViewModel

logger = logging.getLogger(__name__)

# from ..models.ccs_status import CCSStatusModel
# from ..models.temporal_analysis import TemporalAnalysisModel

'''
class AnglePlanViewModel:
    """Viewmodel class, used to create data<->view binding and react on changes from GUI."""

    def __init__(self, angleplanmodel: AnglePlanModel, binding: BindingInterface):
        #self.model = model
        self.angleplan_model = angleplanmodel
        #self.angleplan = AnglePlanModel()

        # here we create a bind that connects ViewModel with View. It returns a communicator object,
        # that allows to update View from ViewModel (by calling update_view).
        # self.model will be updated automatically on changes of connected fields in View,
        # but one also can provide a callback function if they want to react to those events
        # and/or process errors.
        #self.model_bind = binding.new_bind(self.model, callback_after_update=self.change_callback)

        #self.experimentinfo_bind = binding.new_bind(self.model.experimentinfo, callback_after_update=self.change_callback)
        self.angleplan_bind = binding.new_bind(self.angleplan_model, callback_after_update=self.change_callback)
        #self.eiccontrol_bind = binding.new_bind(self.model.eiccontrol, callback_after_update=self.change_callback)
        #self.newtabtemplate_bind = binding.new_bind(self.model.newtabtemplate, callback_after_update=self.change_callback)




    def change_callback(self, results: Dict[str, Any]) -> None:
        if results["error"]:
            print(f"error in fields {results['errored']}, model not changed")
        else:
            print(f"model fields updated: {results['updated']}")

    def update_view(self) -> None:
        self.angleplan_model.load_ap(self.angleplan_model.plan_file)
        self.angleplan_bind.update_in_view(self.angleplan_model)

    def submit_angle_plan(self) -> None:
        #print("submit_angle_plan")
        self.model.eiccontrol.submit_eic(
            self.model.angleplan.angle_list,
            goniometer_type=self.model.angleplan.goniometer_type,
        )
        self.update_view()

    def call_load_token(self) -> None:
        self.model.eiccontrol.load_token(self.model.eiccontrol.token_file)
        self.update_view()


from ..models.main_model import MainModel
from ..models.plotly import PlotlyConfig
from pyvista import Plotter  # just for typing
from ..models.pyvista import PyVistaConfig


class MainViewModel:
    """Viewmodel class, used to create data<->view binding and react on changes from GUI."""

    def __init__(self, model: MainModel, binding: BindingInterface):
        self.model = model
        self.plotly_config = PlotlyConfig()
        self.pyvista_config = PyVistaConfig()

        self.plotly_config_bind = binding.new_bind(
            linked_object=self.plotly_config, callback_after_update=self.update_plotly_figure
        )
        self.plotly_figure_bind = binding.new_bind(linked_object=self.plotly_config)
        self.pyvista_config_bind = binding.new_bind(linked_object=self.pyvista_config)
        # here we create a bind that connects ViewModel with View. It returns a communicator object,
        # that allows to update View from ViewModel (by calling update_view).
        # self.model will be updated automatically on changes of connected fields in View,
        # but one also can provide a callback function if they want to react to those events
        # and/or process errors.
        self.config_bind = binding.new_bind(self.model, callback_after_update=self.change_callback)

    def change_callback(self, results: Dict[str, Any]) -> None:
        if results["error"]:
            print(f"error in fields {results['errored']}, model not changed")
        else:
            print(f"model fields updated: {results['updated']}")
    def update_pyvista_volume(self, plotter: Plotter) -> None:
        self.pyvista_config.render(plotter)

    def update_view(self) -> None:
        self.config_bind.update_in_view(self.model)
    def update_plotly_figure(self, _: Any = None) -> None:
        self.plotly_config_bind.update_in_view(self.plotly_config)
        self.plotly_figure_bind.update_in_view(self.plotly_config.get_figure())

'''  # noqa


def angleplan_optimize(view_model: SingleCrystalSteeringViewModel) -> List:
    import mantid.simpleapi as mtdapi
    import numpy as np
    from mantid.geometry import PointGroupFactory
    from mantid.simpleapi import mtd

    # import NeuXtalViz.models.ap_test_v2 as ap_test_v2
    from ..models.angle_plan_engine import (
        DetectorInstrument,
        QGrids,
    )

    # from ap_test_v2 import DetectorPane, DetectorInstrument, QGrids
    # from ap_test_v2 import optimize_angle_with_fixed_given as oa
    # from ap_test_v2 import analyze_peaks
    logger.debug("=========================================================================")
    logger.debug("==========================angle plan test================================")
    logger.debug("=========================================================================")

    instrument = active().mantid_instrument_name
    # wavelength = view_model.model.experimentinfo.wavelength
    # axes = view_model.model.experimentinfo.axes
    # limits = view_model.model.experimentinfo.limits
    # UB = view_model.model.experimentinfo.UB
    # d_min = view_model.model.experimentinfo.d_min
    # d_max = view_model.model.experimentinfo.d_max
    # offset = view_model.model.experimentinfo.offset
    point_group = view_model.model.experimentinfo.point_group
    # lattice_centering = view_model.model.experimentinfo.lattice_centering

    logger.debug("%s %s", "self.instrument        ", instrument)
    # print('self.wavelength        ',wavelength        )
    # print('self.axes              ',axes              )
    # print('self.limits            ',limits            )
    # print('self.UB                ',UB                )
    # print('self.d_min             ',d_min             )
    # print('self.d_max             ',d_max             )
    # print('self.offset            ',offset            )
    logger.debug("%s %s", "self.point_group       ", point_group)
    # print('self.lattice_centering ',lattice_centering )

    #####################

    logger.debug("--------------------------peak input list--------------------------------")
    # print('peaks',peaks)
    logger.debug("--------------------------UB read--------------------------------")
    ub = np.array(
        [
            [-0.06196579, -0.0646735, 0.00629365],
            [0.05857223, -0.05941086, -0.03262031],
            [0.02816059, -0.01873959, 0.08169699],
        ]
    )
    # if self.has_UB('coverage'):
    #    UB = mtd['coverage'].sample().getOrientedLattice().getUB().copy()
    # else:
    #    UB=np.array([[-0.06196579 ,-0.0646735 ,  0.00629365],
    #                 [ 0.05857223, -0.05941086, -0.03262031],
    #                 [ 0.02816059, -0.01873959,  0.08169699]])
    # print('UB',UB)

    logger.debug("--------------------------symmetry read--------------------------------")
    # laue='m-3'
    # print('Laue',laue)
    # symmetry = self.get_symmetry_transforms(laue)
    # print('symmtries:',symmetry)

    logger.debug("--------------------------euler angle range--------------------------------")
    logger.debug("--------------------------instrument setup--------------------------------")
    mtdapi.LoadEmptyInstrument(InstrumentName=instrument, OutputWorkspace="instrument")

    mtdapi.ExtractMonitors(InputWorkspace="instrument", DetectorWorkspace="instrument", MonitorWorkspace="montitors")

    mtdapi.PreprocessDetectorsToMD(InputWorkspace="instrument", OutputWorkspace="detectors", GetMaskState=False)

    l2 = np.array(mtd["detectors"].column(1)).reshape(-1, 256, 256)
    two_theta = np.array(mtd["detectors"].column(2)).reshape(-1, 256, 256)
    az_phi = np.array(mtd["detectors"].column(3)).reshape(-1, 256, 256)
    logger.debug("%s %s", "L2", l2)

    # TODO: get L1 in cm
    # L1 = np.array(mtd['detectors'].column(1)).reshape(-1, 256,256)
    # l1 = 1800

    x = l2 * 100 * np.sin(two_theta) * np.cos(az_phi)
    y = l2 * 100 * np.sin(two_theta) * np.sin(az_phi)
    z = l2 * 100 * np.cos(two_theta)

    det_ins_parameter = []
    num_pane = x.shape[0]
    for idx_pane in range(num_pane):
        pane_vertices = np.array(
            [
                [x[idx_pane, 0, 0], y[idx_pane, 0, 0], z[idx_pane, 0, 0]],
                [x[idx_pane, 0, -1], y[idx_pane, 0, -1], z[idx_pane, 0, -1]],
                [x[idx_pane, -1, 0], y[idx_pane, -1, 0], z[idx_pane, -1, 0]],
                [x[idx_pane, -1, -1], y[idx_pane, -1, -1], z[idx_pane, -1, -1]],
            ]
        )
        pane_vertices = np.array(
            [
                [x[idx_pane, 10, 10], y[idx_pane, 10, 10], z[idx_pane, 10, 10]],
                [x[idx_pane, 10, -11], y[idx_pane, 10, -11], z[idx_pane, 10, -11]],
                [x[idx_pane, -11, 10], y[idx_pane, -11, 10], z[idx_pane, -11, 10]],
                [x[idx_pane, -11, -11], y[idx_pane, -11, -11], z[idx_pane, -11, -11]],
            ]
        )
        # print('detector pane vertices:',pane_vertices)
        det_ins_parameter.append(
            {
                "pane_id": idx_pane,
                "pane_shape": "rectangle",
                "pane_parameter": {"vertices": pane_vertices, "t_min": 1000, "t_max": 16000},
            }
        )
    # det_ins_parameter=[det_ins_parameter[0]]
    multi_detector_system = DetectorInstrument(det_ins_parameter)
    multi_detector_system.initialize_detector()

    #############################################################
    # pass to angle plan
    ################################################################
    view_model.model.angleplan.qpane_cones = []

    for idx_pane in range(num_pane):
        pane = multi_detector_system.detector_panes[idx_pane]
        qv0 = pane.qvertices.copy()
        qf0 = pane.qfaces.copy()
        qv1 = [i.tolist() for i in qv0]
        qf1 = [[t.tolist() for t in qf0[i]] for i in qf0.keys()]
        view_model.model.angleplan.qpane_cones.append({"pane_id": idx_pane, "qvertices": qv1, "qfaces": qf1})

        ##################################################################################
        # each qface is 6 surface of cube
        # each face has 4 vertices[ 0,1,2,3]
        # shaped as
        #  0---1
        #  |   |
        #  2---3
        ##################################################################################

    logger.debug("-------------------------grids setup-----------------------------")
    # Qmax=multi_detector_system.get_max_Q()
    # Qmin=multi_detector_system.get_min_Q()
    # Qmax=10
    # Qmin=0
    # grid_parameter={'Nx':10,'Ny':10,'Nz':10,'Qmax':Qmax,'Qmin':Qmin}
    # grids=QGrids(grid_mode='uniform',grid_parameter=grid_parameter)
    # print(grid_parameter)
    # print(grids.points.shape)

    qhmax = 10
    qkmax = 10
    qlmax = 10
    qh = np.linspace(-qhmax, qhmax, 2 * qhmax + 1)
    qk = np.linspace(-qkmax, qkmax, 2 * qkmax + 1)
    ql = np.linspace(-qlmax, qlmax, 2 * qlmax + 1)

    qhkl_irr_h, qhkl_irr_k, qhkl_irr_l = np.meshgrid(qh, qk, ql)
    # qhkl_irr_h,qhkl_irr_k,qhkl_irr_l=np.meshgrid(np.arange(qhmax),np.arange(qkmax),np.arange(qlmax),indexing='ij')

    qhkl_irr_h_flat = qhkl_irr_h.flatten()
    qhkl_irr_k_flat = qhkl_irr_k.flatten()
    qhkl_irr_l_flat = qhkl_irr_l.flatten()
    # qhkl_irr=np.column_stack((qhkl_irr_h_flat,qhkl_irr_k_flat,qhkl_irr_l_flat)).T
    qhkl_irr = np.column_stack((qhkl_irr_h_flat, qhkl_irr_k_flat, qhkl_irr_l_flat))

    logger.debug("%s %s", "qhkl_irr shape", qhkl_irr.shape)

    pg = PointGroupFactory.createPointGroup(point_group)
    so = pg.getSymmetryOperations()
    logger.debug("%s %s", "symmetry operations:", so)
    # qhkl_sym_list=[]
    qlab_sym_list = []
    a = np.array([1, 0, 0])
    b = np.array([0, 1, 0])
    c = np.array([0, 0, 1])
    symmetry_operations = []
    for sym in so:
        qhkl_sym = [sym.transformHKL(q) for q in qhkl_irr]
        qlab = np.array(qhkl_sym) @ (ub).T
        # qhkl_sym_list.append(qlab)
        logger.debug("%s %s", "symmetry operation:", sym)
        qlab_sym_list.append(qlab)
        tsyma = sym.transformHKL(a)
        tsymb = sym.transformHKL(b)
        tsymc = sym.transformHKL(c)
        tsym = np.array([tsyma, tsymb, tsymc]).tolist()
        logger.debug("%s %s %s", tsyma, tsymb, tsymc)
        logger.debug("%s %s", "symmetry operation:", tsym)
        symmetry_operations.append(tsym)
        logger.debug("%s %s", "symmetry operation:", symmetry_operations)
    view_model.model.angleplan.symmetry_operations = symmetry_operations

    # print('qhkl_sym_list length and shape',len(qhkl_sym_list),qhkl_sym_list[-1].shape)
    logger.debug("%s %s %s", "qlab_sym_list length and shape", len(qlab_sym_list), qlab_sym_list[-1].shape)

    grid_parameter = {"num_sym": len(qlab_sym_list), "qlist": qlab_sym_list}
    # grid_parameter={'Nx':10,'Ny':10,'Nz':10,'Qmax':Qmax,'Qmin':Qmin}
    grids = QGrids(grid_mode="input", grid_parameter=grid_parameter)
    if grids.points:
        logger.debug("%s %s", "grids shape", grids.points[0].shape)

    logger.debug("-------------------------initial coverage calculation-----------------------------")
    logger.debug("coverage calculation")

    coverage_results = grids.get_coverage(multi_detector_system)
    # print(grids.mask.shape)
    logger.debug("%s %s %s", "initial coverage", np.sum(coverage_results) * 100 / np.size(coverage_results), "%")
    # print(grids.points.shape)
    # print(grids.points[:100,:])
    # print('shape coverage',coverage_results.shape)
    # print(coverage_results[:100,:])

    logger.debug("-------------------------analyze peak-----------------------------")
    # peaks_list=[peak for peak in peaks.values()]
    # analyze_peaks(peaks_list,UB,multi_detector_system,symmetry)

    logger.debug("-------------------------ask for and set initial angles list-----------------------------")
    logger.debug("            ---------------------not implemented---------------------------")
    logger.debug("-------------------------optimize angle-----------------------------")
    # fixed_angle_list = np.array([[0, 135, 0]])
    fixed_angle_list = [[0, 135, 0]]
    logger.debug("%s %s", "fixed_angle_list:", fixed_angle_list)
    # euler_angle_range = [[0, 360, 1], [135, 135, 1], [0, 360, 1]]

    ############################################### optimization #######################################
    # final_angle_list,final_coverage=optimize_angle_with_fixed_given(grids,multi_detector_system,fixed_angle_list,euler_angle_range)#noqa
    # print("Detector Coverage Results: ", np.sum(final_coverage)/np.size(final_coverage)*100,'%')
    # return final_angle_list

    # final_angle_list = []
    return []

    exit("debug")
    logger.debug("------------------------- visualizie-----------------------------")
    ## Define vertices
    # vertices = np.array([
    #    [0, 0, 0],
    #    [1, 0, 0],
    #    [1, 1, 0],
    #    [0, 1, 0],
    #    [0, 0, 1],
    #    [1, 0, 1],
    #    [1, 1, 1],
    #    [0, 1, 1],
    # ])

    ## Define faces
    # faces = np.array([
    #    [4, 0, 1, 2, 3],  # bottom
    #    [4, 4, 5, 6, 7],  # top
    #    [4, 0, 1, 5, 4],  # front
    #    [4, 1, 2, 6, 5],  # right
    #    [4, 2, 3, 7, 6],  # back
    #    [4, 3, 0, 4, 7],  # left
    # ])

    # self.polyhedron_data=[]
    # for pane in multi_detector_system.detector_panes:
    #    vr=np.array(pane.rvertices)
    #    sr= np.array([ [4, 0, 1, 3, 2]])
    #    vq=np.array(pane.qfaces['0']+pane.qfaces['5'])
    #    sq= np.array([
    #                   [4, 0, 1, 3, 2],  # bottom
    #                   [4, 4, 5, 7, 6],  # top
    #                   [4, 0, 1, 5, 4],  # front
    #                   [4, 1, 3, 7, 5],  # right
    #                   [4, 3, 2, 6, 7],  # back
    #                   [4, 2, 0, 4, 6],  # left
    #                     ])
    #    self.polyhedron_data.append([vq,sq])
    #    #self.polyhedron_data.append([vr,sr])

    ##self.polyhedron_data=[vertices,faces]
    ##self.polyhedron_data=[[vertices,faces],[vertices+.5,faces]]
    # self.polyhedron_data.append([grids.points,np.array([ [0 ]])])
    ##print(self.polyhedron_data)


#
