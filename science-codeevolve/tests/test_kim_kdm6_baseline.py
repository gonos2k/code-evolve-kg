# ===--------------------------------------------------------------------------------------===#
#
# Part of the CodeEvolve Project, under the Apache License v2.0.
# See https://github.com/inter-co/science-codeevolve/blob/main/LICENSE for license information.
# SPDX-License-Identifier: Apache-2.0
#
# ===--------------------------------------------------------------------------------------===#
#
# This file tests KIM-meso KDM6 baseline evidence verification.
#
# ===--------------------------------------------------------------------------------------===#

import hashlib
import importlib.util
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml


def _load_module() -> Any:
    script_path: Path = Path(__file__).parents[1] / "scripts" / "verify_kim_kdm6_baseline.py"
    spec = importlib.util.spec_from_file_location("verify_kim_kdm6_baseline", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _make_baseline_tree(tmp_path: Path) -> Dict[str, Any]:
    source_root = tmp_path / "KIM-meso_v1.0"
    bundle_root = tmp_path / "baseline"

    source_digests = {
        "phys/module_mp_kdm6.F": _write(source_root / "phys/module_mp_kdm6.F", "module kdm6\n"),
        "phys/module_microphysics_driver.F": _write(
            source_root / "phys/module_microphysics_driver.F",
            "CASE (KDM6SCHEME)\n",
        ),
        "Registry/Registry.EM_COMMON": _write(
            source_root / "Registry/Registry.EM_COMMON",
            "package kdm6scheme mp_physics==37\n",
        ),
        "phys/module_mp_radar.F": _write(source_root / "phys/module_mp_radar.F", "radar\n"),
        "share/module_model_constants.F": _write(
            source_root / "share/module_model_constants.F",
            "constants\n",
        ),
    }

    build_log = _write(bundle_root / "logs/build.log", "build completed\n")
    wrf_exe = _write(bundle_root / "main/wrf.exe", "fake exe\n")
    ideal_exe = _write(bundle_root / "main/ideal.exe", "fake ideal\n")
    namelist = _write(bundle_root / "run/namelist.input", "&physics\n mp_physics = 37, 37,\n/\n")
    run_log = _write(bundle_root / "run/rsl.out.0000", "d01 wrf: SUCCESS COMPLETE WRF\n")
    output = _write(bundle_root / "run/wrfout.37.nc", "netcdf output\n")
    fixture = _write(bundle_root / "fixtures/kdm6_train_case01.bin", "fixture\n")

    sources = [
        {"kind": "raw_kim_fortran_code", "path": path, "sha256": digest}
        for path, digest in source_digests.items()
    ]
    manifest = {
        "schema_version": 1,
        "domain": "kim_kdm6_microphysics",
        "target": {"source_root_env": "KIM_MESO_SOURCE_ROOT"},
        "full_model_baseline": {
            "compile": {
                "log_path": "logs/build.log",
                "log_sha256": build_log,
                "wrf_exe_path": "main/wrf.exe",
                "wrf_exe_sha256": wrf_exe,
                "ideal_exe_path": "main/ideal.exe",
                "ideal_exe_sha256": ideal_exe,
            },
            "run": {
                "namelist_path": "run/namelist.input",
                "namelist_sha256": namelist,
                "required_namelist": {"mp_physics": 37},
                "forbidden_namelist": {"mp_physics": 137},
                "log_path": "run/rsl.out.0000",
                "log_sha256": run_log,
                "success_pattern": "wrf: SUCCESS COMPLETE WRF",
                "output_path": "run/wrfout.37.nc",
                "output_sha256": output,
            },
            "fixture_capture": {
                "artifact_path": "fixtures/kdm6_train_case01.bin",
                "artifact_sha256": fixture,
            },
        },
        "sources": sources,
    }
    manifest_path = bundle_root / "kim_kdm6_evidence.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    return {
        "source_root": source_root,
        "bundle_root": bundle_root,
        "manifest_path": manifest_path,
        "manifest": manifest,
    }


class TestKimKdm6Baseline:
    def test_valid_baseline_manifest_writes_receipt(self, tmp_path):
        module = _load_module()
        data = _make_baseline_tree(tmp_path)
        output_path = tmp_path / "receipt.json"

        receipt = module.verify_kim_kdm6_baseline(
            manifest_path=data["manifest_path"],
            bundle_root=data["bundle_root"],
            source_root=data["source_root"],
            output_path=output_path,
        )

        assert receipt["baseline_valid"] is True
        assert receipt["namelist"]["mp_physics"] == [37, 37]
        assert "phys/module_mp_kdm6.F" in receipt["source_digests"]
        assert output_path.exists()

    def test_rejects_mp137_namelist(self, tmp_path):
        module = _load_module()
        data = _make_baseline_tree(tmp_path)
        manifest = data["manifest"]
        namelist_path = data["bundle_root"] / "run/namelist.input"
        digest = _write(namelist_path, "&physics\n mp_physics = 137,\n/\n")
        manifest["full_model_baseline"]["run"]["namelist_sha256"] = digest
        data["manifest_path"].write_text(
            yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
        )

        with pytest.raises(ValueError, match="forbidden mp_physics=137"):
            module.verify_kim_kdm6_baseline(
                manifest_path=data["manifest_path"],
                bundle_root=data["bundle_root"],
                source_root=data["source_root"],
            )

    def test_rejects_kdm6ad_run_log_marker(self, tmp_path):
        module = _load_module()
        data = _make_baseline_tree(tmp_path)
        manifest = data["manifest"]
        run_log_path = data["bundle_root"] / "run/rsl.out.0000"
        digest = _write(run_log_path, "wrf: SUCCESS COMPLETE WRF\nKDM6AD_PHASE\n")
        manifest["full_model_baseline"]["run"]["log_sha256"] = digest
        data["manifest_path"].write_text(
            yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
        )

        with pytest.raises(ValueError, match="KDM6AD"):
            module.verify_kim_kdm6_baseline(
                manifest_path=data["manifest_path"],
                bundle_root=data["bundle_root"],
                source_root=data["source_root"],
            )

    def test_rejects_spaced_mp137_run_log_marker(self, tmp_path):
        module = _load_module()
        data = _make_baseline_tree(tmp_path)
        manifest = data["manifest"]
        run_log_path = data["bundle_root"] / "run/rsl.out.0000"
        digest = _write(
            run_log_path,
            "wrf: SUCCESS COMPLETE WRF\n================ mp_physics = 137 ================\n",
        )
        manifest["full_model_baseline"]["run"]["log_sha256"] = digest
        data["manifest_path"].write_text(
            yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
        )

        with pytest.raises(ValueError, match="forbidden run marker"):
            module.verify_kim_kdm6_baseline(
                manifest_path=data["manifest_path"],
                bundle_root=data["bundle_root"],
                source_root=data["source_root"],
            )

    def test_rejects_short_mp137_run_log_marker(self, tmp_path):
        module = _load_module()
        data = _make_baseline_tree(tmp_path)
        manifest = data["manifest"]
        run_log_path = data["bundle_root"] / "run/rsl.out.0000"
        digest = _write(run_log_path, "wrf: SUCCESS COMPLETE WRF\n[wrf] mp=137 ...\n")
        manifest["full_model_baseline"]["run"]["log_sha256"] = digest
        data["manifest_path"].write_text(
            yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
        )

        with pytest.raises(ValueError, match="forbidden run marker"):
            module.verify_kim_kdm6_baseline(
                manifest_path=data["manifest_path"],
                bundle_root=data["bundle_root"],
                source_root=data["source_root"],
            )

    def test_rejects_diagnostic_log_marker(self, tmp_path):
        module = _load_module()
        data = _make_baseline_tree(tmp_path)
        manifest = data["manifest"]
        diagnostic_digest = _write(
            data["bundle_root"] / "run/rsl.error.0000",
            "KDM6AD_PHASE phy_init top mp_physics=          37\n",
        )
        manifest["full_model_baseline"]["run"]["diagnostic_log_paths"] = [
            {"path": "run/rsl.error.0000", "sha256": diagnostic_digest}
        ]
        data["manifest_path"].write_text(
            yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
        )

        with pytest.raises(ValueError, match="Diagnostic log"):
            module.verify_kim_kdm6_baseline(
                manifest_path=data["manifest_path"],
                bundle_root=data["bundle_root"],
                source_root=data["source_root"],
            )

    def test_rejects_source_digest_mismatch(self, tmp_path):
        module = _load_module()
        data = _make_baseline_tree(tmp_path)
        (data["source_root"] / "phys/module_mp_kdm6.F").write_text("changed\n", encoding="utf-8")

        with pytest.raises(ValueError, match="mismatch"):
            module.verify_kim_kdm6_baseline(
                manifest_path=data["manifest_path"],
                bundle_root=data["bundle_root"],
                source_root=data["source_root"],
            )
