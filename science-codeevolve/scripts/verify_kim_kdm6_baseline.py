# ===--------------------------------------------------------------------------------------===#
#
# Part of the CodeEvolve Project, under the Apache License v2.0.
# See https://github.com/inter-co/science-codeevolve/blob/main/LICENSE for license information.
# SPDX-License-Identifier: Apache-2.0
#
# ===--------------------------------------------------------------------------------------===#
#
# This file verifies local evidence for a Fortran-only KIM-meso KDM6 baseline run.
#
# ===--------------------------------------------------------------------------------------===#

import argparse
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, Mapping, Optional

import yaml

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
PLACEHOLDER_RE = re.compile(r"(replace-with|placeholder|todo|/path/to|\.\.\.)", re.IGNORECASE)
MP_PHYSICS_RE = re.compile(r"(?im)^\s*mp_physics\s*=\s*([^!\n/]+)")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        loaded: Any = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"Baseline manifest must be a YAML mapping: {path}")
    return loaded


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def _is_placeholder(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return not text or bool(PLACEHOLDER_RE.search(text))


def _require_mapping(data: Mapping[str, Any], key: str) -> Dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Manifest field {key!r} must be a mapping.")
    return value


def _require_sha256(value: Any, *, label: str) -> str:
    digest = str(value or "").strip().lower()
    if SHA256_RE.fullmatch(digest) is None:
        raise ValueError(f"{label} must be a 64-character SHA-256 digest.")
    return digest


def _normalize_relative_path(value: Any, *, label: str) -> str:
    if _is_placeholder(value):
        raise ValueError(f"{label} is missing or placeholder.")
    raw_path = str(value).strip().replace("\\", "/")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or ".." in path.parts or path.as_posix() in {"", "."}:
        raise ValueError(f"{label} must be a bundle-relative path.")
    return path.as_posix()


def _resolve_bundle_file(
    bundle_root: Path,
    value: Any,
    *,
    label: str,
    required: bool = True,
) -> Optional[Path]:
    if _is_placeholder(value):
        if required:
            raise ValueError(f"{label} is missing or placeholder.")
        return None
    relative_path = _normalize_relative_path(value, label=label)
    resolved = (bundle_root / relative_path).resolve()
    try:
        resolved.relative_to(bundle_root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside bundle root.") from exc
    if not resolved.is_file():
        if required:
            raise FileNotFoundError(f"{label} not found: {relative_path}")
        return None
    return resolved


def _verify_digest(
    path: Path,
    expected_digest: Any,
    *,
    label: str,
) -> str:
    expected = _require_sha256(expected_digest, label=label)
    actual = _sha256_path(path)
    if actual != expected:
        raise ValueError(f"{label} mismatch for {path}: expected {expected}, got {actual}")
    return actual


def _source_root_from_manifest(
    manifest: Mapping[str, Any],
    *,
    source_root_override: Optional[Path],
) -> Path:
    if source_root_override is not None:
        source_root = source_root_override
    else:
        target = _require_mapping(manifest, "target")
        env_name = str(target.get("source_root_env") or "KIM_MESO_SOURCE_ROOT")
        env_value = os.environ.get(env_name)
        if not env_value:
            raise ValueError(f"Set {env_name} or pass --source-root.")
        source_root = Path(env_value)
    resolved = source_root.expanduser().resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(f"KIM-meso source root not found: {resolved}")
    return resolved


def _verify_source_digests(manifest: Mapping[str, Any], source_root: Path) -> Dict[str, str]:
    verified: Dict[str, str] = {}
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Manifest field 'sources' must be a non-empty list.")
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise ValueError(f"sources[{index}] must be a mapping.")
        rel_path = _normalize_relative_path(source.get("path"), label=f"sources[{index}].path")
        path = (source_root / rel_path).resolve()
        try:
            path.relative_to(source_root)
        except ValueError as exc:
            raise ValueError(f"sources[{index}].path must stay inside source root.") from exc
        if not path.is_file():
            raise FileNotFoundError(f"Source file not found: {rel_path}")
        verified[rel_path] = _verify_digest(
            path,
            source.get("sha256"),
            label=f"sources[{index}].sha256",
        )
    return verified


def _extract_mp_physics_values(namelist_text: str) -> Iterable[int]:
    match = MP_PHYSICS_RE.search(namelist_text)
    if match is None:
        raise ValueError("namelist.input does not contain mp_physics.")
    raw_values = match.group(1)
    values = [int(value) for value in re.findall(r"-?\d+", raw_values)]
    if not values:
        raise ValueError("namelist.input mp_physics has no integer values.")
    return values


def _verify_namelist(namelist_path: Path, run_cfg: Mapping[str, Any]) -> Dict[str, Any]:
    text = namelist_path.read_text(encoding="utf-8", errors="replace")
    values = list(_extract_mp_physics_values(text))
    required = _require_mapping(run_cfg, "required_namelist")
    forbidden = _require_mapping(run_cfg, "forbidden_namelist")
    required_mp = int(required.get("mp_physics", 37))
    forbidden_mp = int(forbidden.get("mp_physics", 137))
    if forbidden_mp in values:
        raise ValueError(f"namelist.input contains forbidden mp_physics={forbidden_mp}.")
    if not values or any(value != required_mp for value in values):
        raise ValueError(
            f"namelist.input mp_physics values must all equal {required_mp}; got {values}."
        )
    return {"mp_physics": values}


def _verify_success_log(run_log_path: Path, run_cfg: Mapping[str, Any]) -> None:
    success_pattern = str(run_cfg.get("success_pattern") or "wrf: SUCCESS COMPLETE WRF")
    log_text = run_log_path.read_text(encoding="utf-8", errors="replace")
    if success_pattern not in log_text:
        raise ValueError(f"Run log does not contain success marker: {success_pattern!r}")
    if "mp_physics=137" in log_text or "KDM6AD_PHASE" in log_text:
        raise ValueError("Run log contains KDM6AD/mp_physics=137 markers.")


def verify_kim_kdm6_baseline(
    *,
    manifest_path: Path,
    bundle_root: Path,
    source_root: Optional[Path] = None,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Verifies a Fortran-only KIM-meso KDM6 baseline evidence manifest."""
    manifest = _load_yaml(manifest_path)
    if str(manifest.get("domain")) != "kim_kdm6_microphysics":
        raise ValueError("Manifest domain must be 'kim_kdm6_microphysics'.")

    resolved_source_root = _source_root_from_manifest(manifest, source_root_override=source_root)
    source_digests = _verify_source_digests(manifest, resolved_source_root)

    baseline = _require_mapping(manifest, "full_model_baseline")
    compile_cfg = _require_mapping(baseline, "compile")
    run_cfg = _require_mapping(baseline, "run")
    fixture_cfg = _require_mapping(baseline, "fixture_capture")

    build_log_path = _resolve_bundle_file(
        bundle_root, compile_cfg.get("log_path"), label="compile.log_path"
    )
    assert build_log_path is not None
    run_log_path = _resolve_bundle_file(bundle_root, run_cfg.get("log_path"), label="run.log_path")
    assert run_log_path is not None
    namelist_path = _resolve_bundle_file(
        bundle_root,
        run_cfg.get("namelist_path"),
        label="run.namelist_path",
    )
    assert namelist_path is not None
    output_artifact_path = _resolve_bundle_file(
        bundle_root,
        run_cfg.get("output_path"),
        label="run.output_path",
    )
    assert output_artifact_path is not None
    fixture_path = _resolve_bundle_file(
        bundle_root,
        fixture_cfg.get("artifact_path"),
        label="fixture_capture.artifact_path",
    )
    assert fixture_path is not None

    wrf_exe_path = _resolve_bundle_file(
        bundle_root,
        compile_cfg.get("wrf_exe_path", "main/wrf.exe"),
        label="compile.wrf_exe_path",
    )
    assert wrf_exe_path is not None
    ideal_exe_path = _resolve_bundle_file(
        bundle_root,
        compile_cfg.get("ideal_exe_path"),
        label="compile.ideal_exe_path",
        required=not _is_placeholder(compile_cfg.get("ideal_exe_sha256")),
    )

    artifact_digests: Dict[str, str] = {
        "build_log": _verify_digest(
            build_log_path,
            compile_cfg.get("log_sha256"),
            label="compile.log_sha256",
        ),
        "wrf_exe": _verify_digest(
            wrf_exe_path,
            compile_cfg.get("wrf_exe_sha256"),
            label="compile.wrf_exe_sha256",
        ),
        "namelist": _verify_digest(
            namelist_path,
            run_cfg.get("namelist_sha256"),
            label="run.namelist_sha256",
        ),
        "run_log": _verify_digest(
            run_log_path,
            run_cfg.get("log_sha256"),
            label="run.log_sha256",
        ),
        "output": _verify_digest(
            output_artifact_path,
            run_cfg.get("output_sha256"),
            label="run.output_sha256",
        ),
        "fixture": _verify_digest(
            fixture_path,
            fixture_cfg.get("artifact_sha256"),
            label="fixture_capture.artifact_sha256",
        ),
    }
    if ideal_exe_path is not None:
        artifact_digests["ideal_exe"] = _verify_digest(
            ideal_exe_path,
            compile_cfg.get("ideal_exe_sha256"),
            label="compile.ideal_exe_sha256",
        )

    namelist_summary = _verify_namelist(namelist_path, run_cfg)
    _verify_success_log(run_log_path, run_cfg)

    receipt: Dict[str, Any] = {
        "schema_version": 1,
        "domain": "kim_kdm6_microphysics",
        "baseline_valid": True,
        "source_root_env": str(
            _require_mapping(manifest, "target").get("source_root_env") or "KIM_MESO_SOURCE_ROOT"
        ),
        "source_digests": source_digests,
        "artifact_digests": artifact_digests,
        "namelist": namelist_summary,
        "claim_boundary": (
            "This receipt verifies full-model Fortran KDM6 baseline evidence only. "
            "It does not prove that a candidate improves KDM6."
        ),
    }

    if output_path is not None:
        _write_json(output_path, receipt)
    return receipt


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    receipt = verify_kim_kdm6_baseline(
        manifest_path=args.manifest,
        bundle_root=args.bundle_root,
        source_root=args.source_root,
        output_path=args.output,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
