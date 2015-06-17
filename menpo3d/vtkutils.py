import numpy as np
import vtk
from vtk.util.numpy_support import (numpy_to_vtk, numpy_to_vtkIdTypeArray,
                                    vtk_to_numpy)
from menpo.shape import TriMesh


def trimesh_to_vtk(trimesh):
    r"""Return a `vtkPolyData` representation of a :map:`TriMesh` instance

    Parameters
    ----------
    trimesh : :map:`TriMesh`
        The menpo :map:`TriMesh` object that needs to be converted to a
        `vtkPolyData`

    Returns
    -------
    `vtk_mesh` : `vtkPolyData`
        A VTK mesh representation of the Menpo :map:`TriMesh` data
    """
    mesh = vtk.vtkPolyData()
    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(trimesh.points, deep=1))
    mesh.SetPoints(points)

    cells = vtk.vtkCellArray()
    cells.SetCells(trimesh.n_tris,
                   numpy_to_vtkIdTypeArray(
                       np.hstack((np.ones(trimesh.n_tris)[:, None] * 3,
                                  trimesh.trilist)).astype(np.int64).ravel(),
                       deep=1))
    mesh.SetPolys(cells)
    return mesh


def trimesh_from_vtk(vtk_mesh):
    r"""Return a :map:`TriMesh` representation of a `vtkPolyData` instance

    Parameters
    ----------
    vtk_mesh : `vtkPolyData`
        The VTK mesh representation that needs to be converted to a
        :map:`TriMesh`

    Returns
    -------
    trimesh : :map:`TriMesh`
        A menpo :map:`TriMesh` representation of the VTK mesh data
    """
    points = vtk_to_numpy(vtk_mesh.GetPoints().GetData())
    trilist = vtk_to_numpy(vtk_mesh.GetPolys().GetData())
    return TriMesh(points, trilist=trilist.reshape([-1, 4])[:, 1:])


class VTKClosestPointLocator(object):
    r"""A callable that can be used to find the closest point on a given
    `vtkPolyData` for a query point.

    Parameters
    ----------
    vtk_mesh : `vtkPolyData`
        The VTK mesh that will be queried for finding closest points. A
        data structure will be initialized around this mesh which will enable
        efficient future lookups.
    """
    def __init__(self, vtk_mesh):
        cell_locator = vtk.vtkCellLocator()
        cell_locator.SetDataSet(vtk_mesh)
        cell_locator.BuildLocator()
        self.cell_locator = cell_locator

        # prepare some private properties that will be filled in for us by VTK
        self._c_point = [0., 0., 0.]
        self._cell_id = vtk.mutable(0)
        self._sub_id = vtk.mutable(0)
        self._distance = vtk.mutable(0.0)

    def __call__(self, point):
        r"""Return the nearest point on the mesh and the index of the nearest
        triangle

        Parameters
        ----------
        point : ``(3,)`` `ndarray`
            Query point

        Returns
        -------
        `nearest_point`, `tri_index` : ``(3,)`` `ndarray`, ``int``
            A tuple of the nearest point on the `vtkPolyData` and the triangle
            index of the triangle that the nearest point is located inside of.
        """
        self.cell_locator.FindClosestPoint(point, self._c_point,
                                           self._cell_id,
                                           self._sub_id,
                                           self._distance)
        return self._c_point[:], self._cell_id.get()
