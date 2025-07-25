# This file is part of tad-dftd4.
#
# SPDX-Identifier: Apache-2.0
# Copyright (C) 2024 Grimme Group
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Dispersion Methods: Base
========================

Base classes and interfaces for dispersion terms.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

import torch
from tad_mctc.typing import DD, Any, CNFunction, Tensor, TensorLike

from ..cutoff import Cutoff
from ..damping import Damping, Param
from ..model import ModelInst, ModelKey


class DispTerm(TensorLike, ABC):
    """
    Base class for all dispersion terms.

    Parameters
    ----------
    damping_fn : Damping
        Damping function to be used for the dispersion term.
    charge_dependent : bool
        Whether the term is charge-dependent, i.e., requires atomic charges
        for the calculation.
    device : torch.device, optional
        Device on which the term is calculated.
    dtype : torch.dtype, optional
        Data type of the term's tensors.
    """

    damping_fn: Damping
    """Damping function to be used for the dispersion term."""

    charge_dependent: bool
    """
    Whether the term is charge-dependent, i.e., requires atomic charges for
    the calculation.
    """

    __slots__ = ("damping_fn", "charge_dependent")

    def __init__(
        self,
        damping_fn: Damping,
        charge_dependent: bool,
        *,
        device: torch.device | None = None,
        dtype: torch.dtype | None = None,
    ):
        super().__init__(device=device, dtype=dtype)

        self.damping_fn = damping_fn
        self.charge_dependent = charge_dependent

    def __eq__(self, other: Any):
        if self.__class__ is not other.__class__:
            return False

        return (
            self.damping_fn == other.damping_fn
            and self.charge_dependent == other.charge_dependent
        )

    @abstractmethod
    def calculate(
        self,
        numbers: Tensor,
        positions: Tensor,
        param: Param,
        cn: Tensor,
        model: ModelInst,
        q: Tensor | None,
        r4r2: Tensor,
        rvdw: Tensor,
        cutoff: Cutoff,
    ) -> Tensor:
        """Evaluate the energy for the dispersion term."""


class Disp(TensorLike):
    """Base class for DFT-D dispersion calculations."""

    terms: list[DispTerm]
    """List of dispersion terms for which the calculation is performed."""

    cn_fn: CNFunction
    """Coordination number."""

    cn_fn_kwargs: dict[str, Any]
    """Keyword arguments for the coordination number function."""

    _model_key: ModelKey
    """Key for the DFT-D model, e.g., 'd4'."""

    _model_kwargs: dict[str, Any]
    """Keyword arguments for the DFT-D model."""

    _model_instance: ModelInst | None
    """Instance of the DFT-D model, if provided."""

    __slots__ = (
        "terms",
        "cn_fn",
        "cn_fn_kwargs",
        "_model_key",
        "_model_instance",
        "_model_kwargs",
    )

    _ALLOWED_MODELS = ("d3", "d4", "d4s", "d5")
    """Allowed DFT-D models for the calculation."""

    TERMS: ClassVar[list[tuple[type[DispTerm], dict[str, Any] | None]]] = []
    """List of dispersion terms to be registered in the constructor."""

    def __init__(
        self,
        model: ModelKey | ModelInst = "d4",
        model_kwargs: dict[str, Any] | None = None,
        cn_fn: CNFunction | None = None,
        cn_fn_kwargs: dict[str, Any] | None = None,
        *,
        device: torch.device | None = None,
        dtype: torch.dtype | None = None,
    ):
        super().__init__(device=device, dtype=dtype)

        if isinstance(model, str):
            key = model.casefold()

            if key not in self._ALLOWED_MODELS:
                raise ValueError(
                    f"Unknown model '{key}'. "
                    f"Please use {', '.join(self._ALLOWED_MODELS)}."
                )

            self._model_key = key
            self._model_instance = None
            self._model_kwargs = model_kwargs or {}

        else:
            # sentinel, never queried
            self._model_key = "instance"  # type: ignore[assignment]

            self._model_instance = model
            self._model_kwargs = {}
            if model_kwargs:
                from warnings import warn

                warn(
                    "`model` is an instance - `model_kwargs` were ignored.",
                    RuntimeWarning,
                    stacklevel=2,
                )

        if cn_fn is None:
            name = (
                self._model_instance.__class__.__name__
                if self._model_instance is not None
                else self._model_key
            )
            if "3" in name:
                # pylint: disable=import-outside-toplevel
                from tad_mctc.ncoord import cn_d3

                cn_fn = cn_d3
            elif "4" in name:
                # pylint: disable=import-outside-toplevel
                from tad_mctc.ncoord import cn_d4

                cn_fn = cn_d4
            elif "5" in name:
                # pylint: disable=import-outside-toplevel
                from tad_mctc.ncoord import cn_d3

                cn_fn = cn_d3
            else:  # pragma: no cover
                raise ValueError(
                    f"Unknown model '{self._model_key}'. "
                    "Please use 'd3', 'd4', 'd4s', or 'd5'."
                )

        self.cn_fn = cn_fn
        self.cn_fn_kwargs = cn_fn_kwargs if cn_fn_kwargs is not None else {}

        self.terms: list[DispTerm] = []
        for term_cls, kw in self.TERMS:
            kw = {} if kw is None else kw.copy()
            self.register(term_cls(**kw))

    def register(self, term: DispTerm) -> None:
        self.terms.append(term)

    def deregister(self, term: DispTerm) -> None:
        self.terms.remove(term)

    def get_model(self, numbers: Tensor) -> ModelInst:
        """
        Get the DFT-D4 model for the given atomic numbers.

        Parameters
        ----------
        numbers : Tensor
            Atomic numbers of the atoms in the system.

        Returns
        -------
        ModelInst
            The DFT-D4 model initialized with the atomic numbers.
        """
        if self._model_instance is not None:
            return self._model_instance

        if self._model_key.casefold() == "d3":
            # pylint: disable=import-outside-toplevel
            from tad_dftd4.model.d3 import D3Model

            return D3Model(numbers=numbers, **self._model_kwargs, **self.dd)

        if self._model_key.casefold() == "d4":
            # pylint: disable=import-outside-toplevel
            from tad_dftd4.model.d4 import D4Model

            return D4Model(numbers=numbers, **self._model_kwargs, **self.dd)

        if self._model_key.casefold() == "d4s":
            # pylint: disable=import-outside-toplevel
            from tad_dftd4.model.d4s import D4SModel

            return D4SModel(numbers=numbers, **self._model_kwargs, **self.dd)

        raise ValueError(
            f"Unknown model '{self._model_key}'. "
            "Please use 'd3', 'd4', 'd4s', or 'd5'."
        )

    # Radii

    def get_rcov(self, numbers: Tensor) -> Tensor:
        # pylint: disable=import-outside-toplevel
        from tad_mctc.data import COV_D3

        return COV_D3(**self.dd)[numbers]

    def get_r4r2(self, numbers: Tensor) -> Tensor:
        # pylint: disable=import-outside-toplevel
        from tad_dftd4.data import R4R2

        return R4R2(**self.dd)[numbers]

    def get_rvdw(self, numbers: Tensor) -> Tensor:
        # pylint: disable=import-outside-toplevel
        from tad_mctc.data import VDW_PAIRWISE

        return VDW_PAIRWISE(**self.dd)[
            numbers.unsqueeze(-1), numbers.unsqueeze(-2)
        ]

    # Calculation

    def calculate(
        self,
        numbers: Tensor,
        positions: Tensor,
        charge: Tensor,
        param: Param,
        *,
        cutoff: Cutoff | None = None,
        q: Tensor | None = None,
        rcov: Tensor | None = None,
        r4r2: Tensor | None = None,
        rvdw: Tensor | None = None,
    ):
        """
        Evaluate DFT-D4 dispersion energy for a (batch of) molecule(s).

        Parameters
        ----------
        numbers : Tensor
            Atomic numbers for all atoms in the system of shape ``(..., nat)``.
        positions : Tensor
            Cartesian coordinates of all atoms (shape: ``(..., nat, 3)``).
        charge : Tensor
            Total charge of the system.
        param : Param
            DFT-D4 damping parameters.
        model : D4Model | D4SModel | None, optional
            The DFT-D4 dispersion model for the evaluation of the C6
            coefficients. Defaults to ``None``, which creates
            :class:`tad_dftd4.model.d4.D4Model`.
        rcov : Tensor | None, optional
            Covalent radii of the atoms in the system. Defaults to
            ``None``, i.e., default values are used.
        r4r2 : Tensor | None, optional
            r⁴ over r² expectation values of the atoms in the system. Defaults
            to ``None``, i.e., default values are used.
        q : Tensor | None, optional
            Atomic partial charges. Defaults to ``None``, i.e., EEQ charges are
            calculated using the total ``charge``.
        cutoff : Cutoff | None, optional
            Collection of real-space cutoffs. Defaults to ``None``, i.e.,
            :class:`tad_dftd4.cutoff.Cutoff` is initialized with its defaults.
        counting_function : CountingFunction, optional
            Counting function used for the DFT-D4 coordination number. Defaults
            to the error function counting function
            :func:`tad_mctc.ncoord.count.erf_count`.
        damping_function : DampingFunction, optional
            Damping function to evaluate distance dependent contributions.
            Defaults to the Becke-Johnson rational damping function
            :func:`tad_dftd4.damping.rational.rational_damping`.

        Returns
        -------
        Tensor
            Atom-resolved DFT-D4 dispersion energy.

        Raises
        ------
        ValueError
            Shape inconsistencies between ``numbers``, ``positions``, ``r4r2``,
            or, ``rcov``.
        RuntimeError
            If atomic charges are explicitly provided, but no term requires
            them.
        """
        dd: DD = {"device": positions.device, "dtype": positions.dtype}

        if numbers.shape != positions.shape[:-1]:
            raise ValueError(
                f"Shape of positions ({positions.shape}) is not consistent "
                f"with atomic numbers ({numbers.shape}).",
            )

        if cutoff is None:
            cutoff = Cutoff(**dd)

        model = self.get_model(numbers=numbers)

        # 2) radii defaults
        if r4r2 is None:
            r4r2 = self.get_r4r2(numbers)
        if numbers.shape != r4r2.shape:
            raise ValueError(
                f"Shape of expectation values r4r2 ({r4r2.shape}) is not "
                f"consistent with atomic numbers ({numbers.shape}).",
            )

        if rcov is None:
            rcov = self.get_rcov(numbers)
        if numbers.shape != rcov.shape:
            raise ValueError(
                f"Shape of covalent radii ({rcov.shape}) is not consistent "
                f"with atomic numbers ({numbers.shape}).",
            )

        if rvdw is None:
            rvdw = self.get_rvdw(numbers)
        if numbers.shape != rvdw.shape[:-1]:
            raise ValueError(
                f"Shape of van der Waals radii ({rvdw.shape}) is not "
                f"consistent with atomic numbers ({numbers.shape}).",
            )

        # 3) Coordination numbers
        cn = self.cn_fn(
            numbers, positions, rcov=rcov, cutoff=cutoff.cn, **self.cn_fn_kwargs
        )

        # 4) charges if any term demands them
        is_c_dep = any(t.charge_dependent for t in self.terms)
        if q is not None and is_c_dep is False:
            raise RuntimeError(
                "Atomic charges are explicitly provided, but no term "
                "requires them. Please remove the `q` argument or "
                "provide a term that requires atomic charges.",
            )

        if q is None and is_c_dep is True:
            # pylint: disable=import-outside-toplevel
            from tad_multicharge import get_eeq_charges

            q = get_eeq_charges(
                numbers, positions, charge, cutoff=cutoff.cn_eeq
            )

        if q is not None:
            if numbers.shape != q.shape:
                raise ValueError(
                    f"Shape of atomic charges ({q.shape}) is not consistent "
                    f"with atomic numbers ({numbers.shape}).",
                )

        # 5) delegate
        energy = torch.zeros_like(numbers, **dd)
        for term in self.terms:
            energy = energy + term.calculate(
                numbers=numbers,
                positions=positions,
                param=param,
                cn=cn,
                model=model,
                q=q,
                r4r2=r4r2,
                rvdw=rvdw,
                cutoff=cutoff,
            )

        return energy
