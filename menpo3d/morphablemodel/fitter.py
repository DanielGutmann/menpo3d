import numpy as np
import numpy.matlib
import menpo.io as mio
from menpo.image import Image
from menpofit.fitter import MultiScaleParametricFitter
from lk import SimultaneousForwardAdditive
from model import Model


class MorphableModelFitter(object):
    r"""
    Abstract class for defining an 3DMM fitter.

    """
    def __init__(self, mm):
        self._model = mm

    @property
    def mm(self):
        r"""
        The 3DMM model.

        """
        return self._model

    def _precompute(self):
        return homogenize(self._model.shape_pc)

    def _compute_shape(self, alpha_c):
        mm = self._model
        shape = model_to_object(alpha_c, mm.shape_mean, mm.shape_pc, mm.shape_ev)
        shape = homogenize(shape)
        s_m = np.matlib.repmat(np.mean(shape[0:3, :], 1), 1, np.size(shape, 1))
        shape[0:3, :, 0] -= s_m
        return shape

    # TODO
    def fit(self):

        # Define control parameters
        ctrl_params = control_parameters(pt=1, vb=True)

        # Define standard fitting parameters
        std_fit_params = standard_fitting_parameters(ctrl_params)

        # Define fitting parameters
        fit_params = fitting_parameters(20, -1, -1, [0, 1, 4, 5], -1, -1, 10 ** -3)

        alpha_c = std_fit_params['alpha_array']
        beta_c = std_fit_params['beta_array']
        rho_c = std_fit_params['rho_array']
        iota_c = std_fit_params['iota_array']

        [n_alphas, n_betas, n_iotas, n_rhos] = [0]*4
        if fit_params['n_alphas'] != -1:
            n_alphas = len(fit_params['n_alphas'])
        if fit_params['n_betas'] != -1:
            n_betas = len(fit_params['n_betas'])
        if fit_params['n_rhos'] != -1:
            n_rhos = len(fit_params['n_rhos'])
        if fit_params['n_iotas'] != -1:
            n_iotas = len(fit_params['n_iotas'])

        n_params = n_alphas + n_betas + n_iotas + n_rhos

        # Precomputations
        s_pc = self._precompute()

        # Simultaneous Forwards Additive Algorithm
        for i in xrange(fit_params['max_iters']):
            # Alignment on anchor points only

            # Compute shape and texture
            shape = self._compute_shape(alpha_c)
            #return
            # Compute warp and projection matrices

            [rot, view_matrix, projection_matrix] = compute_warp_and_projection_matrices()

            # Compute anchor points projection
            anchor_array = self._model.triangle_array
            warped = warp(shape, view_matrix)
            projection = project(warped, projection_matrix)
            [uv_anchor, yx_anchor] = compute_anchor_points_projection(anchor_array, projection)

            # Compute anchor points error
            anchor_error_pixel = compute_anchor_points_error(yx_anchor)

            # Compute the derivatives
            s_uv_anchor = sample_object_at_uv(shape, anchor_array, uv_anchor)
            w_uv_anchor = sample_object_at_uv(warp, anchor_array, uv_anchor)
            s_pc_uv_anchor = sample_object_at_uv(s_pc, anchor_array, uv_anchor)

            dp_dalpha = []
            dp_dbeta = []
            dp_diota = []
            dp_drho = []

            if n_alphas > 0:
                dp_dalpha = compute_projection_derivatives_shape_parameters(s_uv_anchor, w_uv_anchor, rot,
                                                                            s_pc_uv_anchor, ctrl_params)
            if n_rhos > 0:
                dp_drho = compute_projection_derivatives_warp_parameters(s_uv_anchor, w_uv_anchor, rot,
                                                                         s_pc_uv_anchor, ctrl_params)

            # Compute steepest descent matrix and hessian
            sd_anchor = np.hstack((-dp_dalpha, -dp_drho, dp_dbeta, dp_diota))
            h_anchor = hessian(sd_anchor)
            sd_error_product_anchor = compute_sd_error_product(sd_anchor, anchor_error_pixel)

            # Visualize
            visualize(image, anchors, yx_anchor)

            # Update parameters
            delta_sigma = update_parameters(h_anchor, sd_error_product_anchor)
            [alpha_c, beta_c, rho_c, iota_c] = update(delta_sigma, fit_params)

            # Check for convergence
            if np.linalg.norm(delta_sigma) < fit_params['cvg_thresh']:
                break

        # Save final parameters
        fit_params['n_alphas'] = alpha_c
        fit_params['n_betas'] = beta_c
        fit_params['n_rhos'] = rho_c
        fit_params['n_iotas'] = iota_c


def hessian(sd):
    # Computes the hessian as defined in the Lucas Kanade Algorithm
    n_channels = np.size(sd[:, 0, 1])
    n_params = np.size(sd[0, :, 0])
    h = np.zeros((n_params, n_params))
    sd = np.transpose(sd, [2, 1, 0])
    for i in xrange(n_channels):
        h_i = np.dot(np.transpose(sd[:, :, i]), sd[:, :, i])
        h += h_i
    return h


def standard_fitting_parameters(params):

    if params['projection_type'] == 0:
        # Define projection parameters
        # focal length, phi, theta, varphi, tw_x, tw_y, (tw_z)
        rho_array = np.zeros(6)
        rho_array[0] = 1.2  # focal length
    else:
        rho_array = np.zeros(7)
        rho_array[0] = 30  # focal length
    rho_array[4] = 0.045  # tw_x
    rho_array[5] = 0.306  # tw_y

    # Define illumination and color correction parameters:
    # in order: gamma (red, green, blue), contrast, offset (red, green, blue),
    # ambiant light intensity (red, green, blue),
    # Directional light intensity (red, green, blue), directional light direction (theta, phi), Ks, v
    iota_array = [1, 1, 1, 1, 0, 0, 0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0., 0., 30, 40]

    # Define shape parameters
    alpha_array = np.zeros(101)

    # Define texture parameters
    beta_array = np.zeros(101)

    std_fit_params = {
        'rho_array': rho_array,
        'iota_array': iota_array,
        'alpha_array': alpha_array,
        'beta_array': beta_array
    }
    return std_fit_params


def fitting_parameters(max_iters, n_points, n_alphas, n_rhos, n_betas, n_iotas,
                       cvg_thresh):
    fit_params = {
        'max_iters': max_iters,  # number of iteration: -1 : until convergence
        'n_points': n_points,  # number of points
        # parameters
        'n_alphas': n_alphas,
        'n_rhos': n_rhos,
        'n_betas': n_betas,
        'n_iotas': n_iotas,
        'cvg_thresh': cvg_thresh,
    }
    return fit_params


def control_parameters(pt=0, vb=False, vis=False):
    ctrl_params = {
        'projection_type': pt,  # 0: weak perspective, 1: perspective
        'verbose': vb,  # Console information: False:  off, True: on
        'visualize': vis  # Visualize the fitting
    }
    return ctrl_params


def compute_warp_and_projection_matrices():
    rot = {}
    view_matrix = []
    projection_matrix = []
    return [rot, view_matrix, projection_matrix]


def compute_anchor_points_projection(self, anchor_array, projection):
    [uv_anchor, yx_anchor] = [0] * 2
    return [uv_anchor, yx_anchor]


def compute_anchor_points_error(yx_anchor):
    return 0


# TODO
def sample_object_at_uv(shape, anchor_array, uv_anchor):
    return 0


# TODO
def compute_ortho_proj_derivatives_shape_params():
    return 0


# TODO
def compute_pers_proj_derivatives_shape_params():
    return 0


# TODO
def compute_ortho_warp_derivatives_shape_params():
    return 0


# TODO
def compute_pers_warp_derivatives_shape_params():
    return 0


# TODO
def compute_projection_derivatives_shape_parameters(s_uv_anchor, w_uv_anchor, rot,
                                                    s_pc_uv_anchor, ctrl_params):
    if ctrl_params['projection_type'] == 0:
        dp_dgamma = compute_ortho_proj_derivatives_shape_params()
    else:
        dp_dgamma = compute_pers_proj_derivatives_shape_params()
    return dp_dgamma


# TODO
def compute_projection_derivatives_warp_parameters(s_uv_anchor, w_uv_anchor, rot,
                                                   s_pc_uv_anchor, ctrl_params):
    if ctrl_params['projection_type'] == 0:
        dp_dgamma = compute_ortho_warp_derivatives_shape_params()
    else:
        dp_dgamma = compute_pers_warp_derivatives_shape_params()
    return dp_dgamma


# TODO
def compute_sd_error_product(sd_anchor, error_uv):
    return 0


# TODO
def warp(image, view_matrix):
    r"""
        Warps an image into the template's mask.

        Parameters
        ----------
        image : `menpo.image.Image` or subclass
            The input image to be warped.

        Returns
        -------
        warped_image : `menpo.image.Image` or subclass
            The warped image.
    """
    return 0


# TODO
def project(warp, projection_matrix):
    return 0


# TODO: doc + comments
def model_to_object(coeff, mean, pc, ev):
    # Maybe add these lines directly in the model import_from_basel
    mean = np.ndarray.flatten(mean)
    ev = np.ndarray.flatten(ev)
    # Reconstruction
    nseg = 1
    ndim = np.size(coeff, 0)
    obj = mean * np.ones([1, nseg]) + np.dot(pc[:, 0:ndim], np.multiply(coeff, ev[0:ndim]))
    return np.transpose(np.array(obj))

    # Blending
    # nver = np.size(obj, 0) / 3
    # allver = np.zeros([nseg * nver, 3])
    # k = 0
    # for i in xrange(nseg):
    #     allver[k + 1:k + nver, :] = np.reshape(obj[:, i], (3, nver), order='F')
    #     k += nver
    #
    # obj = np.transpose(np.linalg.inv(mm) * mb * allver)
    #
    # return obj


# TODO: model2object
def compute_texture():
    texture = []
    return texture


# TODO: doc + comments
def homogenize(obj):
    obj = np.array(obj)
    npoints = np.size(obj, 0) / 3
    nobjects = np.size(obj, 1)

    out = np.ones([4, npoints, nobjects])
    out[0:3, :, :] = np.reshape(obj, (3, npoints, nobjects), order='F')

    return out


# TODO
def visualize(image, anchors, yx_anchor):
    print "visualize"


# TODO
def update_parameters(hess, sd_error_product):
    return -np.linalg.inv(hess) * sd_error_product


def update(delta_sigma, fit_params):
    [alpha_c, beta_c, rho_c, iota_c] = [0]*4
    return [alpha_c, beta_c, rho_c, iota_c]


if __name__ == "__main__":
    model = Model()
    mm = model.init_from_basel("model.mat")
    mmf = MorphableModelFitter(mm)
    mmf.fit()

