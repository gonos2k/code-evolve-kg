# ===--------------------------------------------------------------------------------------===#
#
# Part of the CodeEvolve Project, under the Apache License v2.0.
# See https://github.com/inter-co/science-codeevolve/blob/main/LICENSE for license information.
# SPDX-License-Identifier: Apache-2.0
#
# ===--------------------------------------------------------------------------------------===#
#
# This file tests KG ablation plan generation.
#
# ===--------------------------------------------------------------------------------------===#

import importlib.util
from pathlib import Path
from typing import Any, Dict

import yaml


def _load_module() -> Any:
    script_path: Path = Path(__file__).parents[1] / "scripts" / "make_kg_ablation_plan.py"
    spec = importlib.util.spec_from_file_location("make_kg_ablation_plan", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_base_config(path: Path) -> None:
    config: Dict[str, Any] = {
        "SEED": 42,
        "SYS_MSG": "Use KG knowledge before editing.",
        "EVOLVE_CONFIG": {"fitness_key": "fitness", "num_epochs": 3, "num_islands": 1},
        "KNOWLEDGE_CONTEXT": {"paths": ["wiki/concepts/example.md"], "require_okf": True},
        "KNOWLEDGE_GATE": {"required": True, "domain": "wrf_single_physics"},
        "GRAPHIFY_EXPORT": {
            "output_dir": "graphify-evolve-corpus",
            "knowledge_links": ["[[decisions/example]]"],
            "knowledge_context_paths": ["wiki/concepts/example.md"],
        },
    }
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)


def _read_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    assert isinstance(data, dict)
    return data


class TestKGAblationPlan:
    def test_generates_same_seed_kg_variants(self, tmp_path):
        module = _load_module()
        base_config_path: Path = tmp_path / "base.yaml"
        _write_base_config(base_config_path)

        manifest: Dict[str, Any] = module.build_ablation_plan(
            base_config_path=base_config_path,
            input_dir=tmp_path / "input",
            output_dir=tmp_path / "plan",
            experiment_out_dir=tmp_path / "runs",
            seeds=[7],
        )

        assert manifest["variants"] == ["kg_on", "context_only", "kg_off"]
        assert len(manifest["runs"]) == 3
        assert manifest["warnings"]
        assert (tmp_path / "plan" / "kg_ablation_plan.json").exists()

        kg_on = _read_yaml(tmp_path / "plan" / "seed-7" / "kg_on.yaml")
        assert kg_on["SEED"] == 7
        assert "KNOWLEDGE_CONTEXT" in kg_on
        assert "KNOWLEDGE_GATE" in kg_on
        assert kg_on["ABLATION_METADATA"]["kg_context_enabled"] is True
        assert kg_on["ABLATION_METADATA"]["kg_gate_enabled"] is True

        context_only = _read_yaml(tmp_path / "plan" / "seed-7" / "context_only.yaml")
        assert "KNOWLEDGE_CONTEXT" in context_only
        assert "KNOWLEDGE_GATE" not in context_only
        assert context_only["ABLATION_METADATA"]["kg_context_enabled"] is True
        assert context_only["ABLATION_METADATA"]["kg_gate_enabled"] is False

        kg_off = _read_yaml(tmp_path / "plan" / "seed-7" / "kg_off.yaml")
        assert "KNOWLEDGE_CONTEXT" not in kg_off
        assert "KNOWLEDGE_GATE" not in kg_off
        assert "knowledge_links" not in kg_off["GRAPHIFY_EXPORT"]
        assert "knowledge_context_paths" not in kg_off["GRAPHIFY_EXPORT"]
        assert kg_off["SYS_MSG"] == "Use KG knowledge before editing."
        assert kg_off["ABLATION_METADATA"]["kg_context_enabled"] is False
        assert kg_off["ABLATION_METADATA"]["graphify_kg_links_enabled"] is False

    def test_can_replace_kg_off_sys_msg(self, tmp_path):
        module = _load_module()
        base_config_path: Path = tmp_path / "base.yaml"
        _write_base_config(base_config_path)

        manifest: Dict[str, Any] = module.build_ablation_plan(
            base_config_path=base_config_path,
            input_dir=tmp_path / "input",
            output_dir=tmp_path / "plan",
            experiment_out_dir=tmp_path / "runs",
            seeds=[7],
            kg_off_sys_msg="Optimize the code using only evaluator feedback.",
        )

        assert manifest["warnings"] == []
        kg_off = _read_yaml(tmp_path / "plan" / "seed-7" / "kg_off.yaml")
        assert kg_off["SYS_MSG"] == "Optimize the code using only evaluator feedback."

    def test_can_omit_context_only_variant(self, tmp_path):
        module = _load_module()
        base_config_path: Path = tmp_path / "base.yaml"
        _write_base_config(base_config_path)

        manifest: Dict[str, Any] = module.build_ablation_plan(
            base_config_path=base_config_path,
            input_dir=tmp_path / "input",
            output_dir=tmp_path / "plan",
            experiment_out_dir=tmp_path / "runs",
            seeds=[1, 2],
            include_context_only=False,
        )

        assert manifest["variants"] == ["kg_on", "kg_off"]
        assert [run["run_id"] for run in manifest["runs"]] == [
            "seed-1/kg_on",
            "seed-1/kg_off",
            "seed-2/kg_on",
            "seed-2/kg_off",
        ]
        assert all(run["command"][0] == "codeevolve" for run in manifest["runs"])
