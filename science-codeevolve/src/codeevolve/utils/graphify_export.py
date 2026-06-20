# ===--------------------------------------------------------------------------------------===#
#
# Part of the CodeEvolve Project, under the Apache License v2.0.
# See https://github.com/inter-co/science-codeevolve/blob/main/LICENSE for license information.
# SPDX-License-Identifier: Apache-2.0
#
# ===--------------------------------------------------------------------------------------===#
#
# This file exports evolved candidate code into a Graphify-managed corpus.
#
# ===--------------------------------------------------------------------------------------===#

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass, field
from numbers import Real
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from codeevolve.database import Program
from codeevolve.utils.constants import DEFAULT_EXTENSION, LANGUAGE_TO_EXTENSION
from codeevolve.utils.knowledge_use import (
    declared_okf_concept_use,
    declared_usage_evidence_validation,
    declared_usage_traceability,
    declared_usage_traceability_rejection,
    okf_context_available_from_receipts,
    required_decision_concepts_by_id,
)

FINITE_NUMERIC_PENALTY: float = 1.0e30


def _as_bool(value: Any, default: bool) -> bool:
    """Converts common configuration values to bool."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_string_list(value: Any, key: str) -> List[str]:
    """Converts a scalar or list configuration value to a string list."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise ValueError(f"GRAPHIFY_EXPORT.{key} must be a string or list of strings.")


def _safe_token(value: Optional[Any], fallback: str = "unknown") -> str:
    """Returns a filename-safe token."""
    if value is None:
        return fallback
    token: str = re.sub(r"[^A-Za-z0-9_]+", "_", str(value)).strip("_")
    return token or fallback


def _write_once(path: Path, content: str) -> None:
    """Atomically writes a shared file only if it does not already exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return

    temp_path: Path = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    try:
        try:
            os.link(temp_path, path)
        except FileExistsError:
            return
        except OSError:
            try:
                with path.open("x", encoding="utf-8") as output:
                    output.write(content)
            except FileExistsError:
                return
    finally:
        temp_path.unlink(missing_ok=True)


def _write_if_changed(path: Path, content: str) -> None:
    """Atomically writes a shared file when its content changed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return

    temp_path: Path = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    try:
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _indented_block(content: str) -> str:
    """Formats arbitrary text as an indented Markdown code block."""
    if not content:
        return "    (empty)"
    return "\n".join(f"    {line}" if line else "" for line in content.splitlines())


def _yaml_string(value: str) -> str:
    """Returns a YAML-safe double-quoted scalar."""
    return json.dumps(value)


def _json_safe(value: Any) -> Any:
    """Returns a JSON-safe value with finite numbers only."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else FINITE_NUMERIC_PENALTY
    if isinstance(value, int):
        return value
    if isinstance(value, Real):
        number: float = float(value)
        return number if math.isfinite(number) else FINITE_NUMERIC_PENALTY
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _looks_like_absolute_path(value: str) -> bool:
    """Returns whether a string appears to expose a local absolute path."""
    if Path(value).expanduser().is_absolute():
        return True
    return re.match(r"^[A-Za-z]:[\\/]", value) is not None


def _public_receipt_value(value: Any) -> Any:
    """Returns a Graphify-safe receipt value without local absolute paths."""
    if isinstance(value, dict):
        public: Dict[str, Any] = {}
        for key, item in value.items():
            key_text: str = str(key)
            if key_text in {"resolved_path", "local_path"}:
                continue
            public[key_text] = _public_receipt_value(item)
        return public
    if isinstance(value, list):
        return [_public_receipt_value(item) for item in value]
    if isinstance(value, tuple):
        return [_public_receipt_value(item) for item in value]
    if isinstance(value, str) and _looks_like_absolute_path(value):
        basename: str = Path(value).name or "path"
        return f"<absolute-path-redacted:{basename}>"
    return value


def _public_fixture_summary(fixture_summary: Any) -> Dict[str, Any]:
    """Builds a Graphify-safe fixture summary without local fixture paths."""
    if not isinstance(fixture_summary, dict):
        return {}
    return _public_receipt_value(
        {
            "train_cases": fixture_summary.get("train_cases", 0),
            "holdout_cases": fixture_summary.get("holdout_cases", 0),
            "private_holdout_cases": fixture_summary.get("private_holdout_cases", 0),
            "traceable_train_fixture_names": fixture_summary.get(
                "traceable_train_fixture_names", []
            ),
            "traceable_train_fixture_names_truncated": fixture_summary.get(
                "traceable_train_fixture_names_truncated", 0
            ),
            "fixture_receipts_sha256": fixture_summary.get("fixture_receipts_sha256"),
        }
    )


def _public_knowledge_gate_summary(
    *,
    knowledge_gate_receipt: Dict[str, Any],
    receipt_path: Optional[str],
    receipt_sha256: Optional[str],
) -> Dict[str, Any]:
    """Builds the public Graphify link to a private knowledge-gate receipt."""
    if not knowledge_gate_receipt:
        return {}
    wrf_target: Dict[str, Any] = knowledge_gate_receipt.get("wrf_target", {})
    return _public_receipt_value(
        {
            "schema_version": knowledge_gate_receipt.get("schema_version"),
            "gate_passed": knowledge_gate_receipt.get("gate_passed"),
            "domain": knowledge_gate_receipt.get("domain"),
            "receipt_path": receipt_path,
            "receipt_sha256": receipt_sha256,
            "manifest_sha256": knowledge_gate_receipt.get("manifest_sha256"),
            "knowledge_context_sha256": knowledge_gate_receipt.get("knowledge_context_sha256"),
            "wrf_commit": wrf_target.get("wrf_commit"),
        }
    )


def _as_finite_float(value: Any, default: float = 0.0) -> float:
    """Converts numeric-like values to finite floats."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, Real):
        number: float = float(value)
        return number if math.isfinite(number) else default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _required_decision_declaration_status(
    *,
    knowledge_gate_receipt: Dict[str, Any],
    context_available: List[Dict[str, Any]],
    context_declared_used: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Returns whether declared OKF use covers every required decision id."""
    decision_ids: List[str] = [
        str(decision_id)
        for decision_id in knowledge_gate_receipt.get("kg_decision_ids", [])
        if str(decision_id).strip()
    ]
    manifest_context_paths: Set[str] = {
        str(path)
        for path in knowledge_gate_receipt.get("kg_context_paths", [])
        if str(path).strip()
    }
    if decision_ids and not manifest_context_paths:
        concepts_by_id: Dict[str, List[str]] = {decision_id: [] for decision_id in decision_ids}
    else:
        concepts_by_id = required_decision_concepts_by_id(
            context_available=context_available,
            decision_ids=decision_ids,
            manifest_context_paths=manifest_context_paths,
            configured_by_id=knowledge_gate_receipt.get("required_decision_concepts_by_id"),
            require_configured_by_id=bool(decision_ids),
        )

    declared_ids: Set[str] = {str(item["concept_id"]) for item in context_declared_used}
    unavailable_decision_ids: List[str] = [
        decision_id for decision_id in decision_ids if not concepts_by_id.get(decision_id)
    ]
    missing_declared_decision_ids: List[str] = [
        decision_id
        for decision_id, concept_ids in concepts_by_id.items()
        if concept_ids and not declared_ids.intersection(concept_ids)
    ]
    passed: int = 0 if unavailable_decision_ids or missing_declared_decision_ids else 1
    if not decision_ids:
        passed = 1

    return {
        "required": 1 if decision_ids else 0,
        "passed": passed,
        "kg_context_paths": sorted(manifest_context_paths),
        "decision_concepts_by_id": concepts_by_id,
        "unavailable_decision_ids": unavailable_decision_ids,
        "missing_declared_decision_ids": missing_declared_decision_ids,
    }


def _build_knowledge_use_receipt(
    *,
    program: Program,
    knowledge_gate_receipt: Dict[str, Any],
) -> Dict[str, Any]:
    """Builds a candidate-level receipt for OKF knowledge exposure and use."""
    context_available: List[Dict[str, Any]] = okf_context_available_from_receipts(
        knowledge_gate_receipt.get("knowledge_context_receipts", [])
    )
    context_declared_used, declaration_present, explicit_none = declared_okf_concept_use(
        model_msg=program.model_msg,
        context_available=context_available,
    )
    required_decision_declaration: Dict[str, Any] = _required_decision_declaration_status(
        knowledge_gate_receipt=knowledge_gate_receipt,
        context_available=context_available,
        context_declared_used=context_declared_used,
    )
    context_declared_traceability: List[Dict[str, Any]] = []
    require_evidence_traceability: bool = (
        str(knowledge_gate_receipt.get("domain", "")) == "wrf_single_physics"
    )
    for item in context_declared_used:
        usage: str = str(item["usage"])
        traceability: Dict[str, Any] = declared_usage_traceability(usage)
        evidence_validation: Dict[str, Any] = declared_usage_evidence_validation(
            usage,
            model_msg=program.model_msg,
            fixture_summary=knowledge_gate_receipt.get("fixture_summary"),
            eval_metrics=program.eval_metrics or {},
        )
        rejection: Optional[str] = declared_usage_traceability_rejection(
            usage,
            code=program.code,
            model_msg=program.model_msg,
            fixture_summary=knowledge_gate_receipt.get("fixture_summary"),
            eval_metrics=program.eval_metrics or {},
            require_evidence_traceability=require_evidence_traceability,
        )
        context_declared_traceability.append(
            {
                "concept_id": str(item["concept_id"]),
                "evidence_traceability_required": (1 if require_evidence_traceability else 0),
                "traceability_present": 0 if rejection else 1,
                "fields": traceability["fields"],
                "usable_fields": traceability["usable_fields"],
                "evidence_validation": evidence_validation,
                "placeholder_fields": traceability["placeholder_fields"],
                "missing": traceability["missing"],
                "rejection": rejection,
            }
        )
    eval_metrics: Dict[str, Any] = program.eval_metrics or {}
    exposure_score: float = 1.0 if context_available else 0.0
    declared_usage_score: float = (
        min(1.0, len(context_declared_used) / len(context_available)) if context_available else 0.0
    )
    declared_traceability_passed: int = (
        1
        if context_declared_traceability
        and all(item["traceability_present"] for item in context_declared_traceability)
        else 0
    )
    declared_traceability_score: float = float(declared_traceability_passed)
    declared_required_decision_score: float = float(required_decision_declaration["passed"])
    semantic_gate_reported: float = 1.0 if "semantic_gate_passed" in eval_metrics else 0.0
    semantic_gate_passed: float = _as_finite_float(eval_metrics.get("semantic_gate_passed"), 0.0)
    acceptance_policy_passed: float = _as_finite_float(
        eval_metrics.get("acceptance_policy_passed"), 0.0
    )
    gate_alignment_score: float = (
        1.0 if semantic_gate_reported >= 1.0 and semantic_gate_passed >= 1.0 else 0.0
    )
    if not knowledge_gate_receipt:
        gate_alignment_score = 0.0
    score_parts: List[float] = [
        exposure_score,
        declared_usage_score,
        declared_traceability_score,
        gate_alignment_score,
    ]
    if required_decision_declaration["required"]:
        score_parts.append(declared_required_decision_score)
    overall_score: float = sum(score_parts) / len(score_parts)

    if not context_available:
        assessment_status: str = "no_okf_context"
    elif not declaration_present:
        assessment_status = "no_declared_usage"
    elif explicit_none:
        assessment_status = "declared_no_relevant_usage"
    elif context_declared_used and not declared_traceability_passed:
        assessment_status = "declared_usage_unstructured"
    elif (
        context_declared_used
        and required_decision_declaration["required"]
        and not required_decision_declaration["passed"]
    ):
        assessment_status = "declared_usage_missing_required_decision"
    elif context_declared_used:
        assessment_status = "declared_usage"
    else:
        assessment_status = "declared_usage_unmatched"

    return {
        "knowledge_use_schema_version": 2,
        "okf_bundle": {
            "root": knowledge_gate_receipt.get("okf_bundle_root"),
            "okf_version": "0.1" if knowledge_gate_receipt.get("okf_bundle_root") else None,
            "bundle_sha256": knowledge_gate_receipt.get("knowledge_context_sha256"),
        },
        "context_available": context_available,
        "context_declared_used": context_declared_used,
        "context_declared_traceability": context_declared_traceability,
        "declaration_present": 1 if declaration_present else 0,
        "declared_traceability_passed": declared_traceability_passed,
        "declared_required_decision_passed": required_decision_declaration["passed"],
        "policy_evidence": {
            "required_decision_ids": knowledge_gate_receipt.get("kg_decision_ids", []),
            "required_decision_concept_ids": knowledge_gate_receipt.get(
                "required_decision_concept_ids", []
            ),
            "kg_context_paths": knowledge_gate_receipt.get("kg_context_paths", []),
            "required_decision_declarations": required_decision_declaration,
            "acceptance_policy_passed": acceptance_policy_passed,
            "semantic_gate_reported": semantic_gate_reported,
            "semantic_gate_passed": semantic_gate_passed,
            "static_policy_rejections": _as_finite_float(
                eval_metrics.get("static_policy_rejections"), 0.0
            ),
            "knowledge_policy_rejections": _as_finite_float(
                eval_metrics.get("knowledge_policy_rejections"), 0.0
            ),
            "failure_code": _as_finite_float(eval_metrics.get("failure_code"), 0.0),
        },
        "evaluation_evidence": {
            "correct": _as_finite_float(eval_metrics.get("correct"), 0.0),
            "fitness": _as_finite_float(program.fitness, 0.0),
            "max_abs_error": _as_finite_float(eval_metrics.get("max_abs_error"), 0.0),
            "max_rel_error": _as_finite_float(eval_metrics.get("max_rel_error"), 0.0),
        },
        "assessment": {
            "usage_assessment_kind": "declared_self_report",
            "assessment_status": assessment_status,
            "knowledge_exposure_score": exposure_score,
            "declared_usage_score": declared_usage_score,
            "declared_traceability_score": declared_traceability_score,
            "declared_traceability_passed": declared_traceability_passed,
            "declared_required_decision_score": declared_required_decision_score,
            "declared_required_decision_passed": required_decision_declaration["passed"],
            "verified_usage_available": 0.0,
            "verified_usage_score": 0.0,
            "gate_alignment_score": gate_alignment_score,
            "overall_declared_use_score": overall_score,
            "overall_knowledge_use_score": None,
            "overall_knowledge_use_score_kind": (
                "deprecated_alias_removed_use_overall_declared_use_score"
            ),
        },
    }


@dataclass(frozen=True)
class GraphifyExportRecord:
    """Result of exporting one evolved program."""

    code_path: Path
    metadata_path: Path
    candidate_path: Path
    manifest_path: Path
    diff_path: Optional[Path] = None


@dataclass
class EvolvedCodeGraphExporter:
    """Exports evaluated programs into a corpus that Graphify can index.

    The exported corpus is intentionally outside the wiki. Graphify owns the
    evolved code files and structural code graph; KG/wiki pages remain the
    source of domain assumptions and validation decisions. Sidecar metadata
    records the bridge between the two layers.
    """

    root: Path
    mode: str = "all"
    include_initial: bool = True
    required: bool = True
    knowledge_links: List[str] = field(default_factory=list)
    knowledge_context_paths: List[str] = field(default_factory=list)
    knowledge_gate_receipt: Dict[str, Any] = field(default_factory=dict)
    knowledge_gate_receipt_path: Optional[str] = None
    knowledge_gate_receipt_sha256: Optional[str] = None

    @classmethod
    def from_config(
        cls,
        config: Dict[str, Any],
        args: Dict[str, Any],
    ) -> Optional["EvolvedCodeGraphExporter"]:
        """Creates an exporter from ``GRAPHIFY_EXPORT`` config.

        Args:
            config: Full CodeEvolve config.
            args: Runtime arguments containing output paths.

        Returns:
            Configured exporter, or ``None`` when disabled.
        """
        export_cfg: Any = config.get("GRAPHIFY_EXPORT")
        if export_cfg is None:
            return None
        if not isinstance(export_cfg, dict):
            raise ValueError("GRAPHIFY_EXPORT must be a mapping.")
        if not _as_bool(export_cfg.get("enabled"), True):
            return None

        root_value: str = str(export_cfg.get("root", "graphify-evolve-corpus"))
        root_path: Path = Path(root_value).expanduser()
        if not root_path.is_absolute():
            root_path = Path(args["out_dir"]) / root_path

        knowledge_context_paths: List[str] = _as_string_list(
            export_cfg.get("knowledge_context_paths"), "knowledge_context_paths"
        )
        if not knowledge_context_paths:
            knowledge_context_paths = _as_string_list(
                config.get("KNOWLEDGE_CONTEXT", {}).get("paths"), "knowledge_context_paths"
            )

        return cls(
            root=root_path,
            mode=str(export_cfg.get("mode", "all")),
            include_initial=_as_bool(export_cfg.get("include_initial"), True),
            required=_as_bool(export_cfg.get("required"), True),
            knowledge_links=_as_string_list(export_cfg.get("knowledge_links"), "knowledge_links"),
            knowledge_context_paths=knowledge_context_paths,
            knowledge_gate_receipt=dict(config.get("_KNOWLEDGE_GATE_RECEIPT", {})),
            knowledge_gate_receipt_path=config.get("_KNOWLEDGE_GATE_RECEIPT_PATH"),
            knowledge_gate_receipt_sha256=config.get("_KNOWLEDGE_GATE_RECEIPT_SHA256"),
        )

    def export_program(
        self,
        program: Program,
        *,
        role: str,
        became_best: bool = False,
        prompt: Optional[Program] = None,
    ) -> Optional[GraphifyExportRecord]:
        """Exports a program and sidecar metadata if it matches the export mode.

        Args:
            program: Evaluated program to export.
            role: Human-readable role, such as ``"initial"`` or ``"candidate"``.
            became_best: Whether this program became the local best after insertion.
            prompt: Prompt used to generate the program, if available.

        Returns:
            Paths written for this program, or ``None`` when filtered out.
        """
        if not self._should_export(program, role=role, became_best=became_best):
            return None

        island_token: str = _safe_token(program.island_found)
        epoch: int = int(program.iteration_found or 0)
        program_token: str = _safe_token(program.id)[:12]
        role_token: str = _safe_token(role)
        stem: str = f"epoch_{epoch:06d}__{role_token}__program_{program_token}"
        extension: str = LANGUAGE_TO_EXTENSION.get(program.language, DEFAULT_EXTENSION)

        island_dir: Path = self.root / f"island_{island_token}"
        code_dir: Path = island_dir / "code"
        metadata_dir: Path = island_dir / "metadata"
        diff_dir: Path = island_dir / "diffs"
        candidate_dir: Path = island_dir / "candidates"
        code_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.mkdir(parents=True, exist_ok=True)
        diff_dir.mkdir(parents=True, exist_ok=True)
        candidate_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_corpus_readme()
        self._ensure_knowledge_bridge()

        code_path: Path = code_dir / f"{stem}{extension}"
        metadata_path: Path = metadata_dir / f"{stem}.json"
        candidate_path: Path = candidate_dir / f"{stem}.md"
        diff_path: Optional[Path] = diff_dir / f"{stem}.md" if program.model_msg else None
        manifest_path: Path = island_dir / "manifest.jsonl"

        code_path.write_text(program.code, encoding="utf-8")
        if diff_path is not None:
            diff_path.write_text(
                self._build_diff_document(program=program, role=role),
                encoding="utf-8",
            )
        metadata: Dict[str, Any] = self._build_metadata(
            program=program,
            role=role,
            became_best=became_best,
            prompt=prompt,
            code_path=code_path,
            metadata_path=metadata_path,
            candidate_path=candidate_path,
            diff_path=diff_path,
        )
        metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8"
        )
        candidate_path.write_text(
            self._build_candidate_card(
                program=program,
                role=role,
                became_best=became_best,
                prompt=prompt,
                code_path=code_path,
                metadata_path=metadata_path,
                candidate_path=candidate_path,
                diff_path=diff_path,
            ),
            encoding="utf-8",
        )
        with manifest_path.open("a", encoding="utf-8") as manifest_file:
            manifest_file.write(json.dumps(metadata, sort_keys=True, allow_nan=False) + "\n")

        return GraphifyExportRecord(
            code_path=code_path,
            metadata_path=metadata_path,
            candidate_path=candidate_path,
            manifest_path=manifest_path,
            diff_path=diff_path,
        )

    def _should_export(self, program: Program, *, role: str, became_best: bool) -> bool:
        """Returns whether a program should be exported under the configured mode."""
        if role == "initial" and not self.include_initial:
            return False
        if self.mode == "all":
            return True
        if self.mode == "positive":
            return program.fitness > 0
        if self.mode == "best":
            return became_best or role == "initial"
        raise ValueError("GRAPHIFY_EXPORT.mode must be one of: all, positive, best.")

    def _build_metadata(
        self,
        *,
        program: Program,
        role: str,
        became_best: bool,
        prompt: Optional[Program],
        code_path: Path,
        metadata_path: Path,
        candidate_path: Path,
        diff_path: Optional[Path],
    ) -> Dict[str, Any]:
        """Builds JSON metadata that links evolved code to KG knowledge."""
        model_msg_sha256: Optional[str] = None
        if program.model_msg:
            model_msg_sha256 = hashlib.sha256(program.model_msg.encode("utf-8")).hexdigest()
        original_prompt_id: Optional[str] = program.original_prompt_id
        if original_prompt_id is None:
            original_prompt_id = program.prompt_id
        resolved_prompt_id: Optional[str] = program.resolved_prompt_id
        if resolved_prompt_id is None:
            resolved_prompt_id = prompt.id if prompt is not None else program.prompt_id
        prompt_fallback_used: bool = program.prompt_fallback_used or (
            resolved_prompt_id is not None and original_prompt_id != resolved_prompt_id
        )
        knowledge_use: Dict[str, Any] = _build_knowledge_use_receipt(
            program=program,
            knowledge_gate_receipt=self.knowledge_gate_receipt,
        )
        public_knowledge_gate: Dict[str, Any] = _public_knowledge_gate_summary(
            knowledge_gate_receipt=self.knowledge_gate_receipt,
            receipt_path=self.knowledge_gate_receipt_path,
            receipt_sha256=self.knowledge_gate_receipt_sha256,
        )
        public_fixture_summary: Dict[str, Any] = _public_fixture_summary(
            self.knowledge_gate_receipt.get("fixture_summary", {})
        )
        public_context_receipts: List[Dict[str, Any]] = _public_receipt_value(
            self.knowledge_gate_receipt.get("knowledge_context_receipts", [])
        )
        public_knowledge_context_paths: List[str] = _public_receipt_value(
            self.knowledge_context_paths
        )

        return _json_safe(
            {
                "schema_version": 1,
                "role": role,
                "program_id": program.id,
                "parent_id": program.parent_id,
                "prompt_id": program.prompt_id,
                "original_prompt_id": original_prompt_id,
                "resolved_prompt_id": resolved_prompt_id,
                "prompt_fallback_used": prompt_fallback_used,
                "prompt_program_id": prompt.id if prompt is not None else None,
                "inspiration_ids": program.inspiration_ids,
                "model_id": program.model_id,
                "language": program.language,
                "island_found": program.island_found,
                "iteration_found": program.iteration_found,
                "generation": program.generation,
                "depth": program.depth,
                "returncode": program.returncode,
                "fitness": program.fitness,
                "became_best": became_best,
                "eval_metrics": program.eval_metrics,
                "features": program.features,
                "error": program.error,
                "warning": program.warning,
                "code_sha256": hashlib.sha256(program.code.encode("utf-8")).hexdigest(),
                "model_msg_sha256": model_msg_sha256,
                "code_path": str(code_path.relative_to(self.root)),
                "metadata_path": str(metadata_path.relative_to(self.root)),
                "candidate_card_path": str(candidate_path.relative_to(self.root)),
                "diff_path": (
                    str(diff_path.relative_to(self.root)) if diff_path is not None else None
                ),
                "knowledge_links": self.knowledge_links,
                "knowledge_context_paths": public_knowledge_context_paths,
                "knowledge_gate": public_knowledge_gate,
                "knowledge_gate_receipt_path": _public_receipt_value(
                    self.knowledge_gate_receipt_path
                ),
                "knowledge_gate_receipt_sha256": self.knowledge_gate_receipt_sha256,
                "evidence_manifest_sha256": self.knowledge_gate_receipt.get("manifest_sha256"),
                "wrf_commit": self.knowledge_gate_receipt.get("wrf_target", {}).get("wrf_commit"),
                "wrf_target": _public_receipt_value(self.knowledge_gate_receipt.get("wrf_target")),
                "kg_decision_ids": self.knowledge_gate_receipt.get("kg_decision_ids", []),
                "required_decision_concept_ids": self.knowledge_gate_receipt.get(
                    "required_decision_concept_ids", []
                ),
                "fixture_summary": public_fixture_summary,
                "knowledge_context_sha256": self.knowledge_gate_receipt.get(
                    "knowledge_context_sha256"
                ),
                "knowledge_context_receipts": public_context_receipts,
                "knowledge_use": _public_receipt_value(knowledge_use),
            }
        )

    def _build_diff_document(self, *, program: Program, role: str) -> str:
        """Builds a Markdown document containing the generated SEARCH/REPLACE diff."""
        return "\n".join(
            [
                f"# Generated Diff for Program {program.id}",
                "",
                f"- Role: `{role}`",
                f"- Parent program: `{program.parent_id}`",
                f"- Prompt program: `{program.prompt_id}`",
                f"- Model id: `{program.model_id}`",
                "",
                "## Diff",
                "",
                _indented_block(program.model_msg or ""),
                "",
            ]
        )

    def _build_candidate_card(
        self,
        *,
        program: Program,
        role: str,
        became_best: bool,
        prompt: Optional[Program],
        code_path: Path,
        metadata_path: Path,
        candidate_path: Path,
        diff_path: Optional[Path],
    ) -> str:
        """Builds a Markdown bridge card for semantic Graphify extraction."""
        relative_code: str = str(code_path.relative_to(self.root))
        relative_metadata: str = str(metadata_path.relative_to(self.root))
        relative_card: str = str(candidate_path.relative_to(self.root))
        relative_diff: Optional[str] = (
            str(diff_path.relative_to(self.root)) if diff_path is not None else None
        )
        original_prompt_id: Optional[str] = program.original_prompt_id
        if original_prompt_id is None:
            original_prompt_id = program.prompt_id
        resolved_prompt_id: Optional[str] = program.resolved_prompt_id
        if resolved_prompt_id is None:
            resolved_prompt_id = prompt.id if prompt is not None else program.prompt_id
        prompt_fallback_used: bool = program.prompt_fallback_used or (
            resolved_prompt_id is not None and original_prompt_id != resolved_prompt_id
        )
        knowledge_use: Dict[str, Any] = _build_knowledge_use_receipt(
            program=program,
            knowledge_gate_receipt=self.knowledge_gate_receipt,
        )
        public_receipt_path: Any = _public_receipt_value(self.knowledge_gate_receipt_path)
        public_fixture_summary: Dict[str, Any] = _public_fixture_summary(
            self.knowledge_gate_receipt.get("fixture_summary", {})
        )
        public_knowledge_context_paths: List[str] = _public_receipt_value(
            self.knowledge_context_paths
        )

        lines: List[str] = [
            "---",
            "schema_version: 1",
            f"program_id: {_yaml_string(program.id)}",
            f"role: {_yaml_string(role)}",
            f"fitness: {_json_safe(program.fitness)}",
            f"became_best: {str(became_best).lower()}",
            f"original_prompt_id: {_yaml_string(original_prompt_id or '')}",
            f"resolved_prompt_id: {_yaml_string(resolved_prompt_id or '')}",
            f"prompt_fallback_used: {str(prompt_fallback_used).lower()}",
            f"code_path: {_yaml_string(relative_code)}",
            f"metadata_path: {_yaml_string(relative_metadata)}",
            f"candidate_card_path: {_yaml_string(relative_card)}",
            f"diff_path: {_yaml_string(relative_diff) if relative_diff is not None else 'null'}",
        ]
        if self.knowledge_links:
            lines.append("knowledge_links:")
            lines.extend(f"  - {_yaml_string(link)}" for link in self.knowledge_links)
        else:
            lines.append("knowledge_links: []")
        if public_knowledge_context_paths:
            lines.append("knowledge_context_paths:")
            lines.extend(f"  - {_yaml_string(path)}" for path in public_knowledge_context_paths)
        else:
            lines.append("knowledge_context_paths: []")
        if self.knowledge_gate_receipt:
            lines.extend(
                [
                    f"knowledge_gate_receipt_path: {_yaml_string(str(public_receipt_path or ''))}",
                    f"knowledge_gate_receipt_sha256: {_yaml_string(self.knowledge_gate_receipt_sha256 or '')}",
                    f"evidence_manifest_sha256: {_yaml_string(str(self.knowledge_gate_receipt.get('manifest_sha256', '')))}",
                    f"wrf_commit: {_yaml_string(str(self.knowledge_gate_receipt.get('wrf_target', {}).get('wrf_commit', '')))}",
                ]
            )
        lines.extend(
            [
                "---",
                "",
                f"# CodeEvolve Candidate {program.id}",
                "",
                "This card links one evolved code artifact to its evaluation metadata, "
                "generated diff, lineage, and KG context so Graphify semantic extraction "
                "can connect code changes with domain knowledge.",
                "",
                "## Artifacts",
                "",
                f"- Source code: `{relative_code}`",
                f"- Metadata: `{relative_metadata}`",
                f"- Candidate card: `{relative_card}`",
                (
                    f"- Generated diff: `{relative_diff}`"
                    if relative_diff
                    else "- Generated diff: `(none)`"
                ),
                "",
                "## Lineage",
                "",
                f"- Program id: `{program.id}`",
                f"- Parent program id: `{program.parent_id}`",
                f"- Original prompt id: `{original_prompt_id}`",
                f"- Resolved prompt id: `{resolved_prompt_id}`",
                f"- Prompt fallback used: `{prompt_fallback_used}`",
                f"- Prompt program id: `{prompt.id if prompt is not None else None}`",
                f"- Inspiration ids: `{', '.join(program.inspiration_ids)}`",
                f"- Island: `{program.island_found}`",
                f"- Iteration: `{program.iteration_found}`",
                f"- Generation: `{program.generation}`",
                f"- Depth: `{program.depth}`",
                "",
                "## Evaluation",
                "",
                f"- Fitness: `{_json_safe(program.fitness)}`",
                f"- Return code: `{program.returncode}`",
                f"- Became best: `{became_best}`",
                "",
                "## KG Links",
                "",
            ]
        )
        if self.knowledge_links:
            lines.extend(f"- {link}" for link in self.knowledge_links)
        else:
            lines.append("- (none configured)")
        lines.extend(["", "## Knowledge Context Paths", ""])
        if public_knowledge_context_paths:
            lines.extend(f"- `{path}`" for path in public_knowledge_context_paths)
        else:
            lines.append("- (none configured)")
        if self.knowledge_gate_receipt:
            lines.extend(
                [
                    "",
                    "## Knowledge Gate",
                    "",
                    f"- Receipt path: `{public_receipt_path}`",
                    f"- Receipt sha256: `{self.knowledge_gate_receipt_sha256}`",
                    f"- Evidence manifest sha256: `{self.knowledge_gate_receipt.get('manifest_sha256')}`",
                    f"- Knowledge context sha256: `{self.knowledge_gate_receipt.get('knowledge_context_sha256')}`",
                    f"- WRF commit: `{self.knowledge_gate_receipt.get('wrf_target', {}).get('wrf_commit')}`",
                    f"- KG decision ids: `{', '.join(self.knowledge_gate_receipt.get('kg_decision_ids', []))}`",
                    f"- Fixture summary: `{_json_safe(public_fixture_summary)}`",
                ]
            )
        lines.extend(
            [
                "",
                "## Knowledge Use Receipt",
                "",
                f"- Assessment status: `{knowledge_use['assessment']['assessment_status']}`",
                f"- OKF context available: `{len(knowledge_use['context_available'])}`",
                f"- Declared OKF concepts used: `{len(knowledge_use['context_declared_used'])}`",
                f"- Overall declared-use score: `{_json_safe(knowledge_use['assessment']['overall_declared_use_score'])}`",
            ]
        )
        if knowledge_use["context_declared_used"]:
            lines.append("- Declared concepts:")
            lines.extend(
                f"  - `{item['concept_id']}`: {item['usage']}"
                for item in knowledge_use["context_declared_used"]
            )
        lines.append("")
        return "\n".join(lines)

    def _ensure_corpus_readme(self) -> None:
        """Writes a corpus README explaining how Graphify should own this folder."""
        readme_path: Path = self.root / "README.md"
        _write_once(
            readme_path,
            "\n".join(
                [
                    "# CodeEvolve Graphify Corpus",
                    "",
                    "This directory contains candidate code exported from a CodeEvolve run.",
                    "",
                    "- Graphify owns the evolved code graph for this directory.",
                    "- KG/wiki pages own domain assumptions, validation policy, and decisions.",
                    "- Candidate Markdown cards and metadata sidecars link each code file back to KG pages and evaluation metrics.",
                    "",
                    "Use semantic Graphify extraction when you need queryable KG-code links:",
                    "",
                    "```text",
                    "/graphify . --update",
                    "```",
                    "",
                    "Use the structural code refresh only for pure code AST updates:",
                    "",
                    "```bash",
                    "graphify update .",
                    "```",
                    "",
                    "`graphify update .` can skip semantic extraction for code-only changes, so it is not sufficient when candidate cards, metadata, or KG bridge files changed.",
                    "",
                ]
            ),
        )

    def _ensure_knowledge_bridge(self) -> None:
        """Writes the run-level bridge from Graphify corpus to KG pages."""
        bridge_path: Path = self.root / "knowledge_bridge.md"
        public_knowledge_context_paths: List[str] = _public_receipt_value(
            self.knowledge_context_paths
        )
        lines: List[str] = [
            "# Knowledge Bridge",
            "",
            "This file records the KG pages that should be considered when interpreting this evolved-code corpus.",
            "Run semantic Graphify extraction on this corpus when these links change so the KG-code bridge becomes queryable.",
            "",
            "## KG Links",
            "",
        ]
        if self.knowledge_links:
            lines.extend(f"- {link}" for link in self.knowledge_links)
        else:
            lines.append("- (none configured)")
        lines.extend(["", "## Knowledge Context Paths", ""])
        if public_knowledge_context_paths:
            lines.extend(f"- `{path}`" for path in public_knowledge_context_paths)
        else:
            lines.append("- (none configured)")
        if self.knowledge_gate_receipt:
            public_receipt_path = _public_receipt_value(self.knowledge_gate_receipt_path)
            lines.extend(
                [
                    "",
                    "## Knowledge Gate Receipt",
                    "",
                    f"- Receipt path: `{public_receipt_path}`",
                    f"- Receipt sha256: `{self.knowledge_gate_receipt_sha256}`",
                    f"- Evidence manifest sha256: `{self.knowledge_gate_receipt.get('manifest_sha256')}`",
                    f"- Knowledge context sha256: `{self.knowledge_gate_receipt.get('knowledge_context_sha256')}`",
                    f"- WRF target commit: `{self.knowledge_gate_receipt.get('wrf_target', {}).get('wrf_commit')}`",
                ]
            )
        lines.append("")
        _write_if_changed(bridge_path, "\n".join(lines))
