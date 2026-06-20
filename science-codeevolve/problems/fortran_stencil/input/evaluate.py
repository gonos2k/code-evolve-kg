# ===--------------------------------------------------------------------------------------===#
#
# Part of the CodeEvolve Project, under the Apache License v2.0.
# See https://github.com/inter-co/science-codeevolve/blob/main/LICENSE for license information.
# SPDX-License-Identifier: Apache-2.0
#
# ===--------------------------------------------------------------------------------------===#
#
# This file evaluates Fortran stencil candidates for CodeEvolve.
#
# ===--------------------------------------------------------------------------------------===#

import json
import math
import re
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from codeevolve.toolchains.fortran import BuildMode, FortranProfile, FortranSource, FortranToolchain

PENALTY = 1.0e30
ABS_TOL = 1.0e-10
REL_TOL = 1.0e-10

FAILURE_NONE = 0
FAILURE_DEBUG_COMPILE = 10
FAILURE_DEBUG_RUN = 11
FAILURE_CORRECTNESS = 12
FAILURE_RELEASE_COMPILE = 13
FAILURE_BENCHMARK_RUN = 14
FAILURE_PARSE = 15
FAILURE_STATIC_REJECT = 16

BANNED_FORTRAN_APIS = (
    "execute_command_line",
    "command_argument_count",
    "get_command_argument",
    "get_environment_variable",
    "getarg",
    "getenv",
    "iargc",
    "system",
    "inquire",
    "flush",
    "open",
    "close",
    "read",
    "write",
)

BANNED_FORTRAN_PATTERNS: Tuple[Tuple[str, str], ...] = (
    ("iso_c_binding", r"(?im)^\s*use\b(?:\s*,\s*intrinsic)?\s*(?:::)?\s*iso_c_binding\b"),
    ("bind(c)", r"(?i)\bbind\s*\(\s*c\s*\)"),
    ("include", r"(?im)^\s*(?:#\s*)?include\b"),
    ("print", r"(?im)^\s*print\b"),
    ("read", r"(?im)^\s*read\b"),
    ("write", r"(?im)^\s*write\b"),
)


def _parse_key_values(stdout: str) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        metrics[key.strip()] = float(raw_value.strip())
    return metrics


def _finite_metrics(metrics: Dict[str, float]) -> Dict[str, float]:
    finite: Dict[str, float] = {}
    for key, value in metrics.items():
        number = float(value)
        if not math.isfinite(number):
            number = PENALTY
        finite[key] = number
    return finite


def _write_metrics(results_path: str, metrics: Dict[str, float]) -> None:
    with open(results_path, "w") as f:
        json.dump(_finite_metrics(metrics), f, indent=4, allow_nan=False)


def _strip_fortran_comments(source: str) -> str:
    """Removes free-form Fortran comments for static API screening."""
    return "\n".join(line.split("!", 1)[0] for line in source.splitlines())


def _find_banned_api_uses(source: str) -> List[str]:
    """Returns banned Fortran APIs referenced by the candidate source."""
    screened_source = _strip_fortran_comments(source)
    banned_uses: set[str] = set()
    for api_name in BANNED_FORTRAN_APIS:
        if re.search(rf"\b{re.escape(api_name)}\s*\(", screened_source, re.IGNORECASE):
            banned_uses.add(api_name)
    for label, pattern in BANNED_FORTRAN_PATTERNS:
        if re.search(pattern, screened_source):
            banned_uses.add(label)
    return sorted(banned_uses)


def _failure_metrics(
    *,
    failure_code: int,
    eval_time: float,
    compile_time_s: float = 0.0,
    max_abs_error: float = PENALTY,
    max_rel_error: float = PENALTY,
    debug_compiled: int = 0,
    release_compiled: int = 0,
    input_unchanged: int = 0,
) -> Dict[str, float]:
    return {
        "fitness": 0.0,
        "correct": 0.0,
        "failure_code": float(failure_code),
        "debug_compiled": float(debug_compiled),
        "release_compiled": float(release_compiled),
        "input_unchanged": float(input_unchanged),
        "max_abs_error": max_abs_error,
        "max_rel_error": max_rel_error,
        "candidate_time_s": 0.0,
        "reference_time_s": 0.0,
        "compile_time_s": compile_time_s,
        "eval_time": eval_time,
    }


def _sources(
    root: Path, toolchain: FortranToolchain, candidate_path: Path
) -> Tuple[FortranSource, ...]:
    return (
        toolchain.candidate_source(candidate_path),
        FortranSource(root / "reference_kernel.f90"),
        FortranSource(root / "driver.f90"),
    )


def _run_required(
    toolchain: FortranToolchain,
    exe: Path,
    args: Iterable[str],
    required_keys: Iterable[str],
) -> Tuple[bool, Dict[str, float], str]:
    result = toolchain.run_executable(exe, args)
    if not result.ok:
        return False, {}, result.stderr

    try:
        metrics = _parse_key_values(result.stdout)
    except ValueError as err:
        return False, {}, str(err)

    missing = [key for key in required_keys if key not in metrics]
    if missing:
        return False, metrics, f"missing metrics: {missing}"
    return True, metrics, result.stderr


def evaluate(program_path: str, results_path: str) -> None:
    """Evaluates one candidate program and writes numeric CodeEvolve metrics."""
    started_at = time.perf_counter()
    root = Path.cwd()

    try:
        profile = FortranProfile.from_yaml(root / "fortran_profile.yaml")
    except Exception as err:
        print(f"Invalid Fortran profile: {err}", file=sys.stderr)
        sys.exit(2)

    toolchain = FortranToolchain(profile)
    if not toolchain.compiler_available():
        print(f"Fortran compiler not found: {profile.compiler}", file=sys.stderr)
        sys.exit(2)

    candidate_path = Path(program_path)
    try:
        banned_uses = _find_banned_api_uses(candidate_path.read_text(encoding="utf-8"))
    except OSError as err:
        print(f"Unable to read candidate source: {err}", file=sys.stderr)
        _write_metrics(
            results_path,
            _failure_metrics(
                failure_code=FAILURE_STATIC_REJECT,
                eval_time=time.perf_counter() - started_at,
            ),
        )
        return
    if banned_uses:
        print(
            "Candidate uses banned Fortran APIs: " + ", ".join(sorted(banned_uses)),
            file=sys.stderr,
        )
        _write_metrics(
            results_path,
            _failure_metrics(
                failure_code=FAILURE_STATIC_REJECT,
                eval_time=time.perf_counter() - started_at,
            ),
        )
        return

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        sources = _sources(root, toolchain, candidate_path)

        debug_build = toolchain.build_executable(
            sources=sources,
            output=work / "verify.exe",
            build_dir=work / "debug",
            mode=BuildMode.DEBUG,
        )
        if not debug_build.ok:
            print(debug_build.stderr, file=sys.stderr)
            _write_metrics(
                results_path,
                _failure_metrics(
                    failure_code=FAILURE_DEBUG_COMPILE,
                    eval_time=time.perf_counter() - started_at,
                    compile_time_s=debug_build.compile_time_s,
                ),
            )
            return

        max_abs_error = 0.0
        max_rel_error = 0.0
        for n, seed in ((1, 17), (17, 101), (4099, 104729)):
            ok, metrics, stderr = _run_required(
                toolchain,
                debug_build.output,
                ("verify", str(n), "1", str(seed)),
                ("correct", "finite", "input_unchanged", "max_abs_error", "max_rel_error"),
            )
            if not ok:
                print(stderr, file=sys.stderr)
                _write_metrics(
                    results_path,
                    _failure_metrics(
                        failure_code=FAILURE_DEBUG_RUN,
                        eval_time=time.perf_counter() - started_at,
                        compile_time_s=debug_build.compile_time_s,
                        debug_compiled=1,
                    ),
                )
                return

            max_abs_error = max(max_abs_error, metrics["max_abs_error"])
            max_rel_error = max(max_rel_error, metrics["max_rel_error"])
            if (
                metrics["correct"] != 1.0
                or metrics["finite"] != 1.0
                or metrics["input_unchanged"] != 1.0
                or metrics["max_abs_error"] > ABS_TOL
                or metrics["max_rel_error"] > REL_TOL
            ):
                _write_metrics(
                    results_path,
                    _failure_metrics(
                        failure_code=FAILURE_CORRECTNESS,
                        eval_time=time.perf_counter() - started_at,
                        compile_time_s=debug_build.compile_time_s,
                        max_abs_error=max_abs_error,
                        max_rel_error=max_rel_error,
                        debug_compiled=1,
                    ),
                )
                return

        release_build = toolchain.build_executable(
            sources=sources,
            output=work / "benchmark.exe",
            build_dir=work / "release",
            mode=BuildMode.RELEASE,
        )
        compile_time_s = debug_build.compile_time_s + release_build.compile_time_s
        if not release_build.ok:
            print(release_build.stderr, file=sys.stderr)
            _write_metrics(
                results_path,
                _failure_metrics(
                    failure_code=FAILURE_RELEASE_COMPILE,
                    eval_time=time.perf_counter() - started_at,
                    compile_time_s=compile_time_s,
                    max_abs_error=max_abs_error,
                    max_rel_error=max_rel_error,
                    debug_compiled=1,
                ),
            )
            return

        candidate_times: List[float] = []
        reference_times: List[float] = []
        for n, repetitions, seed in (
            (2048, 4, 11),
            (32768, 20, 101),
            (32768, 20, 202),
            (32768, 20, 303),
        ):
            ok, metrics, stderr = _run_required(
                toolchain,
                release_build.output,
                ("bench", str(n), str(repetitions), str(seed)),
                (
                    "candidate_time_s",
                    "reference_time_s",
                    "correct",
                    "finite",
                    "input_unchanged",
                    "max_abs_error",
                    "max_rel_error",
                ),
            )
            if not ok:
                print(stderr, file=sys.stderr)
                _write_metrics(
                    results_path,
                    _failure_metrics(
                        failure_code=FAILURE_BENCHMARK_RUN,
                        eval_time=time.perf_counter() - started_at,
                        compile_time_s=compile_time_s,
                        max_abs_error=max_abs_error,
                        max_rel_error=max_rel_error,
                        debug_compiled=1,
                        release_compiled=1,
                    ),
                )
                return
            max_abs_error = max(max_abs_error, metrics["max_abs_error"])
            max_rel_error = max(max_rel_error, metrics["max_rel_error"])
            if (
                metrics["correct"] != 1.0
                or metrics["finite"] != 1.0
                or metrics["input_unchanged"] != 1.0
                or metrics["max_abs_error"] > ABS_TOL
                or metrics["max_rel_error"] > REL_TOL
            ):
                _write_metrics(
                    results_path,
                    _failure_metrics(
                        failure_code=FAILURE_CORRECTNESS,
                        eval_time=time.perf_counter() - started_at,
                        compile_time_s=compile_time_s,
                        max_abs_error=max_abs_error,
                        max_rel_error=max_rel_error,
                        debug_compiled=1,
                        release_compiled=1,
                    ),
                )
                return
            candidate_times.append(metrics["candidate_time_s"])
            reference_times.append(metrics["reference_time_s"])

    if not candidate_times or not reference_times:
        _write_metrics(
            results_path,
            _failure_metrics(
                failure_code=FAILURE_PARSE,
                eval_time=time.perf_counter() - started_at,
                compile_time_s=compile_time_s,
                max_abs_error=max_abs_error,
                max_rel_error=max_rel_error,
                debug_compiled=1,
                release_compiled=1,
            ),
        )
        return

    candidate_time_s = statistics.median(candidate_times)
    reference_time_s = statistics.median(reference_times)
    fitness = reference_time_s / max(candidate_time_s, 1.0e-30)
    _write_metrics(
        results_path,
        {
            "fitness": fitness,
            "correct": 1.0,
            "failure_code": float(FAILURE_NONE),
            "debug_compiled": 1.0,
            "release_compiled": 1.0,
            "input_unchanged": 1.0,
            "max_abs_error": max_abs_error,
            "max_rel_error": max_rel_error,
            "candidate_time_s": candidate_time_s,
            "reference_time_s": reference_time_s,
            "compile_time_s": compile_time_s,
            "eval_time": time.perf_counter() - started_at,
        },
    )


if __name__ == "__main__":
    evaluate(sys.argv[1], sys.argv[2])
