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
Test reading parameters from TOML file.
"""
from __future__ import annotations

import pytest

from tad_dftd4.damping.parameters import get_params, get_params_default


def test_default() -> None:
    params = get_params_default()
    assert isinstance(params, dict)
    assert "s6" in params


@pytest.mark.parametrize("func", ["pbe", "b3lyp", "revpbe"])
def test_func(func: str) -> None:
    params = get_params(func)
    assert isinstance(params, dict)
    assert "a1" in params
    assert "a2" in params


def test_with_doi() -> None:
    params = get_params("pbe", with_reference=True)
    assert isinstance(params, dict)
    assert "doi" in params