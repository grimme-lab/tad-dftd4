"""
Coordination number: EEQ
========================

Calculation of coordination number for the EEQ model.
"""

import torch

from .. import defaults
from ..data import cov_rad_d3
from ..typing import CountingFunction, Tensor, Any
from ..util import real_pairs
from .count import erf_count

__all__ = ["get_coordination_number_eeq"]


def get_coordination_number_eeq(
    numbers: Tensor,
    positions: Tensor,
    counting_function: CountingFunction = erf_count,
    rcov: Tensor | None = None,
    cutoff: Tensor | None = None,
    cn_max: Tensor | float | None = defaults.D4_CN_EEQ_MAX,
    **kwargs: Any,
) -> Tensor:
    """
    Compute fractional coordination number using an exponential counting function.

    Parameters
    ----------
    numbers : Tensor
        Atomic numbers of molecular structure.
    positions : Tensor
        Atomic positions of molecular structure.
    counting_function : CountingFunction
        Calculate weight for pairs. Defaults to `erf_count`.
    rcov : Tensor | None, optional
        Covalent radii for each species. Defaults to `None`.
    cutoff : Tensor | None, optional
        Real-space cutoff. Defaults to `None`.
    cn_max : Tensor | float | None, optional
        Maximum coordination number. Defaults to `8.0` (float).
    kwargs : dict[str, Any]
        Pass-through arguments for counting function.

    Returns
    -------
    Tensor
        Coordination numbers for all atoms.

    Raises
    ------
    ValueError
        If shape mismatch between `numbers`, `positions` and `rcov` is detected.
    """

    if cutoff is None:
        cutoff = positions.new_tensor(defaults.D4_CN_EEQ_CUTOFF)

    if rcov is None:
        rcov = cov_rad_d3[numbers]
    rcov = rcov.type(positions.dtype).to(positions.device)

    if numbers.shape != rcov.shape:
        raise ValueError(
            f"Shape of covalent radii {rcov.shape} is not consistent with "
            f"({numbers.shape})."
        )
    if numbers.shape != positions.shape[:-1]:
        raise ValueError(
            f"Shape of positions ({positions.shape[:-1]}) is not consistent "
            f"with atomic numbers ({numbers.shape})."
        )

    mask = real_pairs(numbers)
    distances = torch.where(
        mask,
        torch.cdist(
            positions,
            positions,
            p=2,
            compute_mode="use_mm_for_euclid_dist",
        ),
        positions.new_tensor(torch.finfo(positions.dtype).eps),
    )

    rc = rcov.unsqueeze(-2) + rcov.unsqueeze(-1)
    cf = torch.where(
        mask * (distances <= cutoff),
        counting_function(distances, rc, **kwargs),
        positions.new_tensor(0.0),
    )
    cn = torch.sum(cf, dim=-1)

    if cn_max is None:
        return cn

    return cut_coordination_number(cn, cn_max)


def cut_coordination_number(
    cn: Tensor, cn_max: Tensor | float = defaults.D4_CN_EEQ_MAX
):
    if isinstance(cn_max, float):
        cn_max = cn.new_tensor(cn_max)

    return torch.log(1.0 + torch.exp(cn_max)) - torch.log(1.0 + torch.exp(cn_max - cn))