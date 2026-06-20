# ===--------------------------------------------------------------------------------------===#
#
# Part of the CodeEvolve Project, under the Apache License v2.0.
# See https://github.com/inter-co/science-codeevolve/blob/main/LICENSE for license information.
# SPDX-License-Identifier: Apache-2.0
#
# ===--------------------------------------------------------------------------------------===#
#
# This file tests the Fortran stencil problem evaluator.
#
# ===--------------------------------------------------------------------------------------===#

import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran not found")

REPO_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = REPO_ROOT / "problems" / "fortran_stencil" / "input"
EVALUATOR = INPUT_DIR / "evaluate.py"


def _run_evaluator(candidate_path: Path, results_path: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    return subprocess.run(
        [sys.executable, str(EVALUATOR), str(candidate_path), str(results_path)],
        cwd=INPUT_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )


class TestFortranProblemEvaluator:
    """Test suite for the fortran_stencil evaluator."""

    def test_valid_candidate_returns_positive_fitness(self, tmp_path: Path):
        """Tests that the initial candidate compiles, validates, and benchmarks."""
        results_path = tmp_path / "results.json"
        result = _run_evaluator(INPUT_DIR / "src" / "init_program.f90", results_path)

        assert result.returncode == 0, result.stderr
        metrics = json.loads(results_path.read_text())
        assert metrics["correct"] == 1.0
        assert metrics["failure_code"] == 0.0
        assert metrics["fitness"] > 0.0
        assert metrics["debug_compiled"] == 1.0
        assert metrics["release_compiled"] == 1.0
        assert all(math.isfinite(float(value)) for value in metrics.values())

    def test_compile_error_is_structured_candidate_failure(self, tmp_path: Path):
        """Tests that candidate compiler errors produce fitness=0 JSON."""
        candidate_path = tmp_path / "broken.f90"
        candidate_path.write_text("module candidate_kernel\n")
        results_path = tmp_path / "results.json"

        result = _run_evaluator(candidate_path, results_path)

        assert result.returncode == 0
        assert result.stderr
        metrics = json.loads(results_path.read_text())
        assert metrics["fitness"] == 0.0
        assert metrics["correct"] == 0.0
        assert metrics["failure_code"] == 10.0
        assert all(math.isfinite(float(value)) for value in metrics.values())

    def test_banned_fortran_api_is_structured_candidate_failure(self, tmp_path: Path):
        """Tests that obvious forbidden runtime access is rejected before compile."""
        candidate_path = tmp_path / "banned_api.f90"
        candidate_path.write_text(
            """module candidate_kernel
  use iso_fortran_env, only: real64
  implicit none
  private
  public :: kernel
contains
  subroutine kernel(n, x, y)
    integer, intent(in) :: n
    real(real64), intent(in) :: x(n)
    real(real64), intent(out) :: y(n)
    call execute_command_line("true")
    y = x
  end subroutine kernel
end module candidate_kernel
""",
            encoding="utf-8",
        )
        results_path = tmp_path / "results.json"

        result = _run_evaluator(candidate_path, results_path)

        assert result.returncode == 0
        assert "execute_command_line" in result.stderr
        metrics = json.loads(results_path.read_text())
        assert metrics["fitness"] == 0.0
        assert metrics["failure_code"] == 16.0

    def test_banned_fortran_statement_is_structured_candidate_failure(self, tmp_path: Path):
        """Tests that forbidden Fortran statements are rejected before compile."""
        candidate_path = tmp_path / "banned_statement.f90"
        candidate_path.write_text(
            """module candidate_kernel
  use iso_fortran_env, only: real64
  implicit none
  private
  public :: kernel
contains
  subroutine kernel(n, x, y)
    integer, intent(in) :: n
    real(real64), intent(in) :: x(n)
    real(real64), intent(out) :: y(n)
    print *, n
    y = x
  end subroutine kernel
end module candidate_kernel
""",
            encoding="utf-8",
        )
        results_path = tmp_path / "results.json"

        result = _run_evaluator(candidate_path, results_path)

        assert result.returncode == 0
        assert "print" in result.stderr
        metrics = json.loads(results_path.read_text())
        assert metrics["fitness"] == 0.0
        assert metrics["failure_code"] == 16.0

    def test_benchmark_specific_wrong_output_fails_correctness(self, tmp_path: Path):
        """Tests that benchmark cases also enforce numerical correctness."""
        candidate_path = tmp_path / "benchmark_cheat.f90"
        candidate_path.write_text(
            """module candidate_kernel
  use iso_fortran_env, only: real64
  implicit none
  private
  public :: kernel
contains
  subroutine kernel(n, x, y)
    integer, intent(in) :: n
    real(real64), intent(in) :: x(n)
    real(real64), intent(out) :: y(n)
    integer :: i

    if (n == 1 .or. n == 17 .or. n == 4099) then
      y(1) = x(1)
      do i = 2, n - 1
        y(i) = 0.25_real64 * x(i - 1) + 0.50_real64 * x(i) + 0.25_real64 * x(i + 1)
      end do
      y(n) = x(n)
    else
      y = 0.0_real64
    end if
  end subroutine kernel
end module candidate_kernel
""",
            encoding="utf-8",
        )
        results_path = tmp_path / "results.json"

        result = _run_evaluator(candidate_path, results_path)

        assert result.returncode == 0
        metrics = json.loads(results_path.read_text())
        assert metrics["fitness"] == 0.0
        assert metrics["correct"] == 0.0
        assert metrics["failure_code"] == 12.0
        assert metrics["debug_compiled"] == 1.0
        assert metrics["release_compiled"] == 1.0

    def test_benchmark_input_mutation_fails_correctness(self, tmp_path: Path):
        """Tests that candidates cannot make reference timing use mutated input."""
        candidate_path = tmp_path / "benchmark_input_mutation.f90"
        candidate_path.write_text(
            """module candidate_kernel
  use iso_fortran_env, only: real64
  implicit none
  private
  public :: kernel
contains
  subroutine kernel(n, x, y)
    integer, intent(in) :: n
    real(real64) :: x(n)
    real(real64), intent(out) :: y(n)
    integer :: i

    if (n == 1 .or. n == 17 .or. n == 4099) then
      y(1) = x(1)
      do i = 2, n - 1
        y(i) = 0.25_real64 * x(i - 1) + 0.50_real64 * x(i) + 0.25_real64 * x(i + 1)
      end do
      y(n) = x(n)
    else
      x = 0.0_real64
      y = 0.0_real64
    end if
  end subroutine kernel
end module candidate_kernel
""",
            encoding="utf-8",
        )
        results_path = tmp_path / "results.json"

        result = _run_evaluator(candidate_path, results_path)

        assert result.returncode == 0
        metrics = json.loads(results_path.read_text())
        assert metrics["fitness"] == 0.0
        assert metrics["correct"] == 0.0
        assert metrics["failure_code"] == 12.0
        assert metrics["input_unchanged"] == 0.0

    def test_benchmark_call_count_cache_fails_correctness(self, tmp_path: Path):
        """Tests that benchmark loops require real work on every repetition."""
        candidate_path = tmp_path / "benchmark_call_count_cache.f90"
        candidate_path.write_text(
            """module candidate_kernel
  use iso_fortran_env, only: real64
  implicit none
  private
  public :: kernel
  logical, save :: already_computed = .false.
contains
  subroutine kernel(n, x, y)
    integer, intent(in) :: n
    real(real64), intent(in) :: x(n)
    real(real64), intent(out) :: y(n)
    integer :: i

    if (already_computed) return
    already_computed = .true.
    y(1) = x(1)
    do i = 2, n - 1
      y(i) = 0.25_real64 * x(i - 1) + 0.50_real64 * x(i) + 0.25_real64 * x(i + 1)
    end do
    y(n) = x(n)
  end subroutine kernel
end module candidate_kernel
""",
            encoding="utf-8",
        )
        results_path = tmp_path / "results.json"

        result = _run_evaluator(candidate_path, results_path)

        assert result.returncode == 0
        metrics = json.loads(results_path.read_text())
        assert metrics["fitness"] == 0.0
        assert metrics["correct"] == 0.0
        assert metrics["failure_code"] == 12.0
