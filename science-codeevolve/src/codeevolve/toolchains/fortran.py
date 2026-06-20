# ===--------------------------------------------------------------------------------------===#
#
# Part of the CodeEvolve Project, under the Apache License v2.0.
# See https://github.com/inter-co/science-codeevolve/blob/main/LICENSE for license information.
# SPDX-License-Identifier: Apache-2.0
#
# ===--------------------------------------------------------------------------------------===#
#
# This file implements reusable GNU Fortran build and run helpers for problem evaluators.
#
# ===--------------------------------------------------------------------------------------===#

import os
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

MODULE_DEF_RE = re.compile(r"^\s*module\s+(?!procedure\b)([A-Za-z_]\w*)", re.IGNORECASE)
USE_RE = re.compile(
    r"^\s*use\b(?:\s*,\s*(?:intrinsic|non_intrinsic)\s*)?(?:::)?\s*([A-Za-z_]\w*)",
    re.IGNORECASE,
)


class SourceForm(StrEnum):
    """Fortran source layout."""

    FREE = "free"
    FIXED = "fixed"


class BuildMode(StrEnum):
    """Compiler flag profile used for a build."""

    DEBUG = "debug"
    RELEASE = "release"


@dataclass(frozen=True)
class FortranSource:
    """One Fortran source file plus source-specific compile settings."""

    path: Path
    form: SourceForm = SourceForm.FREE
    preprocess: bool = False


@dataclass(frozen=True)
class CommandResult:
    """Result of a compiler or executable subprocess."""

    argv: Tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    elapsed_s: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        """Returns whether the subprocess succeeded."""
        return self.returncode == 0 and not self.timed_out


@dataclass(frozen=True)
class BuildResult:
    """Result of compiling and linking a Fortran executable."""

    ok: bool
    output: Path
    commands: Tuple[CommandResult, ...]
    stderr: str = ""

    @property
    def compile_time_s(self) -> float:
        """Returns total time spent in compiler subprocesses."""
        return sum(command.elapsed_s for command in self.commands)


@dataclass(frozen=True)
class FortranProfile:
    """Compiler profile for a Fortran candidate evaluator."""

    compiler: str = "gfortran"
    standard: str = "f2018"
    candidate_form: SourceForm = SourceForm.FREE
    candidate_preprocess: bool = False
    openmp: bool = False
    compile_timeout_s: float = 30.0
    run_timeout_s: float = 10.0
    free_line_length: str = "none"
    fixed_line_length: str = "72"
    debug_flags: Tuple[str, ...] = (
        "-O0",
        "-fcheck=all",
        "-fbacktrace",
        "-ffpe-trap=invalid,zero,overflow",
        "-Wall",
        "-Wextra",
        "-Wimplicit-interface",
    )
    release_flags: Tuple[str, ...] = (
        "-O3",
        "-fno-unsafe-math-optimizations",
    )
    runtime_env: Dict[str, str] = field(
        default_factory=lambda: {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        }
    )
    remove_env: Tuple[str, ...] = ("API_KEY", "API_BASE", "OPENAI_API_KEY")

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "FortranProfile":
        """Creates a profile from a FORTRAN_PROFILE mapping."""
        profile_data: Dict[str, Any] = dict(data)
        if "candidate_form" in profile_data:
            profile_data["candidate_form"] = SourceForm(profile_data["candidate_form"])

        debug_flags = profile_data.get("debug_flags")
        if debug_flags is not None:
            profile_data["debug_flags"] = tuple(str(flag) for flag in debug_flags)

        release_flags = profile_data.get("release_flags")
        if release_flags is not None:
            profile_data["release_flags"] = tuple(str(flag) for flag in release_flags)

        runtime_env = profile_data.get("runtime_env")
        if runtime_env is not None:
            profile_data["runtime_env"] = {
                str(key): str(value) for key, value in runtime_env.items()
            }

        remove_env = profile_data.get("remove_env")
        if remove_env is not None:
            profile_data["remove_env"] = tuple(str(name) for name in remove_env)

        return cls(**profile_data)

    @classmethod
    def from_yaml(cls, path: Path) -> "FortranProfile":
        """Loads a profile from a YAML file containing FORTRAN_PROFILE."""
        with open(path, "r") as f:
            loaded: Dict[str, Any] = yaml.safe_load(f) or {}

        profile_data: Optional[Dict[str, Any]] = loaded.get("FORTRAN_PROFILE")
        if profile_data is None:
            raise KeyError("FORTRAN_PROFILE")
        return cls.from_mapping(profile_data)


class FortranToolchain:
    """Builds and runs Fortran executables for CodeEvolve problem evaluators."""

    def __init__(self, profile: Optional[FortranProfile] = None):
        """Initializes the toolchain with a compiler profile."""
        self.profile: FortranProfile = profile or FortranProfile()
        self.compiler: str = self.profile.compiler

    def compiler_available(self) -> bool:
        """Returns whether the configured compiler is available on PATH."""
        return shutil.which(self.compiler) is not None

    def candidate_source(self, path: Path) -> FortranSource:
        """Creates a FortranSource for the evolved candidate file."""
        return FortranSource(
            path=path,
            form=self.profile.candidate_form,
            preprocess=self.profile.candidate_preprocess,
        )

    def build_executable(
        self,
        *,
        sources: Iterable[FortranSource],
        output: Path,
        build_dir: Path,
        mode: BuildMode,
    ) -> BuildResult:
        """Compiles sources individually, then links one executable."""
        module_dir: Path = build_dir / "mod"
        object_dir: Path = build_dir / "obj"
        module_dir.mkdir(parents=True, exist_ok=True)
        object_dir.mkdir(parents=True, exist_ok=True)
        output.parent.mkdir(parents=True, exist_ok=True)

        commands: List[CommandResult] = []
        objects: List[Path] = []
        mode_flags: Tuple[str, ...] = self._mode_flags(mode)

        for index, source in enumerate(self._ordered_sources(sources)):
            object_path = object_dir / f"{index:02d}_{source.path.stem}.o"
            command: List[str] = [
                self.compiler,
                f"-std={self.profile.standard}",
                *self._source_flags(source),
                *mode_flags,
                *self._openmp_flags(),
                "-J",
                str(module_dir),
                "-I",
                str(module_dir),
                "-c",
                str(source.path),
                "-o",
                str(object_path),
            ]
            result: CommandResult = self._run_command(
                command, timeout_s=self.profile.compile_timeout_s
            )
            commands.append(result)
            if not result.ok:
                return BuildResult(
                    ok=False,
                    output=output,
                    commands=tuple(commands),
                    stderr=self._combined_stderr(commands),
                )
            objects.append(object_path)

        link_command: List[str] = [
            self.compiler,
            *self._openmp_flags(),
            *(str(obj) for obj in objects),
            "-o",
            str(output),
        ]
        link_result: CommandResult = self._run_command(
            link_command, timeout_s=self.profile.compile_timeout_s
        )
        commands.append(link_result)
        return BuildResult(
            ok=link_result.ok,
            output=output,
            commands=tuple(commands),
            stderr=self._combined_stderr(commands),
        )

    def run_executable(self, exe: Path, args: Iterable[str] = ()) -> CommandResult:
        """Runs an executable with the profile runtime environment."""
        return self._run_command(
            [str(exe), *(str(arg) for arg in args)],
            timeout_s=self.profile.run_timeout_s,
            env=self._runtime_env(),
        )

    def _mode_flags(self, mode: BuildMode) -> Tuple[str, ...]:
        if mode is BuildMode.DEBUG:
            return self.profile.debug_flags
        return self.profile.release_flags

    def _source_flags(self, source: FortranSource) -> List[str]:
        if source.form is SourceForm.FREE:
            flags: List[str] = [
                "-ffree-form",
                f"-ffree-line-length-{self.profile.free_line_length}",
            ]
        else:
            flags = [
                "-ffixed-form",
                f"-ffixed-line-length-{self.profile.fixed_line_length}",
            ]

        if source.preprocess:
            flags.append("-cpp")
        return flags

    def _openmp_flags(self) -> Tuple[str, ...]:
        if self.profile.openmp:
            return ("-fopenmp",)
        return ()

    def _ordered_sources(self, sources: Iterable[FortranSource]) -> List[FortranSource]:
        """Orders sources so in-bundle module providers compile before users."""
        source_list: List[FortranSource] = list(sources)
        module_to_source: Dict[str, FortranSource] = {}
        source_deps: Dict[FortranSource, Tuple[str, ...]] = {}

        for source in source_list:
            provided_modules, used_modules = self._scan_source_modules(source.path)
            for module_name in provided_modules:
                module_to_source.setdefault(module_name, source)
            source_deps[source] = tuple(used_modules)

        ordered: List[FortranSource] = []
        visiting: set[FortranSource] = set()
        visited: set[FortranSource] = set()

        def visit(source: FortranSource) -> None:
            if source in visited:
                return
            if source in visiting:
                return
            visiting.add(source)
            for module_name in source_deps.get(source, ()):
                dependency: Optional[FortranSource] = module_to_source.get(module_name)
                if dependency is not None and dependency is not source:
                    visit(dependency)
            visiting.remove(source)
            visited.add(source)
            ordered.append(source)

        for source in source_list:
            visit(source)
        return ordered

    def _scan_source_modules(self, path: Path) -> Tuple[set[str], List[str]]:
        """Returns modules provided and used by one Fortran source file."""
        try:
            lines: List[str] = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return set(), []

        provided_modules: set[str] = set()
        used_modules: List[str] = []
        for line in lines:
            screened_line: str = line.split("!", 1)[0]
            module_match = MODULE_DEF_RE.match(screened_line)
            if module_match:
                provided_modules.add(module_match.group(1).lower())
                continue
            use_match = USE_RE.match(screened_line)
            if use_match:
                used_modules.append(use_match.group(1).lower())
        return provided_modules, used_modules

    def _runtime_env(self) -> Dict[str, str]:
        env: Dict[str, str] = dict(os.environ)
        for key in self.profile.remove_env:
            env.pop(key, None)
        env.update(self.profile.runtime_env)
        return env

    def _run_command(
        self,
        argv: List[str],
        *,
        timeout_s: float,
        env: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        start: float = time.perf_counter()
        try:
            process = subprocess.Popen(
                argv,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
                env=env,
            )
        except FileNotFoundError as err:
            return CommandResult(
                argv=tuple(argv),
                returncode=127,
                stdout="",
                stderr=str(err),
                elapsed_s=time.perf_counter() - start,
            )

        try:
            stdout, stderr = process.communicate(timeout=timeout_s)
            return CommandResult(
                argv=tuple(argv),
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
                elapsed_s=time.perf_counter() - start,
            )
        except subprocess.TimeoutExpired:
            self._kill_process_group(process)
            stdout, stderr = process.communicate()
            return CommandResult(
                argv=tuple(argv),
                returncode=(
                    process.returncode if process.returncode is not None else -signal.SIGKILL
                ),
                stdout=stdout,
                stderr=stderr,
                elapsed_s=time.perf_counter() - start,
                timed_out=True,
            )

    def _kill_process_group(self, process: subprocess.Popen) -> None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except AttributeError:
            process.kill()

    def _combined_stderr(self, commands: Iterable[CommandResult]) -> str:
        return "\n".join(command.stderr for command in commands if command.stderr)
