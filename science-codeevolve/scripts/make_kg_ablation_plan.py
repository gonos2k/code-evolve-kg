# ===--------------------------------------------------------------------------------------===#
#
# Part of the CodeEvolve Project, under the Apache License v2.0.
# See https://github.com/inter-co/science-codeevolve/blob/main/LICENSE for license information.
# SPDX-License-Identifier: Apache-2.0
#
# ===--------------------------------------------------------------------------------------===#
#
# This file generates same-seed configuration variants for measuring KG grounding
# as a CodeEvolve component.
#
# ===--------------------------------------------------------------------------------------===#

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import yaml

METRICS_TO_COMPARE: List[str] = [
    "best_fitness",
    "median_fitness",
    "accepted_candidate_rate",
    "compile_error_rate",
    "policy_rejection_rate",
    "best_fitness_per_model_call",
    "declared_usage_score",
    "verified_usage_score",
]

MODEL_VISIBLE_KG_TERMS: List[str] = [
    "kg",
    "knowledge",
    "okf",
    "graphify",
]


def _load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        loaded: Any = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"Config must be a YAML mapping: {path}")
    return loaded


def _write_yaml(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=False)


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=False)
        handle.write("\n")


def _strip_graphify_kg_fields(config: Dict[str, Any]) -> None:
    graphify_cfg: Any = config.get("GRAPHIFY_EXPORT")
    if not isinstance(graphify_cfg, dict):
        return
    graphify_cfg.pop("knowledge_links", None)
    graphify_cfg.pop("knowledge_context_paths", None)


def _add_ablation_metadata(
    config: Dict[str, Any],
    *,
    seed: int,
    variant: str,
    kg_context_enabled: bool,
    kg_gate_enabled: bool,
    graphify_kg_links_enabled: bool,
) -> None:
    config["SEED"] = seed
    config["ABLATION_METADATA"] = {
        "schema_version": 1,
        "experiment": "kg_grounding_component",
        "variant": variant,
        "seed": seed,
        "kg_context_enabled": kg_context_enabled,
        "kg_gate_enabled": kg_gate_enabled,
        "graphify_kg_links_enabled": graphify_kg_links_enabled,
        "metrics_to_compare": list(METRICS_TO_COMPARE),
        "claim_boundary": (
            "This variant supports KG component ablation only. It does not by itself "
            "prove semantic knowledge use or WRF physics improvement."
        ),
    }


def _model_visible_kg_terms(config: Mapping[str, Any]) -> List[str]:
    sys_msg: Any = config.get("SYS_MSG", "")
    if not isinstance(sys_msg, str):
        return []
    lower_sys_msg: str = sys_msg.lower()
    return [term for term in MODEL_VISIBLE_KG_TERMS if term in lower_sys_msg]


def _make_variant(
    base_config: Mapping[str, Any],
    *,
    seed: int,
    variant: str,
    kg_off_sys_msg: Optional[str] = None,
) -> Dict[str, Any]:
    config: Dict[str, Any] = deepcopy(dict(base_config))

    if variant == "kg_on":
        graphify_cfg: Any = config.get("GRAPHIFY_EXPORT")
        graphify_kg_links_enabled: bool = isinstance(graphify_cfg, dict) and bool(
            graphify_cfg.get("knowledge_links") or graphify_cfg.get("knowledge_context_paths")
        )
        _add_ablation_metadata(
            config,
            seed=seed,
            variant=variant,
            kg_context_enabled="KNOWLEDGE_CONTEXT" in config,
            kg_gate_enabled="KNOWLEDGE_GATE" in config,
            graphify_kg_links_enabled=graphify_kg_links_enabled,
        )
        return config

    if variant == "context_only":
        config.pop("KNOWLEDGE_GATE", None)
        graphify_cfg = config.get("GRAPHIFY_EXPORT")
        graphify_kg_links_enabled = isinstance(graphify_cfg, dict) and bool(
            graphify_cfg.get("knowledge_links") or graphify_cfg.get("knowledge_context_paths")
        )
        _add_ablation_metadata(
            config,
            seed=seed,
            variant=variant,
            kg_context_enabled="KNOWLEDGE_CONTEXT" in config,
            kg_gate_enabled=False,
            graphify_kg_links_enabled=graphify_kg_links_enabled,
        )
        return config

    if variant == "kg_off":
        config.pop("KNOWLEDGE_CONTEXT", None)
        config.pop("KNOWLEDGE_GATE", None)
        _strip_graphify_kg_fields(config)
        if kg_off_sys_msg is not None:
            config["SYS_MSG"] = kg_off_sys_msg
        _add_ablation_metadata(
            config,
            seed=seed,
            variant=variant,
            kg_context_enabled=False,
            kg_gate_enabled=False,
            graphify_kg_links_enabled=False,
        )
        return config

    raise ValueError(f"Unknown KG ablation variant: {variant}")


def _has_knowledge_context(base_config: Mapping[str, Any]) -> bool:
    return "KNOWLEDGE_CONTEXT" in base_config


def build_ablation_plan(
    *,
    base_config_path: Path,
    input_dir: Path,
    output_dir: Path,
    experiment_out_dir: Path,
    seeds: Sequence[int],
    include_context_only: bool = True,
    kg_off_sys_msg: Optional[str] = None,
) -> Dict[str, Any]:
    """Generates KG ablation configs and returns the run manifest."""
    base_config: Dict[str, Any] = _load_config(base_config_path)
    if not seeds:
        raise ValueError("At least one seed is required.")

    variants: List[str] = ["kg_on", "kg_off"]
    if include_context_only and _has_knowledge_context(base_config):
        variants.insert(1, "context_only")

    runs: List[Dict[str, Any]] = []
    for seed in seeds:
        seed_dir: Path = output_dir / f"seed-{seed}"
        for variant in variants:
            config_path: Path = seed_dir / f"{variant}.yaml"
            run_out_dir: Path = experiment_out_dir / f"seed-{seed}" / variant
            config: Dict[str, Any] = _make_variant(
                base_config,
                seed=seed,
                variant=variant,
                kg_off_sys_msg=kg_off_sys_msg,
            )
            _write_yaml(config_path, config)
            command: List[str] = [
                "codeevolve",
                f"--inpt_dir={input_dir}",
                f"--cfg_path={config_path}",
                f"--out_dir={run_out_dir}",
                "--load_ckpt=0",
                "--y",
            ]
            runs.append(
                {
                    "run_id": f"seed-{seed}/{variant}",
                    "seed": seed,
                    "variant": variant,
                    "config_path": str(config_path),
                    "out_dir": str(run_out_dir),
                    "command": command,
                }
            )

    warnings: List[str] = []
    if kg_off_sys_msg is None and _model_visible_kg_terms(base_config):
        warnings.append(
            "kg_off removes KNOWLEDGE_CONTEXT and KNOWLEDGE_GATE but the base SYS_MSG "
            "still contains model-visible KG/knowledge terms. Provide --kg-off-sys-msg "
            "or use a neutral base prompt for a cleaner ablation."
        )

    manifest: Dict[str, Any] = {
        "schema_version": 1,
        "experiment": "kg_grounding_component",
        "base_config_path": str(base_config_path),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "experiment_out_dir": str(experiment_out_dir),
        "seeds": list(seeds),
        "variants": variants,
        "metrics_to_compare": list(METRICS_TO_COMPARE),
        "warnings": warnings,
        "claim_boundary": (
            "Compare same-seed KG variants before claiming KG improves evolutionary "
            "outcomes. Candidate KNOWLEDGE USE remains declared self-report unless "
            "a separate verifier supplies verified_usage_score."
        ),
        "runs": runs,
    }
    _write_json(output_dir / "kg_ablation_plan.json", manifest)
    return manifest


def _parse_seeds(raw: str, base_config: Mapping[str, Any]) -> List[int]:
    if raw:
        return [int(value.strip()) for value in raw.split(",") if value.strip()]
    base_seed: Any = base_config.get("SEED", 0)
    if isinstance(base_seed, int):
        return [base_seed]
    return [0]


def parse_args() -> argparse.Namespace:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Generate same-seed KG ablation config variants."
    )
    parser.add_argument("--base-config", required=True, type=Path)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--experiment-out-dir",
        type=Path,
        help="Base output directory for future CodeEvolve runs.",
    )
    parser.add_argument(
        "--seeds",
        default="",
        help="Comma-separated integer seeds. Defaults to SEED from the base config.",
    )
    parser.add_argument(
        "--no-context-only",
        action="store_true",
        help="Do not generate the context_only variant.",
    )
    parser.add_argument(
        "--kg-off-sys-msg",
        type=Path,
        help="Optional file whose contents replace SYS_MSG for kg_off variants.",
    )
    return parser.parse_args()


def main() -> int:
    args: argparse.Namespace = parse_args()
    base_config: Dict[str, Any] = _load_config(args.base_config)
    experiment_out_dir: Path = args.experiment_out_dir or args.output_dir / "runs"
    kg_off_sys_msg: Optional[str] = None
    if args.kg_off_sys_msg is not None:
        kg_off_sys_msg = args.kg_off_sys_msg.read_text(encoding="utf-8")
    manifest: Dict[str, Any] = build_ablation_plan(
        base_config_path=args.base_config,
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        experiment_out_dir=experiment_out_dir,
        seeds=_parse_seeds(args.seeds, base_config),
        include_context_only=not args.no_context_only,
        kg_off_sys_msg=kg_off_sys_msg,
    )
    print(f"Wrote {len(manifest['runs'])} run definitions to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
