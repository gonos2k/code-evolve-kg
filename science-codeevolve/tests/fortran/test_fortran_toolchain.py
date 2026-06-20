# ===--------------------------------------------------------------------------------------===#
#
# Part of the CodeEvolve Project, under the Apache License v2.0.
# See https://github.com/inter-co/science-codeevolve/blob/main/LICENSE for license information.
# SPDX-License-Identifier: Apache-2.0
#
# ===--------------------------------------------------------------------------------------===#
#
# This file tests the reusable Fortran toolchain helpers.
#
# ===--------------------------------------------------------------------------------------===#

import shutil
from pathlib import Path

import pytest

from codeevolve.toolchains.fortran import (
    BuildMode,
    FortranProfile,
    FortranSource,
    FortranToolchain,
    SourceForm,
)

pytestmark = pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran not found")


def _write_free_candidate(path: Path) -> None:
    path.write_text("""module candidate_kernel
  use iso_fortran_env, only: real64
  implicit none
contains
  subroutine kernel(n, x, y)
    integer, intent(in) :: n
    real(real64), intent(in) :: x(n)
    real(real64), intent(out) :: y(n)
    integer :: i
    do i = 1, n
      y(i) = 2.0_real64 * x(i)
    end do
  end subroutine kernel
end module candidate_kernel
""")


def _write_fixed_candidate(path: Path) -> None:
    path.write_text("""      module candidate_kernel
      use iso_fortran_env, only: real64
      implicit none
      contains
      subroutine kernel(n, x, y)
      integer, intent(in) :: n
      real(real64), intent(in) :: x(n)
      real(real64), intent(out) :: y(n)
      integer :: i
      do 10 i = 1, n
         y(i) = 3.0_real64 * x(i)
   10 continue
      end subroutine kernel
      end module candidate_kernel
""")


def _write_driver(path: Path, multiplier: float) -> None:
    path.write_text(f"""program driver
  use iso_fortran_env, only: real64
  use candidate_kernel, only: kernel
  implicit none
  real(real64) :: x(3), y(3)
  x = [1.0_real64, 2.0_real64, 3.0_real64]
  call kernel(3, x, y)
  if (abs(sum(y) - {multiplier:.1f}_real64 * sum(x)) > 1.0e-12_real64) error stop
  write (*, '(A,ES20.10)') "sum=", sum(y)
end program driver
""")


class TestFortranToolchain:
    """Test suite for FortranToolchain."""

    def test_free_form_compile_and_run(self, tmp_path: Path):
        """Tests free-form candidate compile and execution."""
        candidate = tmp_path / "candidate.f90"
        driver = tmp_path / "driver.f90"
        _write_free_candidate(candidate)
        _write_driver(driver, multiplier=2.0)

        toolchain = FortranToolchain(FortranProfile())
        build = toolchain.build_executable(
            sources=(
                FortranSource(candidate),
                FortranSource(driver),
            ),
            output=tmp_path / "driver.exe",
            build_dir=tmp_path / "build",
            mode=BuildMode.DEBUG,
        )

        assert build.ok, build.stderr
        result = toolchain.run_executable(build.output)
        assert result.ok, result.stderr
        assert "sum=" in result.stdout

    def test_fixed_candidate_with_free_driver(self, tmp_path: Path):
        """Tests compiling a fixed-form candidate with a free-form driver."""
        candidate = tmp_path / "candidate.f"
        driver = tmp_path / "driver.f90"
        _write_fixed_candidate(candidate)
        _write_driver(driver, multiplier=3.0)

        profile = FortranProfile(candidate_form=SourceForm.FIXED, standard="f2018")
        toolchain = FortranToolchain(profile)
        build = toolchain.build_executable(
            sources=(
                toolchain.candidate_source(candidate),
                FortranSource(driver),
            ),
            output=tmp_path / "driver.exe",
            build_dir=tmp_path / "build",
            mode=BuildMode.DEBUG,
        )

        assert build.ok, build.stderr
        result = toolchain.run_executable(build.output)
        assert result.ok, result.stderr

    def test_module_dependencies_compile_before_users(self, tmp_path: Path):
        """Tests source ordering when a later source provides an earlier module dependency."""
        support = tmp_path / "support.f90"
        support.write_text("""module support_math
  use iso_fortran_env, only: real64
  implicit none
contains
  pure real(real64) function scale(value)
    real(real64), intent(in) :: value
    scale = 4.0_real64 * value
  end function scale
end module support_math
""")
        driver = tmp_path / "driver.f90"
        driver.write_text("""program driver
  use iso_fortran_env, only: real64
  use support_math, only: scale
  implicit none
  if (abs(scale(2.0_real64) - 8.0_real64) > 1.0e-12_real64) error stop
end program driver
""")

        toolchain = FortranToolchain(FortranProfile())
        build = toolchain.build_executable(
            sources=(
                FortranSource(driver),
                FortranSource(support),
            ),
            output=tmp_path / "driver.exe",
            build_dir=tmp_path / "build",
            mode=BuildMode.DEBUG,
        )

        assert build.ok, build.stderr
        assert build.commands[0].argv[-1].endswith("00_support.o")
        result = toolchain.run_executable(build.output)
        assert result.ok, result.stderr

    def test_compile_error_returns_failed_build(self, tmp_path: Path):
        """Tests that compiler diagnostics are returned without raising."""
        candidate = tmp_path / "broken.f90"
        candidate.write_text("module broken\n")

        toolchain = FortranToolchain(FortranProfile())
        build = toolchain.build_executable(
            sources=(FortranSource(candidate),),
            output=tmp_path / "broken.exe",
            build_dir=tmp_path / "build",
            mode=BuildMode.DEBUG,
        )

        assert not build.ok
        assert build.stderr

    def test_run_timeout_marks_result(self, tmp_path: Path):
        """Tests timeout handling for executable process groups."""
        source = tmp_path / "sleep.f90"
        source.write_text("""program sleep_driver
  call execute_command_line("sleep 5")
end program sleep_driver
""")
        profile = FortranProfile(run_timeout_s=0.2)
        toolchain = FortranToolchain(profile)
        build = toolchain.build_executable(
            sources=(FortranSource(source),),
            output=tmp_path / "sleep.exe",
            build_dir=tmp_path / "build",
            mode=BuildMode.RELEASE,
        )

        assert build.ok, build.stderr
        result = toolchain.run_executable(build.output)
        assert result.timed_out
        assert not result.ok
