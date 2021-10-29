"""Class and tools to read Visualization Toolkit (VTK_) data.

.. _VTK: https://vtk.org/
"""

# standard library packages
from glob import glob
from typing import Callable, Union, List, Dict
# third party packages
import torch as pt
from vtk import vtkUnstructuredGridReader, vtkXMLUnstructuredGridReader
from vtk.numpy_interface.dataset_adapter import WrapDataObject, UnstructuredGrid
# flowtorch packages
from flowtorch import DEFAULT_DTYPE
from .dataloader import Dataloader
from .utils import check_and_standardize_path, check_list_or_str


class VTKDataloader(Dataloader):
    """Load unstructured VTK files and time series.

    The loader assumes that snapshots are stored in individual VTK files.
    Currently, only unstructured mesh data are supported.

    Examples

    >>> from flowtorch import DATASETS
    >>> from flowtorch.data import VTKDataloader
    >>> path = DATASETS["vtk_cylinder_re200_flexi"]
    >>> loader = VTKDataloader.from_flexi(path, "Cylinder_Re200_Solution_")
    >>> loader.write_times
    ["0000000", "0000005", "0000300"]
    >>> loader.field_names
    {'0000000': ['Density', 'MomentumX', 'MomentumY', 'MomentumZ']}
    >>> density = loader.load_snapshot("Density", loader.write_times)
    >>> density.shape
    torch.Size([729000, 3])

    >>> from flowtorch import DATASETS
    >>> from flowtorch.data import VTKDataloader
    >>> path = DATASETS["vtk_su2_airfoil_2D"]
    >>> loader = VTKDataloader.from_su2(path, "flow_")
    >>> p, U = loader.load_snapshot(["Pressure", "Velocity"], loader.write_times[0])
    >>> U.shape
    torch.Size([214403, 3])

    """

    def __init__(self, path: str, vtk_reader: Union[vtkUnstructuredGridReader, vtkXMLUnstructuredGridReader],
                 prefix: str = "", suffix: str = "", dtype: str = DEFAULT_DTYPE):
        """Create a VTKDataloader instance from a folder of VTK files.

        The loader assumes that the write time is encoded in the file name.

        :param path: path to folder containing VTK files
        :type path: str
        :param vtk_reader: unstructured VTK reader for XML or legacy VTK format
        :type vtk_reader: Union[vtkUnstructuredGridReader, vtkXMLUnstructuredGridReader]
        :param prefix: part of file name before time value, defaults to ""
        :type prefix: str, optional
        :param suffix: part of file name after time value, defaults to ""
        :type suffix: str, optional
        :param dtype: tensor type, defaults to DEFAULT_DTYPE
        :type dtype: str, optional
        """
        self._path = path
        self._vtk_reader = vtk_reader
        self._prefix = prefix
        self._suffix = suffix
        self._dtype = dtype
        self._write_times = None
        self._field_names = None

    @classmethod
    def from_flexi(cls, path: str, prefix: str = "", suffix: str = ".000000000.vtu", dtype: str = DEFAULT_DTYPE):
        """Create loader instance from VTK files generated by Flexi_.

        Flexi supports the output of field and surface data as unstructured
        XML-based VTK files.

        .. _Flexi: https://www.flexi-project.org/

        :param path: path to folder containing VTK files
        :type path: str
        :param prefix: part of file name before time value, defaults to ""
        :type prefix: str, optional
        :param suffix: part of file name after time value, defaults to ".000000000.vtu"
        :type suffix: str, optional
        :param dtype: tensor type, defaults to DEFAULT_DTYPE
        :type dtype: str, optional
        """
        return cls(path, vtkXMLUnstructuredGridReader, prefix, suffix, dtype)

    @classmethod
    def from_su2(cls, path: str, prefix: str = "", suffix: str = ".vtk", dtype: str = DEFAULT_DTYPE):
        """Create loader instance from VTK files generated by SU2_.

        .. _SU2: https://su2code.github.io/

        :param path: path to folder containing VTK files
        :type path: str
        :param prefix: part of file name before time value, defaults to ""
        :type prefix: str, optional
        :param suffix: part of file name after time value, defaults to ".vtk"
        :type suffix: str, optional
        :param dtype: tensor type, defaults to DEFAULT_DTYPE
        :type dtype: str, optional
        """
        return cls(path, vtkUnstructuredGridReader, prefix, suffix, dtype)

    def _create_vtk_reader(self, file_path: str) -> UnstructuredGrid:
        """Create a VTK reader object for unstructured grids.

        :param file_path: location of the VTK file
        :type file_path: str
        :return: VTK reader for unstructured grids
        :rtype: UnstructuredGrid
        """
        reader = self._vtk_reader()
        reader.SetFileName(file_path)
        if hasattr(reader, "ReadAllVectorsOn"):
            reader.ReadAllVectorsOn()
        if hasattr(reader, "ReadAllScalarsOn"):
            reader.ReadAllScalarsOn()
        reader.Update()
        return WrapDataObject(reader.GetOutput())

    def _build_file_path(self, time: str) -> str:
        """Create file path VTK file.

        :param time: snapshot write time
        :type time: str
        :return: VTK file location
        :rtype: str
        """
        return f"{self._path}/{self._prefix}{time}{self._suffix}"

    def load_snapshot(self,
                      field_name: Union[List[str], str],
                      time: Union[List[str], str]) -> Union[List[pt.Tensor], pt.Tensor]:
        check_list_or_str(field_name, "field_name")
        check_list_or_str(time, "time")
        # load multiple fields
        if isinstance(field_name, list):
            if isinstance(time, list):
                snapshots = [
                    self._create_vtk_reader(self._build_file_path(t)).PointData for t in time
                ]
                return [
                    pt.stack(
                        [pt.tensor(snapshot[name], dtype=self._dtype)
                         for snapshot in snapshots], dim=-1
                    ) for name in field_name
                ]
            else:
                snapshot = self._create_vtk_reader(
                    self._build_file_path(time)).PointData
                return [
                    pt.tensor(snapshot[name], dtype=self._dtype) for name in field_name
                ]
        # load single field
        else:
            if isinstance(time, list):
                return pt.stack(
                    [
                        pt.tensor(
                            self._create_vtk_reader(
                                self._build_file_path(t)).PointData[field_name],
                            dtype=self._dtype
                        ) for t in time
                    ],
                    dim=-1
                )
            else:
                return pt.tensor(
                    self._create_vtk_reader(self._build_file_path(time)).PointData[
                        field_name], dtype=self._dtype
                )

    @ property
    def write_times(self) -> List[str]:
        if self._write_times is None:
            files = glob(self._build_file_path("*"))
            self._write_times = sorted(
                [f.split("/")[-1][len(self._prefix):-len(self._suffix)]
                 for f in files], key=float
            )
        return self._write_times

    @ property
    def field_names(self) -> Dict[str, List[str]]:
        if self._field_names is None:
            snapshot = self._create_vtk_reader(
                self._build_file_path(self.write_times[0])
            )
            self._field_names = dict(
                {self.write_times[0]: snapshot.PointData.keys()}
            )
        return self._field_names

    @ property
    def vertices(self) -> pt.Tensor:
        snapshot = self._create_vtk_reader(
            self._build_file_path(self.write_times[0])
        )
        return pt.tensor(snapshot.Points, dtype=self._dtype)

    @ property
    def weights(self) -> pt.Tensor:
        raise NotImplementedError(
            "The weights property is not yet implemented.")
