"""Implementation of the higher-order DMD (HODMD).
"""

import torch as pt
from .svd import SVD
from .dmd import DMD


class HODMD(DMD):
    """Higher-order dynamic mode decomposition (HODMD).

    For the theoretical background, refer to Clainche and Vega (link_).
    The HODMD wraps around the standard DMD by adding an initial dimensionality
    reduction step and an enrichment of data matrix with delays. To reconstruct
    snapshots and modes in the original space, a few properties of the base class
    are overwritten.
    .. _link: https://doi.org/10.1137/15M1054924

    Examples

    >>> from flowtorch.analysis import HODMD
    >>> dmd = HODMD(data_matrix, dt)
    set time delay explicitly to 5 time levels
    >>> dmd = HODMD(data_matrix, dt, delay=5)
    set the rank for the initial dimensionality reduction
    >>> dmd = HODMD(data_matrix, dt, delay=5, rank_dr=100)
    use optimal mode coefficients
    >>> dmd = HODMD(data_matrix, dt, delay=5, rank_dr=100, optimal=True)

    """

    def __init__(self, data_matrix: pt.Tensor, dt: float, delay: int = None,
                 rank_dr: int = None, svd_dr: SVD = None, **dmd_options: dict):
        """Create a HODMD instance from data matrix and time step.

        :param data_matrix: data matrix whose columns are formed by
            individual snapshots
        :type data_matrix: pt.Tensor
        :param dt: time step between two snapshots
        :type dt: float
        :param delay: number of time levels (delay coordinates) to use;
            a value of 1 corresponds to using only one time level; if the
            default value is not overwritten, delay is set to one third of
            the data matrix's columns (the number of snapshots) as suggested
            by Clainche and Vega (link_); defaults to None
        :type delay: int, optional
        :param rank_dr: SVD rank of the initial dimensionality reduction step; if
            the default value is not overwritten, the rank is automatically determined as
            described in :class:`flowtorch.analysis.svd.SVD`; defaults to None
        :type rank_dr: int, optional
        :param svd_dr: pre-computed SVD for dimensionality reduction; used to avoid
            re-computing the SVD
        :type svd_dr: SVD, optional

        """
        self._dm_org = data_matrix
        self._rows_org, self._cols_org = data_matrix.shape
        self._delay = delay
        self._svd_dr = svd_dr
        if delay is None:
            self._delay = int(self._cols_org / 3)
        self._validate_inputs()
        if self._svd_dr is None:
            self._svd_dr = SVD(data_matrix, rank_dr)
        super(HODMD, self).__init__(
            self._create_time_delays(self._svd_dr.U.T @ self._dm_org),
            dt, **dmd_options
        )

    def _validate_inputs(self):
        """Validate input values.

        :raises ValueError: if delay is less than 1
        :raises ValueError: if there are not enough snapshots for the given
            value of delay; after the embedding, at least two columns must remain
        """
        if self._delay < 1:
            raise ValueError(
                f"The 'delay' parameter must be a positive integer. Got {self._delay}"
            )
        if self._cols_org - self._delay < 1:
            raise ValueError(
                f"The number of snapshots ({self._cols_org:d}) must be larger than the number of time delays ({self._delay:d})"
            )

    def _create_time_delays(self, data_matrix: pt.Tensor) -> pt.Tensor:
        """Create data matrix enriched with time delays (Hankel matrix).

        :param data_matrix: 2D data matrix with (reduced) snapshots as column
            vectors
        :type data_matrix: pt.Tensor
        :return: data matrix enriched with time delays
        :rtype: pt.Tensor
        """
        rows, cols = data_matrix.shape
        d = self._delay
        return pt.cat(
            [data_matrix[:, i:cols - (d - i - 1)] for i in range(d)]
        )

    @property
    def svd_dr(self) -> SVD:
        return self._svd_dr

    @property
    def delay(self) -> int:
        return self._delay

    @property
    def modes(self) -> pt.Tensor:
        """Get DMD modes in the input space.

        As suggested by Clainche and Vega, only the first set of modes
        corresponding to the first r rows of the reduced DMD modes are
        kept (r is the dimension after the initial dimensionality reduction).

        :return: DMD modes in the input space
        :rtype: pt.Tensor
        """
        r = self.svd_dr.rank
        return self.svd_dr.U.type(self._modes.dtype) @ super().modes[:r]

    @property
    def reconstruction_error(self) -> pt.Tensor:
        """Compute the point-wise reconstruction error.

        Due to the time delay, not all snapshots from the input data
        matrix are reconstructed, so the error is only computed for the
        available reconstructed snapshots

        :return: reconstruction error
        :rtype: pt.Tensor
        """
        reconstruction = self.reconstruction
        return reconstruction - self._dm_org[:, :reconstruction.shape[-1]]

    @property
    def projection_error(self) -> pt.Tensor:
        """Compute the difference between Y and AX.

        :return: projection error
        :rtype: pt.Tensor
        """
        r = self.svd_dr.rank
        return self.svd_dr.U @ super().projection_error[:r]

    @property
    def tlsq_error(self) -> pt.Tensor:
        """Compute the *noise* in X and Y.

        :return: noise in X and Y
        :rtype: Tuple[pt.Tensor, pt.Tensor]
        """
        dx, dy = super().tlsq_error
        r = self.svd_dr.rank
        return self.svd_dr.U @ dx[:r], self.svd_dr.U @ dy[:r]
