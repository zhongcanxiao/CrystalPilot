# ruff: noqa
# mypy: ignore-errors

from dataclasses import dataclass, field
from itertools import product
from typing import Any, Dict, List, Union

import numpy as np
import logging

logger = logging.getLogger(__name__)

# units in code and input: length (cm), time(microsec), wavevector (A^-1)

zero_eps = 1e-4
m_neutron = 1.67492750056e-27  # kg
hbar = 1.05457182e-34  #  m^2 kg / s

vtok = 1e4 * m_neutron / hbar * 1e-10  # v (cm/micros) to k (A^-1)
vtok = 15.8825361042


class DetectorPane:
    def __init__(
        self,
        pane_id,
        pane_shape: str,
        L1=1800,
        pane_parameter: Union[int, float, np.array, Dict[str, Any], None] = None,
    ):
        self.pane_shape = pane_shape
        self.pane_id = pane_id
        self.pane_parameter = pane_parameter
        # [{'pane_id':0,'pane_shape':'rectangle','pane_parameter':{'vertices':[4x3],'t_min':100,'t_max':16000 }}]
        self.L1 = L1

    #        self.setup_pane_cone()

    def _shape_notsupported(self):
        raise ValueError("{} detector not supported".format(self.pane_shape))

    def setup_pane_cone(self):
        # Mapping of setup methods
        pane_setup_methods = {"rectangle": self._setup_rectangle_pane_cone}
        # Select and call appropriate setup method
        setup_cone = pane_setup_methods.get(self.pane_shape, self._shape_notsupported)
        setup_cone()

    def _setup_rectangle_pane_cone(self):  # takes 4x3 ndarray
        # sanity check of rectangle vertices
        # print(self.pane_parameter)
        if not isinstance(self.pane_parameter, dict):
            raise ValueError("error in detector pane parameter")
        needed_info = ["vertices", "t_min", "t_max"]
        if not all(key in self.pane_parameter for key in needed_info):
            raise ValueError("missing info in detector pane parameter")
        self.rvertices = self.pane_parameter["vertices"]
        if self.rvertices.shape != (4, 3):
            raise ValueError("rectangle vertices needs to be 4x3 ndarray")
        if np.abs(np.linalg.det(self.rvertices[1:] - self.rvertices[0])) > zero_eps:  # volume formed by 4 vertices
            raise ValueError(
                "4 vertices not coplanar, %f" % (np.abs(np.linalg.det(self.rvertices[1:] - self.rvertices[0])))
            )

        L2 = np.linalg.norm(self.rvertices, axis=1)

        rvertices_dir_vec = ((self.rvertices.T) / L2).T
        rvertices_dis = L2 + self.L1
        t_max = self.pane_parameter["t_max"]
        t_min = self.pane_parameter["t_min"]

        kmin_norm = rvertices_dis / t_max * vtok
        kmax_norm = rvertices_dis / t_min * vtok
        # print('kmin,kmax',kmin_norm,kmax_norm)

        qvertices_dir_vec = rvertices_dir_vec - [0, 0, 1]
        # print('theta',np.arccos(qvertices_dir_vec)/np.pi*180)
        q_a_min, q_b_min, q_c_min, q_d_min = (qvertices_dir_vec.T * kmin_norm).T
        q_a_max, q_b_max, q_c_max, q_d_max = (qvertices_dir_vec.T * kmax_norm).T

        self.qvertices = [q_a_min, q_b_min, q_c_min, q_d_min, q_a_max, q_b_max, q_c_max, q_d_max]
        # print(self.qvertices)

        center_axis = q_a_min + q_b_min + q_c_min + q_d_min
        center_axis = q_a_min + q_b_min + q_c_min + q_d_min
        center_axis = center_axis / np.linalg.norm(center_axis)

        self.center_axis = center_axis

        a = self.rvertices[0]
        b = self.rvertices[1]
        c = self.rvertices[2]
        d = self.rvertices[3]
        o = np.array([0, 0, 0])

        # q_a_min=a/t_max*vtok
        # q_b_min=b/t_max*vtok
        # q_c_min=c/t_max*vtok
        # q_d_min=d/t_max*vtok

        # q_a_max=a/t_min*vtok
        # q_b_max=b/t_min*vtok
        # q_c_max=c/t_min*vtok
        # q_d_max=d/t_min*vtok

        if np.linalg.norm(np.cross(b - a, c - d)) < zero_eps and np.linalg.norm(np.cross(b - c, a - d)) < zero_eps:
            self.anglesurfaces = {"1": [o, a, b], "2": [o, c, d], "3": [o, c, b], "4": [o, a, d]}

            # opposite faces are: 0-5, 2-3, 1-4
            self.qfaces = {  # each face, [0][1],[2][3] are parallel
                "0": [q_a_min, q_b_min, q_c_min, q_d_min],  # bottom face
                "1": [q_a_min, q_b_min, q_a_max, q_b_max],  # side face
                "4": [q_c_min, q_d_min, q_c_max, q_d_max],  # side face
                "2": [q_c_min, q_b_min, q_c_max, q_b_max],  # side face
                "3": [q_a_min, q_d_min, q_a_max, q_d_max],  # side face
                "5": [q_a_max, q_b_max, q_c_max, q_d_max],
            }  # top face

        elif np.linalg.norm(np.cross(b - a, c - d)) < zero_eps and np.linalg.norm(np.cross(a - c, b - d)) < zero_eps:
            self.anglesurfaces = {"1": [o, a, b], "2": [o, c, d], "3": [o, c, a], "4": [o, b, d]}

            self.qfaces = {  # each face, [0][1],[2][3] are parallel
                "0": [q_a_min, q_b_min, q_c_min, q_d_min],  # bottom face
                "1": [q_a_min, q_b_min, q_a_max, q_b_max],  # side face
                "4": [q_c_min, q_d_min, q_c_max, q_d_max],  # side face
                "2": [q_c_min, q_a_min, q_c_max, q_a_max],  # side face
                "3": [q_b_min, q_d_min, q_b_max, q_d_max],  # side face
                "5": [q_a_max, q_b_max, q_c_max, q_d_max],
            }  # top face

        elif np.linalg.norm(np.cross(d - a, c - b)) < zero_eps and np.linalg.norm(np.cross(a - c, b - d)) < zero_eps:
            self.anglesurfaces = {"1": [o, a, d], "2": [o, c, b], "3": [o, c, a], "4": [o, b, d]}

            self.qfaces = {  # each face, [0][1],[2][3] are parallel
                "0": [q_a_min, q_d_min, q_c_min, q_b_min],  # bottom face
                "1": [q_a_min, q_d_min, q_a_max, q_d_max],  # side face
                "4": [q_c_min, q_b_min, q_c_max, q_b_max],  # side face
                "2": [q_c_min, q_a_min, q_c_max, q_a_max],  # side face
                "3": [q_b_min, q_d_min, q_b_max, q_d_max],  # side face
                "5": [q_a_max, q_d_max, q_c_max, q_b_max],
            }  # top face

        else:
            raise ValueError("4 vertices not rectangular")

    def contain_points_in_pane_cone(self, points):
        contain_points_in_pane_cone_methods = {"rectangle": self._contain_points_in_rectangle_pane_cone}
        contain_points = contain_points_in_pane_cone_methods.get(self.pane_shape, self._shape_notsupported)
        coverage = contain_points(points)
        return coverage

    def _contain_points_in_rectangle_pane_cone(self, points):
        # print(self.qvertices,np.linalg.norm(np.array(self.qvertices),axis=1))
        # print(np.linalg.norm(np.array(self.qvertices),axis=1))
        # print(np.min(np.linalg.norm(np.array(self.qvertices),axis=1)))

        self.qmin = np.min(np.linalg.norm(np.array(self.qvertices), axis=1))
        self.qmax = np.max(np.linalg.norm(np.array(self.qvertices), axis=1))

        ##### cannot only consider angle range and radial range, could be both true, but point outside polyhedron
        # qpoint_len= np.linalg.norm(point)<=self.qmax
        # q_inrange= qpoint_len<=self.qmax and qpoint_len>=self.qmin
        # angle_inrange
        # in_qvolume
        def same_side(a, b, c, p, q):
            pside = np.sign(np.dot(np.cross(b - a, c - a), (p - a).T))
            qside = np.sign(np.dot(np.cross(b - a, c - a), (q - a).T))
            # print(a,b,c,p,q,'abcpq')
            # print(pside,qside,'pq')

            return pside * qside

        # points=points[0:20]
        # points=np.array([[0,0,-1]])
        # print(points)
        # points=points[4:5]

        in_qvolume = np.zeros(points.shape[0])
        # print(in_qvolume)
        for idx_face in self.qfaces:
            idx_opposite_face = "%d" % (5 - eval(idx_face))

            a, b, c = self.qfaces[idx_face][0:3]
            q0 = self.qfaces[idx_opposite_face][0]
            p = points
            q = np.zeros_like(points) + q0
            inside_of_face = same_side(a, b, c, p, q)
            # print(inside_of_face)
            in_qvolume += inside_of_face
        # print( in_qvolume)
        # print( len(self.qfaces))
        # print( len(self.qfaces)-zero_eps)
        return in_qvolume >= len(self.qfaces) - zero_eps * 1e4
        ################################
        # 1e-16 absorbed, 6>6+1e-16 is false
        """
        allpts=set(self.qvertices)
        in_qvolume=np.zeros(points.shape[0])
        for facekey in self.qfaces:
            facepts=set(self.qfaces[facekey])
            otherpts=allpts.difference(facepts)
            a,b,c=self.qfaces[facekey][0:3]
            p=points
            q=np.zeros_like(points)+list(otherpts)[0]
            inside_of_face=same_side(a,b,c,p,q)
            in_qvolume +=inside_of_face
        """

    # TODO
    # from twotheta
    # radial:  res(|q|)=vec{q}*k*dt/(L0+L1)
    # angular: res(|vec(q)|)=length/256/L1 cos( vec{q},vec{k}) |q|

    #
    def resolution(self, point):
        if self.contain_points_in_pane_cone(point)[0]:
            # ad hoc change to acoomodate single point
            radial_resolution = np.linalg.norm(point) * 1e-3
            angle_resolution = np.linalg.norm(point) * 1e-1 / 256
        else:
            radial_resolution = None
            angle_resolution = None
        return {"radial": radial_resolution, "angle": angle_resolution}

    def cloest_face_dist(self, point):
        dist = {}
        for idx_face in self.qfaces:
            a, b, c, d = self.qfaces[idx_face]
            face_dir = np.cross(a - b, a - c)
            face_norm_dir = face_dir / np.linalg.norm(face_dir)
            # print(face_norm_dir,a,point)
            # print(face_norm_dir,a-point)
            # print( np.linalg.norm(face_norm_dir,a-point))
            # print( np.abs(np.linalg.norm(face_norm_dir,a-point)))
            dist[idx_face] = np.abs(np.linalg.norm(np.dot(face_norm_dir, a - point)))
        return np.min(np.array(list(dist.values())))


@dataclass
class DetectorInstrument:
    # coordinate_system: str = 'laboratory'
    detector_parameters_list: List
    detector_panes: List[DetectorPane] = field(default_factory=list)
    # [{'pane_shape':'rectangle','pane_parameter':{'vertices':[4x3],'t_min':100,'t_max':16000 }}]

    def initialize_detector(self) -> None:
        self.detector_panes = []
        self.detector_parameters_list
        # print(self.detector_parameters_list)
        for detector_parameters in self.detector_parameters_list:
            detector_pane_id = detector_parameters["pane_id"]
            detector_pane_shape = detector_parameters["pane_shape"]
            detector_pane_parameter = detector_parameters["pane_parameter"]
            detector_pane = DetectorPane(
                pane_id=detector_pane_id, pane_shape=detector_pane_shape, pane_parameter=detector_pane_parameter
            )
            detector_pane.setup_pane_cone()
            self.detector_panes.append(detector_pane)
            # print(detector_pane_parameter)

    # TODO
    def add_detector(self, detector: DetectorPane) -> None:
        self.detector_panes.append(detector)

    # def get_detector_by_id(self, detector_id: str) -> Optional[DetectorPane]:
    #    """Retrieve a specific detector by its ID."""
    #    return next((det for det in self.detector_panes if det.id == detector_id), None)

    # def calculate_total_active_area(self) -> float:
    #    """Calculate total active detector area."""
    #    return sum(
    #        np.sum(det.active_area) * (det.pixel_size ** 2)
    #        for det in self.detector_panes
    #    )
    def get_max_Q(self) -> float:
        vq = []
        for pane in self.detector_panes:
            vq = vq + pane.qfaces["0"] + pane.qfaces["5"]
        rq = [np.linalg.norm(q) for q in vq]
        return np.max(np.array(rq))

    def get_min_Q(self) -> float:
        vq = []
        for pane in self.detector_panes:
            vq = vq + pane.qfaces["0"] + pane.qfaces["5"]
        rq = [np.linalg.norm(q) for q in vq]
        return np.min(np.array(rq))

    def rotate_detectors(self, euler_angles) -> None:
        # YZY convention
        phi, chi, theta = np.array(euler_angles) / 180 * np.pi
        Rz_phi = np.array([[np.cos(phi), -np.sin(phi), 0], [np.sin(phi), np.cos(phi), 0], [0, 0, 1]])

        Ry_chi = np.array([[np.cos(chi), 0, np.sin(chi)], [0, 1, 0], [-np.sin(chi), 0, np.cos(chi)]])

        Rz_theta = np.array([[np.cos(theta), -np.sin(theta), 0], [np.sin(theta), np.cos(theta), 0], [0, 0, 1]])

        R_rotate = Rz_theta @ Ry_chi @ Rz_phi

        self.detector_panes = []
        for detector_parameters in self.detector_parameters_list:
            detector_pane_id = detector_parameters["pane_id"]
            detector_pane_shape = detector_parameters["pane_shape"]
            vertices_rotated = detector_parameters["pane_parameter"]["vertices"] @ R_rotate.T
            t_max = detector_parameters["pane_parameter"]["t_max"]
            t_min = detector_parameters["pane_parameter"]["t_min"]
            new_detector_parameters = {"vertices": vertices_rotated, "t_max": t_max, "t_min": t_min}
            detector_pane = DetectorPane(
                pane_id=detector_pane_id, pane_shape=detector_pane_shape, pane_parameter=new_detector_parameters
            )
            detector_pane.setup_pane_cone()
            self.detector_panes.append(detector_pane)

    # def compute_detector_transforms(self) -> Dict[str, np.ndarray]:
    #    """
    #    Compute transformation matrices for each detector
    #    relative to the laboratory coordinate system.
    #    """
    #    transforms = {}
    #    for detector in self.detector_panes:
    #        # Basic transformation matrix (placeholder - customize as needed)
    #        transform = np.eye(4)
    #        transform[:3, :3] = detector.orientation
    #        transform[:3, 3] = detector.position
    #        transforms[detector.id] = transform
    #    return transforms


class QGrids:
    def __init__(self, grid_mode: str, grid_parameter: Union[int, float, np.array, Dict[str, Any], None] = None):
        self.grid_mode = grid_mode
        # 'uniform' ,'input'
        self.grid_parameter = grid_parameter

        # for uniform {'Nx':10,'Ny':10,'Nz':10,'Qmax':10,'Qmin':0.1}
        # self.points=None
        # self.rotated_points=None
        # self.status=None

        # for input
        # {'num_sym':10,'qlist':numpy.array}

        self.num_sym = None
        self.points = None
        self.rotated_points = None
        self.status = None

        self.setup_grid()

    def _grid_mode_notsupported(self):
        raise ValueError("{} detector not supported".format(self.grid_mode))

    def setup_grid(self):
        # Mapping of setup methods
        grid_setup_methods = {"uniform": self._setup_uniform_grid, "input": self._setup_input_grid}
        # Select and call appropriate setup method
        setup_grid = grid_setup_methods.get(self.grid_mode, self._grid_mode_notsupported)
        # setup_grid = grid_setup_methods.get('uniform')
        setup_grid()

    def _setup_input_grid(self):
        if not isinstance(self.grid_parameter, dict):
            raise ValueError("error in grid parameter")
        needed_info = ["num_sym", "qlist"]
        if not all(key in self.grid_parameter for key in needed_info):
            raise ValueError("missing info in grid parameter")

        self.points = self.grid_parameter["qlist"]
        self.num_sym = self.grid_parameter["num_sym"]
        # self.points=np.array(self.grid_parameter['qlist'])
        self.rotated_points = self.points.copy()
        self.status = np.zeros_like(self.points[0].shape[0])

    def _setup_uniform_grid(self):
        # sanity check of rectangle vertices
        if not isinstance(self.grid_parameter, dict):
            raise ValueError("error in grid parameter")
        needed_info = ["Nx", "Ny", "Nz", "Qmax", "Qmin"]
        if not all(key in self.grid_parameter for key in needed_info):
            raise ValueError("missing info in grid parameter")
        Nx = self.grid_parameter["Nx"]
        Ny = self.grid_parameter["Ny"]
        Nz = self.grid_parameter["Nz"]
        Qmax = self.grid_parameter["Qmax"]
        Qmin = self.grid_parameter["Qmin"]

        x = np.arange(-Qmax, Qmax, Qmax / Nx)
        y = np.arange(-Qmax, Qmax, Qmax / Ny)
        z = np.arange(-Qmax, Qmax, Qmax / Nz)

        X, Y, Z = np.meshgrid(x, y, z)

        # Calculate radius for each point
        R = np.sqrt(X**2 + Y**2 + Z**2)

        # Get points within radius

        mask = np.logical_and(R <= Qmax, R >= Qmin)
        X_limited = X[mask]
        Y_limited = Y[mask]
        Z_limited = Z[mask]

        self.points = np.column_stack((X_limited, Y_limited, Z_limited))

        self.X, self.Y, self.Z = X, Y, Z
        self.mask = mask

        self.Nx = Nx
        self.Ny = Ny
        self.Nz = Nz
        self.Qmax = Qmax
        self.Qmin = Qmin
        self.rotated_points = self.points.copy()
        self.status = np.zeros_like(self.points.shape[0])

    def rotate_q(self, R):
        self.rotated_points = self.points @ R.T

    # TODO
    # give analysis of coverage

    def get_neighbour(self, point):
        pass

    def get_coverage(self, det_ins: DetectorInstrument):
        self.point_coverage_perpane_list = []
        self.status[...] = False
        for detector in det_ins.detector_panes:
            # TODO optimize these loops
            for isym in range(self.num_sym):
                point_coverage_perpane = detector.contain_points_in_pane_cone(self.rotated_points[isym])
                # self.point_coverage_perpane_list.append(point_coverage_perpane)
                self.status = np.logical_or(self.status, point_coverage_perpane)

        #            #point_coverage_perpane=detector.contain_points_in_pane_cone(self.rotated_points[isym])
        #            #self.point_coverage_perpane_list.append(point_coverage_perpane)
        #
        #
        #            #print(point_coverred_perpane)
        #        self.point_coverage_overall=self.point_coverage_perpane_list[0]
        #        #print(point_cover_overall)
        #        #print(np.sum(point_cover_overall))
        #        #print(det_ins.detector_panes)
        #        for icover in self.point_coverage_perpane_list:
        #            self.point_coverage_overall=np.logical_or(icover,self.point_coverage_overall)
        #            #print(point_cover_overall)

        self.point_coverage_overall = self.status.copy()
        return self.point_coverage_overall
        # return np.sum(self.point_cover_overall)


# TODO
def maximum_coverage(det_ins: DetectorInstrument, angle_list, qgrids: QGrids):
    theta_list, chi_list, phi_list = angle_list
    pass


# TODO
def maximize_coverage(grids: QGrids, det_ins: DetectorInstrument):
    pass


def optimize_angle_with_fixed_given(grids: QGrids, det_ins: DetectorInstrument, fixed_angle_list, euler_angle_ranges):
    angle_list = []
    # angle_list=initial_angle_list+fixed_angle_list
    angle_list = [tuple(a) for a in list(fixed_angle_list)]
    angle_list = list(fixed_angle_list).copy()
    if len(angle_list) == 0:
        angle_list = [(0, 0, 0)]
    angle_list.append([10, 135, 0])
    max_coverage = 0.9

    # unifrom grid: current_coverage=[False]*np.sum(grids.mask)
    current_coverage = [False] * np.size(grids.status)
    current_coverage_num = np.sum(current_coverage)

    last_coverage = current_coverage.copy()
    last_coverage_num = np.sum(last_coverage)

    Nstep = 200
    step = 0

    ########## 1st angle rotation#############
    last_coverage = current_coverage.copy()
    last_coverage_num = np.sum(last_coverage)

    det_ins.rotate_detectors(angle_list[0])
    new_coverage = grids.get_coverage(det_ins)

    current_coverage = np.logical_or(last_coverage, new_coverage)
    current_coverage_num = np.sum(current_coverage)

    new_coverage_num = current_coverage_num - last_coverage_num

    last_coverage = current_coverage.copy()

    # print('initial coverage: ',np.sum(current_coverage)*100/np.size(current_coverage),'%','max covarange:',max_coverage)
    ########## nst angle rotation#############
    current_angle_idx = 0
    last_angle_idx = current_angle_idx

    theta_range, chi_range, phi_range = euler_angle_ranges
    # Discretize the ranges into a grid
    theta_list = np.linspace(
        theta_range[0], theta_range[1], int((theta_range[1] - theta_range[0]) / theta_range[2] + 1)
    )
    chi_list = np.linspace(chi_range[0], chi_range[1], int((chi_range[1] - chi_range[0]) / chi_range[2] + 1))
    phi_list = np.linspace(phi_range[0], phi_range[1], int((phi_range[1] - phi_range[0]) / phi_range[2] + 1))

    # Generate all combinations of Euler angles (grid search)
    # angle_combinations = np.meshgrid(pitch_values, yaw_values, roll_values)

    angle_combinations_iter = product(theta_list, chi_list, phi_list)
    angle_combinations = [i for i in angle_combinations_iter]

    while np.sum(current_coverage) < np.size(current_coverage) * max_coverage and step < Nstep:
        step += 1

        # new_angle=grid_search_adaptive(det_ins, grids, euler_angle_ranges,current_coverage,new_coverage_num)
        # new_angle,current_angle_idx=grid_search_adaptive_fromlast(det_ins, grids, euler_angle_ranges,last_coverage,new_coverage_num,last_angle_idx,angle_combinations)
        # last_angle_idx=current_angle_idx
        # new_angle=grid_search(det_ins, grids, euler_angle_ranges,current_coverage)
        new_angle = grid_ascend(det_ins, grids, euler_angle_ranges, current_coverage, angle_list[-1])
        if new_angle == None:
            logger.debug("Max coverage reached, stopping")
            break

        ########## nst angle rotation#############
        last_coverage = current_coverage.copy()
        last_coverage_num = np.sum(last_coverage)

        det_ins.rotate_detectors(new_angle)
        new_coverage = grids.get_coverage(det_ins)

        current_coverage = np.logical_or(last_coverage, new_coverage)
        current_coverage_num = np.sum(current_coverage)

        new_coverage_num = current_coverage_num - last_coverage_num

        last_coverage = current_coverage.copy()

        logger.debug("%s %s", r"current coverage: f%\%", current_coverage_num * 100.0 / np.size(current_coverage))
        # print('where',np.where(current_coverage==True))
        # print('new_angle',new_angle)
        angle_list.append(new_angle)
        logger.debug("%s %s", "angle", angle_list)
    logger.debug("%s %s", "final covrage", np.sum(current_coverage))
    logger.debug("%s %s", "final angle", angle_list)
    return angle_list, current_coverage


def grid_search(det_ins, qgrids, euler_angle_ranges, last_coverage):
    logger.debug("searching for new angle")
    # Define ranges for each Euler angle
    # euler_angle_range=[[0,180,0.5],[135,135,0.5],[0,360,0.5]]
    # print(euler_angle_ranges)
    theta_range, chi_range, phi_range = euler_angle_ranges
    # Discretize the ranges into a grid
    theta_list = np.linspace(
        theta_range[0], theta_range[1], int((theta_range[1] - theta_range[0]) / theta_range[2] + 1)
    )
    chi_list = np.linspace(chi_range[0], chi_range[1], int((chi_range[1] - chi_range[0]) / chi_range[2] + 1))
    phi_list = np.linspace(phi_range[0], phi_range[1], int((phi_range[1] - phi_range[0]) / phi_range[2] + 1))

    # Generate all combinations of Euler angles (grid search)
    # angle_combinations = np.meshgrid(pitch_values, yaw_values, roll_values)

    angle_combinations = product(theta_list, chi_list, phi_list)
    # angle_combinations = product(theta_list, chi_list, phi_list)

    best_coverage = np.sum(last_coverage)
    best_angles = None

    # Perform grid search
    # print(list(angle_combinations))
    # print(theta_list, chi_list, phi_list)
    # print('angle_combinations: ',angle_combinations)
    # print('angle_combinations: ',len(angle_combinations))
    for angles in angle_combinations:
        # print(angles)
        # Rotate the detector
        det_ins.rotate_detectors(angles)
        current_coverage = np.logical_or(last_coverage, qgrids.get_coverage(det_ins))
        covered_points_size = np.sum(current_coverage)
        # print('covered_points_size',covered_points_size)
        if covered_points_size > best_coverage:
            best_coverage = covered_points_size
            best_angles = angles

    return best_angles


# little improvement
def grid_search_adaptive_fromlast(
    det_ins, qgrids, euler_angle_ranges, last_coverage, last_newcoverage, last_angle_idx, angle_combinations
):
    logger.debug("searching for new angle")
    # Define ranges for each Euler angle
    # euler_angle_range=[[0,180,0.5],[135,135,0.5],[0,360,0.5]]
    # print(euler_angle_ranges)
    #    theta_range, chi_range, phi_range = euler_angle_ranges
    #    # Discretize the ranges into a grid
    #    theta_list = np.linspace(theta_range[0], theta_range[1], int((theta_range[1]-theta_range[0])/theta_range[2]+1))
    #    chi_list = np.linspace(chi_range[0], chi_range[1], int((chi_range[1]-chi_range[0])/chi_range[2]+1))
    #    phi_list = np.linspace(phi_range[0], phi_range[1], int((phi_range[1]-phi_range[0])/phi_range[2]+1))
    #
    #    # Generate all combinations of Euler angles (grid search)
    #    #angle_combinations = np.meshgrid(pitch_values, yaw_values, roll_values)
    #
    #    angle_combinations = product(theta_list, chi_list, phi_list)
    #    angle_combinations=[i for i in angle_combinations]
    # angle_combinations = product(theta_list, chi_list, phi_list)

    best_coverage = np.sum(last_coverage)
    best_angles = None

    # Perform grid search
    # print(list(angle_combinations))
    # print(theta_list, chi_list, phi_list)
    # print('angle_combinations: ',angle_combinations)
    # print('angle_combinations: ',len(angle_combinations))
    for i in range(len(angle_combinations)):
        # print(angles)
        # Rotate the detector
        idx = last_angle_idx + i - int(np.floor(i / len(angle_combinations))) * len(angle_combinations)
        angles = angle_combinations[idx]
        det_ins.rotate_detectors(angles)
        current_coverage = np.logical_or(last_coverage, qgrids.get_coverage(det_ins))
        covered_points_size = np.sum(current_coverage)
        # print('covered_points_size',covered_points_size)
        if covered_points_size > best_coverage:
            best_coverage = covered_points_size
            best_angles = angles
            if covered_points_size - np.sum(last_coverage) >= last_newcoverage:
                break
    return best_angles, idx


## 100% speed improvement
def grid_search_adaptive(det_ins, qgrids, euler_angle_ranges, last_coverage, last_newcoverage):
    logger.debug("searching for new angle")
    # Define ranges for each Euler angle
    # euler_angle_range=[[0,180,0.5],[135,135,0.5],[0,360,0.5]]
    # print(euler_angle_ranges)
    theta_range, chi_range, phi_range = euler_angle_ranges
    # Discretize the ranges into a grid
    theta_list = np.linspace(
        theta_range[0], theta_range[1], int((theta_range[1] - theta_range[0]) / theta_range[2] + 1)
    )
    chi_list = np.linspace(chi_range[0], chi_range[1], int((chi_range[1] - chi_range[0]) / chi_range[2] + 1))
    phi_list = np.linspace(phi_range[0], phi_range[1], int((phi_range[1] - phi_range[0]) / phi_range[2] + 1))

    # Generate all combinations of Euler angles (grid search)
    # angle_combinations = np.meshgrid(pitch_values, yaw_values, roll_values)

    angle_combinations = product(theta_list, chi_list, phi_list)
    # angle_combinations = product(theta_list, chi_list, phi_list)

    best_coverage = np.sum(last_coverage)
    best_angles = None

    # Perform grid search
    # print(list(angle_combinations))
    # print(theta_list, chi_list, phi_list)
    # print('angle_combinations: ',angle_combinations)
    # print('angle_combinations: ',len(angle_combinations))
    for angles in angle_combinations:
        # print(angles)
        # Rotate the detector
        det_ins.rotate_detectors(angles)
        current_coverage = np.logical_or(last_coverage, qgrids.get_coverage(det_ins))
        covered_points_size = np.sum(current_coverage)
        # print('covered_points_size',covered_points_size)
        if covered_points_size > best_coverage:
            best_coverage = covered_points_size
            best_angles = angles
            if covered_points_size - np.sum(last_coverage) >= last_newcoverage:
                break
    return best_angles


def grid_ascend(det_ins, qgrids, euler_angle_ranges, last_coverage, last_angles):
    def renormalize_anlge(x, y, z, euler_angle_ranges):
        theta_min, theta_max, d_theta = euler_angle_ranges[0]
        chi_min, chi_max, d_chi = euler_angle_ranges[1]
        phi_min, phi_max, d_phi = euler_angle_ranges[2]
        theta_range = theta_max - theta_min
        chi_range = chi_max - chi_min
        phi_range = phi_max - phi_min
        if theta_range < zero_eps:
            theta = theta_min
        else:
            theta = int((x - np.floor(x / theta_range) * theta_range) / d_theta) * d_theta + theta_min
            theta = ((x - np.floor(x / theta_range) * theta_range) / d_theta) * d_theta + theta_min
        if chi_range < zero_eps:
            chi = chi_min
        else:
            chi = int((y - np.floor(y / chi_range) * chi_range) / d_chi) * d_chi + chi_min
            chi = ((y - np.floor(y / chi_range) * chi_range) / d_chi) * d_chi + chi_min
        if phi_range < zero_eps:
            phi = phi_min
        else:
            phi = int((z - np.floor(z / phi_range) * phi_range) / d_phi) * d_phi + phi_min
            phi = ((z - np.floor(z / phi_range) * phi_range) / d_phi) * d_phi + phi_min
        return theta, chi, phi

    def function_on_grid(x, y, z):
        theta, chi, phi = renormalize_anlge(x, y, z, euler_angle_ranges)
        angles = [theta, chi, phi]
        det_ins.rotate_detectors(angles)
        current_coverage = np.logical_or(last_coverage, qgrids.get_coverage(det_ins))
        covered_points_size = np.sum(current_coverage)
        # print(angles,covered_points_size,np.sum(last_coverage))
        return covered_points_size

    def calculate_gradient(x, y, z, h=0.5):
        """Calculate gradient using finite differences"""
        dx = (function_on_grid(x + h, y, z) - function_on_grid(x, y, z)) / (2 * h)
        dy = (function_on_grid(x, y + h, z) - function_on_grid(x, y, z)) / (2 * h)
        dz = (function_on_grid(x, y, z + h) - function_on_grid(x, y, z)) / (2 * h)
        return np.array([dx, dy, dz])

    def gradient_ascent(start_x, start_y, start_z, learning_rate=0.01, max_steps=1000, tolerance=1e-6):
        """Perform gradient ascent to find maximum"""
        path = [(start_x, start_y, start_z)]
        x, y, z = start_x, start_y, start_z

        for step in range(max_steps):
            gradient = calculate_gradient(x, y, z)
            # print(step,'step',x,y,z,gradient)

            # Update position
            # new_x = x + learning_rate * gradient[0]
            # new_y = y + learning_rate * gradient[1]
            # new_z = z + learning_rate * gradient[2]
            new_x, new_y, new_z = renormalize_anlge(
                x + learning_rate * gradient[0],
                y + learning_rate * gradient[1],
                z + learning_rate * gradient[2],
                euler_angle_ranges,
            )

            # Check convergence
            if np.sqrt((new_x - x) ** 2 + (new_y - y) ** 2 + (new_z - z) ** 2) < tolerance:
                break

            x, y, z = new_x, new_y, new_z
            path.append((x, y, z))

        # return x, y, function_on_grid(x, y), path
        return x, y, z

    logger.debug("gradient searching for new angle")
    start_x, start_y, start_z = last_angles
    best_angles = gradient_ascent(start_x, start_y, start_z, learning_rate=0.5, max_steps=10, tolerance=1e-6)
    ascend_step = 0
    while np.linalg.norm(np.array(best_angles) - np.array(last_angles)) < 2 and ascend_step < 10:
        new_x, new_y, new_z = last_angles + np.random.randint(40, size=3)
        start_x, start_y, start_z = renormalize_anlge(new_x, new_y, new_z, euler_angle_ranges)
        best_angles = gradient_ascent(start_x, start_y, start_z, learning_rate=0.5, max_steps=10, tolerance=1e-6)
        ascend_step += 1

    return [float(i) for i in best_angles]


def analyze_peaks(peaks, ub, det_ins, symmetry):
    # TODO symmetry
    # det_ins.sym_expand(symmetry)

    def rotation_matrix_from_vectors(vec1, vec2):  # Find the rotation matrix that rotates vec1 to vec2 vec2=R@vec1
        # Normalize input vectors
        a = vec1 / np.linalg.norm(vec1)
        b = vec2 / np.linalg.norm(vec2)

        v = np.cross(a, b)
        c = np.dot(a, b)
        s = np.linalg.norm(v)
        if s == 0:
            return np.eye(3) if c > 0 else -np.eye(3)
        kmat = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        return np.eye(3) + kmat + kmat.dot(kmat) * ((1 - c) / (s**2))

    def rotation_matrix_to_euler_yzy(R):  # Convert rotation matrix to Euler angles in YZY convention.
        # Handle numerical errors
        eps = 1e-8
        R = np.clip(R, -1 + eps, 1 - eps)
        theta1 = np.arctan2(R[1, 2], R[0, 2])
        theta2 = np.arccos(R[2, 2])
        theta3 = np.arctan2(R[2, 1], -R[2, 0])
        # Handle singularity when theta2 = 0 or pi
        if abs(theta2) < eps or abs(theta2 - np.pi) < eps:
            theta1 = 0
            theta3 = np.arctan2(R[1, 0], R[0, 0])
            if abs(theta2) < eps:
                theta2 = 0
            else:
                theta2 = np.pi
        return np.array([theta1, theta2, theta3]) * 180 / np.pi

    for peak_hkl in peaks:
        peak_qlab = ub @ peak_hkl

        edge_dist = {}
        resolution_list = {}
        angle_list = {}
        logger.debug("%s %s", "metric for peak", peak_hkl)
        logger.debug("-------------------------------")

        for detector_pane in det_ins.detector_panes:
            R = rotation_matrix_from_vectors(peak_qlab, detector_pane.center_axis)

            current_pane_id = detector_pane.pane_id
            rotated_peak_qlab = R @ peak_qlab
            edge_dist[current_pane_id] = detector_pane.cloest_face_dist(rotated_peak_qlab)
            resolution_list[current_pane_id] = detector_pane.resolution(rotated_peak_qlab)
            angle_list[current_pane_id] = rotation_matrix_to_euler_yzy(R)
            logger.debug(
                "%s %s %s %s",
                "edge distance, resolution, angle",
                edge_dist[current_pane_id],
                resolution_list[current_pane_id],
                angle_list[current_pane_id],
            )


##################
# GA


'''

import random
import numpy as np

# Genetic Algorithm Functions
def initialize_population(pop_size, euler_ranges, num_angles):
    """
    Initialize a population with random individuals (Euler angle sets).
    """
    population = []
    for _ in range(pop_size):
        individual = [random.uniform(*euler_ranges[0]),  # pitch
                      random.uniform(*euler_ranges[1]),  # yaw
                      random.uniform(*euler_ranges[2])]  # roll
        population.append(individual)
    return population

def calculate_fitness(detector, grid, euler_angles):
    """
    Calculate the fitness of an individual by counting how many points are covered
    by the detector after rotating by the given Euler angles.
    """
    detector.rotate_detector(euler_angles)
    covered_points = sum(1 for point in grid.points if detector.is_covered(point))
    return covered_points

def tournament_selection(population, fitnesses, tournament_size=3):
    """
    Tournament selection to pick the best individuals based on fitness.
    """
    tournament = random.sample(list(zip(population, fitnesses)), tournament_size)
    winner = max(tournament, key=lambda x: x[1])
    return winner[0]

def crossover(parent1, parent2):
    """
    Single-point crossover between two parents to create an offspring.
    """
    crossover_point = random.randint(0, 2)  # We have 3 values for pitch, yaw, and roll
    child = parent1[:crossover_point] + parent2[crossover_point:]
    return child

def mutate(individual, euler_ranges, mutation_rate=0.1):
    """
    Mutate an individual by randomly modifying one of its Euler angles.
    """
    if random.random() < mutation_rate:
        mutation_index = random.randint(0, 2)
        individual[mutation_index] = random.uniform(*euler_ranges[mutation_index])

def genetic_algorithm(detector, grid, euler_ranges, pop_size=50, num_generations=100, mutation_rate=0.1):
    """
    Run the genetic algorithm to find the optimal Euler angles that maximize coverage.
    """
    # Initialize population
    population = initialize_population(pop_size, euler_ranges, 3)

    for generation in range(num_generations):
        # Evaluate fitness for each individual
        fitnesses = [calculate_fitness(detector, grid, individual) for individual in population]

        # Selection and crossover
        new_population = []
        for _ in range(pop_size // 2):  # Create pairs of parents
            parent1 = tournament_selection(population, fitnesses)
            parent2 = tournament_selection(population, fitnesses)

            # Create two children via crossover
            child1 = crossover(parent1, parent2)
            child2 = crossover(parent2, parent1)

            # Mutate the children
            mutate(child1, euler_ranges, mutation_rate)
            mutate(child2, euler_ranges, mutation_rate)

            # Add children to the new population
            new_population.extend([child1, child2])

        # Replace the old population with the new one
        population = new_population

        # Optional: Print the best fitness in each generation
        best_fitness = max(fitnesses)
        print(f"Generation {generation}: Best Coverage = {best_fitness}")

    # Return the best individual
    best_individual = max(zip(population, fitnesses), key=lambda x: x[1])[0]
    return best_individual

# Example usage:
# Assume we have some points in QGrids and a DetectorInstrument instance
points = np.random.rand(100, 3)  # 100 random 3D points as an example
grid = QGrids(points)

detector = DetectorInstrument("detector_model")  # Initialize with your actual detector model

# Define the ranges for pitch, yaw, and roll (e.g., from 0 to 180 degrees for each angle)
euler_ranges = ((0, 180), (0, 180), (0, 180))  # Pitch, Yaw, Roll ranges

# Run the genetic algorithm to find the optimal Euler angles
best_angles = genetic_algorithm(detector, grid, euler_ranges)

print("Optimal Euler Angles for Maximum Coverage:", best_angles)




'''

'''
###### gd
# Objective function to maximize coverage
def objective_function(detector, grid, euler_angles):
    """
    Calculate the total coverage by the detector for a given set of Euler angles.
    This function uses a continuous coverage function (like a softmax or sigmoid).
    """
    detector.rotate_detector(euler_angles)

    total_coverage = 0
    for point in grid.points:
        total_coverage += detector.coverage_degree(point)

    return total_coverage

# Gradient computation (numerical approximation)
def compute_gradient(detector, grid, euler_angles, epsilon=1e-5):
    """
    Numerically computes the gradient of the objective function with respect to Euler angles.
    """
    gradient = np.zeros(3)

    for i in range(3):
        # Create a small perturbation in the i-th angle
        euler_angles_perturbed = euler_angles.copy()
        euler_angles_perturbed[i] += epsilon

        # Compute the objective function for both original and perturbed Euler angles
        original_obj = objective_function(detector, grid, euler_angles)
        perturbed_obj = objective_function(detector, grid, euler_angles_perturbed)

        # Approximate the gradient using the difference in objective function values
        gradient[i] = (perturbed_obj - original_obj) / epsilon

    return gradient

# Gradient descent algorithm
def gradient_descent(detector, grid, euler_ranges, learning_rate=0.01, num_iterations=100, epsilon=1e-5):
    """
    Perform gradient descent to find the optimal Euler angles that maximize coverage.
    """
    # Initialize the Euler angles randomly within their ranges
    euler_angles = np.array([np.random.uniform(*euler_ranges[0]),
                             np.random.uniform(*euler_ranges[1]),
                             np.random.uniform(*euler_ranges[2])])

    # Gradient descent loop
    for iteration in range(num_iterations):
        # Compute the gradient of the objective function with respect to the Euler angles
        gradient = compute_gradient(detector, grid, euler_angles, epsilon)

        # Update the Euler angles in the direction of the gradient (maximize coverage)
        euler_angles += learning_rate * gradient

        # Apply bounds to ensure angles stay within the specified ranges
        euler_angles[0] = np.clip(euler_angles[0], euler_ranges[0][0], euler_ranges[0][1])
        euler_angles[1] = np.clip(euler_angles[1], euler_ranges[1][0], euler_ranges[1][1])
        euler_angles[2] = np.clip(euler_angles[2], euler_ranges[2][0], euler_ranges[2][1])

        # Print progress (optional)
        if iteration % 10 == 0:
            coverage = objective_function(detector, grid, euler_angles)
            print(f"Iteration {iteration}: Coverage = {coverage}, Euler Angles = {euler_angles}")

    return euler_angles

# Example usage:
# Assume we have some points in QGrids and a DetectorInstrument instance
points = np.random.rand(100, 3)  # 100 random 3D points as an example
grid = QGrids(points)

detector = DetectorInstrument("detector_model")  # Initialize with your actual detector model

# Define the ranges for pitch, yaw, and roll (e.g., from 0 to 180 degrees for each angle)
euler_ranges = ((0, 180), (0, 180), (0, 180))  # Pitch, Yaw, Roll ranges

# Perform gradient descent to find the optimal Euler angles
best_angles = gradient_descent(detector, grid, euler_ranges)

print("Optimal Euler Angles for Maximum Coverage:", best_angles)


'''


# class CoverageAnalyzer:
#    def __init__(self, multi_detector_system: MultiDetectorSystem):
#        self.multi_detector_system = multi_detector_system
#        self.coverage_map = {}
#
#    def analyze_q_space_coverage(
#        self,
#        q_points: np.ndarray,
#        coverage_threshold: float = 0.5
#    ) -> Dict[str, float]:
#        """
#        Analyze Q-space coverage across multiple detector_panes.
#
#        Args:
#            q_points: Array of Q-vector points
#            coverage_threshold: Minimum coverage percentage
#
#        Returns:
#            Coverage statistics for each detector
#        """
#        coverage_stats = {}
#
#        for detector in self.multi_detector_system.detector_panes:
#            # Simulate point projection and coverage calculation
#            detected_points = self._project_points_to_detector(q_points, detector)
#            coverage_percentage = self._calculate_coverage_percentage(
#                detected_points,
#                detector.active_area
#            )
#
#            coverage_stats[detector.id] = {
#                'coverage_percentage': coverage_percentage,
#                'meets_threshold': coverage_percentage >= coverage_threshold
#            }
#
#        return coverage_stats
#
#    def _project_points_to_detector(
#        self,
#        q_points: np.ndarray,
#        detector: DetectorPane
#    ) -> np.ndarray:
#        """Project Q-points onto a specific detector."""
#        # Placeholder projection - replace with actual geometric projection logic
#        # This is a simplified mock implementation
#        return q_points
#
#    def _calculate_coverage_percentage(
#        self,
#        detected_points: np.ndarray,
#        active_area: np.ndarray
#    ) -> float:
#        """Calculate detector coverage percentage."""
#        # Mock implementation - replace with actual coverage calculation
#        return np.random.uniform(0, 1)
#
# def create_example_multi_detector_system() -> MultiDetectorSystem:
#    """Create an example multi-detector experimental setup."""
#    system = MultiDetectorSystem()
#
#    # Add detector_panes with diverse configurations
#    system.add_detector(DetectorPane(
#        id='detector_1',
#        position=np.array([0, 0, 0]),
#        orientation=np.eye(3),
#        pixel_size=0.1,
#        pixel_dimensions=(100, 100)
#    ))
#
#    system.add_detector(DetectorPane(
#        id='detector_2',
#        position=np.array([1, 0, 0]),
#        orientation=np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]]),
#        pixel_size=0.05,
#        pixel_dimensions=(200, 200)
#    ))
#
#    return system
#
def main():
    # Create multi-detector system
    det1_vertices = np.array([[-1, -1, 1], [1, 1, 1], [-1, 1, 1], [1, -1, 1]])

    det1_vertices *= 300

    det1_vertices += np.array([00, 00, 300])
    R0 = np.array([[-0.707, -0.707, 0], [0.707, -0.707, 0], [0, 0, 1]])
    det2_vertices = R0 @ det1_vertices.T
    det_ins_parameter = [
        {"pane_shape": "rectangle", "pane_parameter": {"vertices": det1_vertices, "t_min": 100, "t_max": 16000}},
        {"pane_shape": "rectangle", "pane_parameter": {"vertices": det2_vertices, "t_min": 100, "t_max": 16000}},
    ]
    multi_detector_system = DetectorInstrument(det_ins_parameter)
    multi_detector_system.initialize_detector()
    logger.debug("multi_Detector_info")
    logger.debug(multi_detector_system.detector_panes)
    logger.debug(multi_detector_system.detector_parameters_list)
    logger.debug(multi_detector_system.detector_panes[0].qvertices)
    logger.debug(multi_detector_system.detector_panes[0].qfaces)
    euler_angle0 = [0, 0, 0]
    multi_detector_system.rotate_detectors(euler_angles=euler_angle0)

    grid_parameter0 = {"Nx": 10, "Ny": 10, "Nz": 10, "Qmax": 10, "Qmin": 0.1}
    grid_parameter0 = {"Nx": 20, "Ny": 20, "Nz": 4, "Qmax": 1, "Qmin": 0e-3}
    grids1 = QGrids(grid_mode="uniform", grid_parameter=grid_parameter0)
    logger.debug("coverage calculation")
    coverage_results = grids1.get_coverage(multi_detector_system)
    logger.debug("grids info")
    logger.debug(coverage_results)
    logger.debug(grids1.points.shape)
    logger.debug(grids1.points)
    logger.debug(coverage_results.shape)
    logger.debug(grids1.mask.shape)
    # Initialize coverage analyzer

    peak1 = np.array([2, 1, 10])
    ub1 = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]]) * 1e-2

    logger.debug("analyze_peak info")
    analyze_peaks([peak1], ub1, multi_detector_system)

    init_angle_list = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]])

    euler_angle_range1 = [[0, 180, 0.5], [135, 135, 0.5], [0, 360, 0.5]]
    euler_angle_range1 = [[0, 360, 10], [0, 135, 10], [0, 360, 10]]
    euler_angle_range1 = [[0, 360, 1], [135, 135, 135], [0, 360, 1]]
    euler_angle_range1 = [[0, 360, 1], [135, 135, 0], [0, 360, 1]]
    fixed_angle_list = np.array([[0, 135, 0]])
    # Generate sample Q-points
    logger.debug("optimize")

    optimize_angle_with_fixed_given(grids1, multi_detector_system, fixed_angle_list, euler_angle_range1)

    # Analyze coverage
    logger.debug("%s %s", "Detector Coverage Results:", coverage_results)


if __name__ == "__main__":
    main()
