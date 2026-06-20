# ===--------------------------------------------------------------------------------------===#
#
# Part of the CodeEvolve Project, under the Apache License v2.0.
# See https://github.com/inter-co/science-codeevolve/blob/main/LICENSE for license information.
# SPDX-License-Identifier: Apache-2.0
#
# ===--------------------------------------------------------------------------------------===#
#
# This file implements unit tests for evolved-code Graphify export.
#
# ===--------------------------------------------------------------------------------------===#

import json
import math
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from codeevolve.database import Program
from codeevolve.utils.graphify_export import EvolvedCodeGraphExporter


def _make_program(
    *,
    code: str = "def f():\n    return 1\n",
    fitness: float = 1.0,
    language: str = "python",
    model_msg: str = "diff",
    eval_metrics: Optional[Dict[str, Any]] = None,
) -> Program:
    """Creates a minimal evaluated program for export tests."""
    metrics: Dict[str, Any] = {"fitness": fitness}
    if eval_metrics is not None:
        metrics.update(eval_metrics)
    return Program(
        id="prog-1234567890",
        code=code,
        language=language,
        returncode=0,
        eval_metrics=metrics,
        features={"fitness": fitness},
        fitness=fitness,
        parent_id="parent-1",
        iteration_found=7,
        generation=7,
        island_found=2,
        prompt_id="prompt-1",
        inspiration_ids=["insp-1"],
        model_id=0,
        model_msg=model_msg,
        depth=3,
    )


class TestEvolvedCodeGraphExporter:
    """Test suite for the evolved-code Graphify exporter."""

    def test_from_config_disabled_returns_none(self, tmp_path: Path):
        """Tests that disabled export config does not create an exporter."""
        config: Dict[str, Any] = {"GRAPHIFY_EXPORT": {"enabled": False}}
        exporter = EvolvedCodeGraphExporter.from_config(config, {"out_dir": tmp_path})
        assert exporter is None

    def test_from_config_inherits_knowledge_context_paths(self, tmp_path: Path):
        """Tests that Graphify metadata can inherit KNOWLEDGE_CONTEXT paths."""
        config: Dict[str, Any] = {
            "KNOWLEDGE_CONTEXT": {"paths": ["wiki/overview.md"]},
            "GRAPHIFY_EXPORT": {"enabled": True},
        }

        exporter = EvolvedCodeGraphExporter.from_config(config, {"out_dir": tmp_path})

        assert exporter is not None
        assert exporter.root == tmp_path / "graphify-evolve-corpus"
        assert exporter.knowledge_context_paths == ["wiki/overview.md"]

    def test_exports_code_metadata_manifest_and_bridge(self, tmp_path: Path):
        """Tests that a program export writes code, metadata, manifest, and KG bridge."""
        exporter = EvolvedCodeGraphExporter(
            root=tmp_path / "corpus",
            knowledge_links=["[[wrf-single-physics-optimization]]"],
            knowledge_context_paths=["wiki/overview.md"],
        )
        program: Program = _make_program()
        prompt: Program = Program(id="prompt-1", code="prompt", language="text")

        record = exporter.export_program(
            program,
            role="candidate",
            became_best=True,
            prompt=prompt,
        )

        assert record is not None
        assert record.code_path.read_text(encoding="utf-8") == program.code
        assert record.code_path.suffix == ".py"
        assert record.candidate_path.exists()
        assert record.diff_path is not None
        assert record.diff_path.exists()
        metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
        assert metadata["program_id"] == program.id
        assert metadata["parent_id"] == "parent-1"
        assert metadata["original_prompt_id"] == "prompt-1"
        assert metadata["resolved_prompt_id"] == "prompt-1"
        assert metadata["prompt_fallback_used"] is False
        assert metadata["prompt_program_id"] == "prompt-1"
        assert metadata["became_best"] is True
        assert metadata["candidate_card_path"] == str(
            record.candidate_path.relative_to(exporter.root)
        )
        assert metadata["diff_path"] == str(record.diff_path.relative_to(exporter.root))
        assert metadata["model_msg_sha256"] is not None
        assert metadata["knowledge_links"] == ["[[wrf-single-physics-optimization]]"]
        assert metadata["knowledge_context_paths"] == ["wiki/overview.md"]

        card = record.candidate_path.read_text(encoding="utf-8")
        assert "CodeEvolve Candidate" in card
        assert "`island_2/code/" in card
        assert "Prompt fallback used: `False`" in card
        assert "[[wrf-single-physics-optimization]]" in card
        assert "diff" in record.diff_path.read_text(encoding="utf-8")

        manifest_lines = record.manifest_path.read_text(encoding="utf-8").splitlines()
        assert len(manifest_lines) == 1
        assert json.loads(manifest_lines[0])["program_id"] == program.id
        assert "Graphify owns the evolved code graph" in (
            tmp_path / "corpus" / "README.md"
        ).read_text(encoding="utf-8")
        assert "/graphify . --update" in (tmp_path / "corpus" / "README.md").read_text(
            encoding="utf-8"
        )
        assert "[[wrf-single-physics-optimization]]" in (
            tmp_path / "corpus" / "knowledge_bridge.md"
        ).read_text(encoding="utf-8")

    def test_export_does_not_overwrite_existing_root_docs(self, tmp_path: Path):
        """Tests that shared root docs are not clobbered by later exports."""
        root = tmp_path / "corpus"
        root.mkdir()
        (root / "README.md").write_text("custom readme", encoding="utf-8")
        exporter = EvolvedCodeGraphExporter(root=root)

        exporter.export_program(_make_program(), role="candidate")

        assert (root / "README.md").read_text(encoding="utf-8") == "custom readme"

    def test_knowledge_bridge_updates_when_links_change(self, tmp_path: Path):
        """Tests that stale KG bridge files are refreshed across exporter configs."""
        root = tmp_path / "corpus"
        first_exporter = EvolvedCodeGraphExporter(
            root=root,
            knowledge_links=["[[old-decision]]"],
            knowledge_context_paths=["wiki/old.md"],
        )
        first_exporter.export_program(_make_program(), role="candidate")
        bridge_path = root / "knowledge_bridge.md"
        assert "[[old-decision]]" in bridge_path.read_text(encoding="utf-8")

        second_exporter = EvolvedCodeGraphExporter(
            root=root,
            knowledge_links=["[[new-decision]]"],
            knowledge_context_paths=["wiki/new.md"],
        )
        second_exporter.export_program(
            _make_program(fitness=2.0),
            role="candidate",
            became_best=True,
        )

        bridge = bridge_path.read_text(encoding="utf-8")
        assert "[[new-decision]]" in bridge
        assert "wiki/new.md" in bridge
        assert "[[old-decision]]" not in bridge

    def test_export_sanitizes_non_finite_metadata_numbers(self, tmp_path: Path):
        """Tests that metadata and manifest remain strict finite JSON."""
        exporter = EvolvedCodeGraphExporter(root=tmp_path / "corpus")
        program: Program = _make_program(fitness=math.nan)

        record = exporter.export_program(program, role="candidate")

        assert record is not None
        metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
        assert metadata["fitness"] == 1.0e30
        assert metadata["eval_metrics"]["fitness"] == 1.0e30
        manifest_line = record.manifest_path.read_text(encoding="utf-8").splitlines()[0]
        manifest = json.loads(manifest_line)
        assert manifest["fitness"] == 1.0e30
        assert "nan" not in record.candidate_path.read_text(encoding="utf-8").lower()

    def test_export_records_prompt_fallback(self, tmp_path: Path):
        """Tests that resume prompt fallback is explicit in Graphify metadata."""
        exporter = EvolvedCodeGraphExporter(root=tmp_path / "corpus")
        program: Program = _make_program()
        program.prompt_id = None
        program.original_prompt_id = None
        program.resolved_prompt_id = "fallback-prompt"
        program.prompt_fallback_used = True
        prompt: Program = Program(id="fallback-prompt", code="prompt", language="text")

        record = exporter.export_program(program, role="checkpoint_best", prompt=prompt)

        assert record is not None
        metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
        assert metadata["original_prompt_id"] is None
        assert metadata["resolved_prompt_id"] == "fallback-prompt"
        assert metadata["prompt_fallback_used"] is True
        card = record.candidate_path.read_text(encoding="utf-8")
        assert "Original prompt id: `None`" in card
        assert "Resolved prompt id: `fallback-prompt`" in card
        assert "Prompt fallback used: `True`" in card

    def test_export_records_knowledge_gate_receipt(self, tmp_path: Path):
        """Tests that Graphify metadata links candidates to the evidence gate."""
        concept_id = "decisions/require-kg-interaction-for-wrf-physics-changes"
        gate_receipt: Dict[str, Any] = {
            "gate_passed": 1,
            "domain": "wrf_single_physics",
            "manifest_sha256": "manifest-sha",
            "wrf_target": {
                "wrf_commit": "abcdef123456",
                "physics_family": "microphysics",
                "scheme_module": "phys/module_mp_thompson.F",
            },
            "kg_decision_ids": ["require-kg-interaction-for-wrf-physics-changes"],
            "kg_context_paths": [
                "wiki/decisions/require-kg-interaction-for-wrf-physics-changes.md"
            ],
            "required_decision_concept_ids": [concept_id],
            "required_decision_concepts_by_id": {
                "require-kg-interaction-for-wrf-physics-changes": [concept_id]
            },
            "fixture_summary": {"train_cases": 1, "holdout_cases": 1},
            "okf_bundle_root": "wiki",
            "knowledge_context_sha256": "context-sha",
            "knowledge_context_receipts": [
                {
                    "source": (
                        "wiki/decisions/" "require-kg-interaction-for-wrf-physics-changes.md"
                    ),
                    "okf_concept_id": concept_id,
                    "okf_type": "Decision",
                    "okf_title": "Require KG Interaction",
                    "sha256": "source-sha",
                    "chars": 12,
                }
            ],
        }
        exporter = EvolvedCodeGraphExporter(
            root=tmp_path / "corpus",
            knowledge_gate_receipt=gate_receipt,
            knowledge_gate_receipt_path=str(tmp_path / "knowledge_gate" / "receipt.json"),
            knowledge_gate_receipt_sha256="receipt-sha",
        )
        model_msg = "\n".join(
            [
                "KNOWLEDGE USE:",
                f"- {concept_id}: symbol=f; diff=SEARCH_REPLACE_1; reason=preserves the WRF semantic-change decision.",
                "<<<<<<< SEARCH",
                "old",
                "=======",
                "new",
                ">>>>>>> REPLACE",
            ]
        )

        record = exporter.export_program(
            _make_program(
                language="fortran",
                model_msg=model_msg,
                eval_metrics={
                    "correct": 1,
                    "acceptance_policy_passed": 1,
                    "semantic_gate_passed": 1,
                    "max_abs_error": 0.0,
                    "max_rel_error": 0.0,
                },
            ),
            role="candidate",
        )

        assert record is not None
        metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
        assert metadata["knowledge_gate"]["domain"] == "wrf_single_physics"
        assert metadata["knowledge_gate_receipt_sha256"] == "receipt-sha"
        assert metadata["evidence_manifest_sha256"] == "manifest-sha"
        assert metadata["wrf_commit"] == "abcdef123456"
        assert metadata["wrf_target"]["scheme_module"] == "phys/module_mp_thompson.F"
        assert metadata["kg_decision_ids"] == ["require-kg-interaction-for-wrf-physics-changes"]
        assert metadata["required_decision_concept_ids"] == [concept_id]
        assert metadata["fixture_summary"]["holdout_cases"] == 1
        assert metadata["knowledge_context_sha256"] == "context-sha"
        assert metadata["knowledge_context_receipts"][0]["okf_concept_id"] == concept_id
        knowledge_use = metadata["knowledge_use"]
        assert knowledge_use["knowledge_use_schema_version"] == 2
        assert knowledge_use["okf_bundle"]["root"] == "wiki"
        assert knowledge_use["context_available"][0]["concept_id"] == concept_id
        assert knowledge_use["context_declared_used"][0]["concept_id"] == concept_id
        assert knowledge_use["context_declared_traceability"][0]["concept_id"] == concept_id
        assert (
            knowledge_use["context_declared_traceability"][0]["evidence_traceability_required"] == 1
        )
        assert knowledge_use["context_declared_traceability"][0]["traceability_present"] == 1
        evidence_validation = knowledge_use["context_declared_traceability"][0][
            "evidence_validation"
        ]
        assert evidence_validation["validated_evidence_fields"] == ["diff"]
        assert evidence_validation["invalid_evidence"] == []
        assert knowledge_use["declared_traceability_passed"] == 1
        assert knowledge_use["declaration_present"] == 1
        assert knowledge_use["policy_evidence"]["required_decision_concept_ids"] == [concept_id]
        assert knowledge_use["policy_evidence"]["acceptance_policy_passed"] == 1.0
        assert knowledge_use["policy_evidence"]["semantic_gate_reported"] == 1.0
        assert knowledge_use["assessment"]["usage_assessment_kind"] == "declared_self_report"
        assert knowledge_use["assessment"]["assessment_status"] == "declared_usage"
        assert knowledge_use["assessment"]["declared_usage_score"] == 1.0
        assert knowledge_use["assessment"]["declared_traceability_score"] == 1.0
        assert knowledge_use["assessment"]["declared_traceability_passed"] == 1
        assert knowledge_use["assessment"]["verified_usage_available"] == 0.0
        assert knowledge_use["assessment"]["verified_usage_score"] == 0.0
        assert knowledge_use["assessment"]["gate_alignment_score"] == 1.0
        assert knowledge_use["assessment"]["overall_declared_use_score"] == 1.0
        assert knowledge_use["assessment"]["overall_knowledge_use_score"] is None
        assert (
            knowledge_use["assessment"]["overall_knowledge_use_score_kind"]
            == "deprecated_alias_removed_use_overall_declared_use_score"
        )
        card = record.candidate_path.read_text(encoding="utf-8")
        assert "## Knowledge Gate" in card
        assert "## Knowledge Use Receipt" in card
        assert "receipt-sha" in card
        assert "context-sha" in card
        assert "abcdef123456" in card
        assert concept_id in card

    def test_export_marks_missing_required_decision_declaration(self, tmp_path: Path):
        """Tests that Graphify mirrors required-decision declaration policy."""
        required_concept_id = "decisions/require-kg-interaction-for-wrf-physics-changes"
        support_concept_id = "concepts/thompson-microphysics-background"
        gate_receipt: Dict[str, Any] = {
            "gate_passed": 1,
            "domain": "wrf_single_physics",
            "okf_bundle_root": "wiki",
            "kg_decision_ids": ["require-kg-interaction-for-wrf-physics-changes"],
            "kg_context_paths": [
                "wiki/decisions/require-kg-interaction-for-wrf-physics-changes.md"
            ],
            "required_decision_concept_ids": [required_concept_id],
            "required_decision_concepts_by_id": {
                "require-kg-interaction-for-wrf-physics-changes": [required_concept_id]
            },
            "knowledge_context_receipts": [
                {
                    "source": (
                        "wiki/decisions/" "require-kg-interaction-for-wrf-physics-changes.md"
                    ),
                    "okf_concept_id": required_concept_id,
                    "okf_type": "Decision",
                    "okf_title": "Require KG Interaction",
                    "sha256": "source-sha-1",
                    "chars": 12,
                },
                {
                    "source": "wiki/concepts/thompson-microphysics-background.md",
                    "okf_concept_id": support_concept_id,
                    "okf_type": "Concept",
                    "okf_title": "Thompson Microphysics Background",
                    "sha256": "source-sha-2",
                    "chars": 12,
                },
            ],
        }
        exporter = EvolvedCodeGraphExporter(
            root=tmp_path / "corpus",
            knowledge_gate_receipt=gate_receipt,
        )
        model_msg = "\n".join(
            [
                "KNOWLEDGE USE:",
                f"- {support_concept_id}: diff=SEARCH_REPLACE_1; reason=uses background context.",
                "<<<<<<< SEARCH",
                "old",
                "=======",
                "new",
                ">>>>>>> REPLACE",
            ]
        )

        record = exporter.export_program(
            _make_program(language="fortran", model_msg=model_msg),
            role="candidate",
        )

        assert record is not None
        metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
        knowledge_use = metadata["knowledge_use"]
        required_status = knowledge_use["policy_evidence"]["required_decision_declarations"]
        assert required_status["passed"] == 0
        assert required_status["missing_declared_decision_ids"] == [
            "require-kg-interaction-for-wrf-physics-changes"
        ]
        assert knowledge_use["declared_required_decision_passed"] == 0
        assert (
            knowledge_use["assessment"]["assessment_status"]
            == "declared_usage_missing_required_decision"
        )
        assert knowledge_use["assessment"]["declared_required_decision_score"] == 0.0

    def test_export_rejects_required_decision_concept_with_wrong_okf_type(self, tmp_path: Path):
        """Tests that Graphify does not trust required-decision ids without type: Decision."""
        concept_id = "decisions/require-kg-interaction-for-wrf-physics-changes"
        gate_receipt: Dict[str, Any] = {
            "gate_passed": 1,
            "domain": "wrf_single_physics",
            "okf_bundle_root": "wiki",
            "kg_decision_ids": ["require-kg-interaction-for-wrf-physics-changes"],
            "kg_context_paths": [
                "wiki/decisions/require-kg-interaction-for-wrf-physics-changes.md"
            ],
            "required_decision_concept_ids": [concept_id],
            "required_decision_concepts_by_id": {
                "require-kg-interaction-for-wrf-physics-changes": [concept_id]
            },
            "knowledge_context_receipts": [
                {
                    "source": (
                        "wiki/decisions/" "require-kg-interaction-for-wrf-physics-changes.md"
                    ),
                    "okf_concept_id": concept_id,
                    "okf_type": "Concept",
                    "okf_title": "Wrong Type",
                    "sha256": "source-sha",
                    "chars": 12,
                }
            ],
        }
        exporter = EvolvedCodeGraphExporter(
            root=tmp_path / "corpus",
            knowledge_gate_receipt=gate_receipt,
        )
        model_msg = "\n".join(
            [
                "KNOWLEDGE USE:",
                f"- {concept_id}: diff=SEARCH_REPLACE_1; reason=claims the configured decision.",
                "<<<<<<< SEARCH",
                "old",
                "=======",
                "new",
                ">>>>>>> REPLACE",
            ]
        )

        record = exporter.export_program(
            _make_program(language="fortran", model_msg=model_msg),
            role="candidate",
        )

        assert record is not None
        metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
        knowledge_use = metadata["knowledge_use"]
        required_status = knowledge_use["policy_evidence"]["required_decision_declarations"]
        assert required_status["passed"] == 0
        assert required_status["unavailable_decision_ids"] == [
            "require-kg-interaction-for-wrf-physics-changes"
        ]
        assert required_status["missing_declared_decision_ids"] == []
        assert knowledge_use["declared_required_decision_passed"] == 0
        assert (
            knowledge_use["assessment"]["assessment_status"]
            == "declared_usage_missing_required_decision"
        )

    def test_export_marks_unstructured_declared_knowledge_use(self, tmp_path: Path):
        """Tests that weak declarations are not treated as structured OKF use."""
        concept_id = "decisions/require-kg-interaction-for-wrf-physics-changes"
        gate_receipt: Dict[str, Any] = {
            "gate_passed": 1,
            "domain": "wrf_single_physics",
            "okf_bundle_root": "wiki",
            "knowledge_context_receipts": [
                {
                    "source": (
                        "wiki/decisions/" "require-kg-interaction-for-wrf-physics-changes.md"
                    ),
                    "okf_concept_id": concept_id,
                    "okf_type": "Decision",
                    "okf_title": "Require KG Interaction",
                    "sha256": "source-sha",
                    "chars": 12,
                }
            ],
        }
        exporter = EvolvedCodeGraphExporter(
            root=tmp_path / "corpus",
            knowledge_gate_receipt=gate_receipt,
        )
        model_msg = "\n".join(
            [
                "KNOWLEDGE USE:",
                f"- {concept_id}: reason=; symbol=;",
                "<<<<<<< SEARCH",
                "old",
                "=======",
                "new",
                ">>>>>>> REPLACE",
            ]
        )

        record = exporter.export_program(
            _make_program(language="fortran", model_msg=model_msg),
            role="candidate",
        )

        assert record is not None
        metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
        knowledge_use = metadata["knowledge_use"]
        assert knowledge_use["context_declared_used"][0]["concept_id"] == concept_id
        assert knowledge_use["context_declared_traceability"][0]["traceability_present"] == 0
        assert knowledge_use["context_declared_traceability"][0]["missing"] == [
            "reason",
            "traceability_field",
        ]
        assert (
            "missing reason, traceability_field"
            in knowledge_use["context_declared_traceability"][0]["rejection"]
        )
        assert (
            "missing evidence_traceability_field"
            in knowledge_use["context_declared_traceability"][0]["rejection"]
        )
        assert knowledge_use["declared_traceability_passed"] == 0
        assert knowledge_use["assessment"]["assessment_status"] == "declared_usage_unstructured"
        assert knowledge_use["assessment"]["declared_usage_score"] == 1.0
        assert knowledge_use["assessment"]["declared_traceability_score"] == 0.0
        assert knowledge_use["assessment"]["overall_declared_use_score"] == 0.5

    def test_export_uses_code_aware_traceability_for_declared_symbols(self, tmp_path: Path):
        """Tests that Graphify uses the same symbol traceability check as the gate."""
        concept_id = "decisions/require-kg-interaction-for-wrf-physics-changes"
        gate_receipt: Dict[str, Any] = {
            "gate_passed": 1,
            "domain": "wrf_single_physics",
            "okf_bundle_root": "wiki",
            "knowledge_context_receipts": [
                {
                    "source": (
                        "wiki/decisions/" "require-kg-interaction-for-wrf-physics-changes.md"
                    ),
                    "okf_concept_id": concept_id,
                    "okf_type": "Decision",
                    "okf_title": "Require KG Interaction",
                    "sha256": "source-sha",
                    "chars": 12,
                }
            ],
        }
        exporter = EvolvedCodeGraphExporter(
            root=tmp_path / "corpus",
            knowledge_gate_receipt=gate_receipt,
        )
        model_msg = "\n".join(
            [
                "KNOWLEDGE USE:",
                f"- {concept_id}: symbol=missing_kernel; reason=preserves decision.",
                "<<<<<<< SEARCH",
                "old",
                "=======",
                "new",
                ">>>>>>> REPLACE",
            ]
        )

        record = exporter.export_program(
            _make_program(
                code="subroutine kernel()\nend subroutine kernel\n",
                language="fortran",
                model_msg=model_msg,
            ),
            role="candidate",
        )

        assert record is not None
        metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
        knowledge_use = metadata["knowledge_use"]
        traceability = knowledge_use["context_declared_traceability"][0]
        assert traceability["traceability_present"] == 0
        assert traceability["missing"] == []
        assert "not present in candidate code" in traceability["rejection"]
        assert "missing evidence_traceability_field" in traceability["rejection"]
        assert knowledge_use["declared_traceability_passed"] == 0
        assert knowledge_use["assessment"]["assessment_status"] == "declared_usage_unstructured"

    def test_export_requires_evidence_traceability_for_wrf(self, tmp_path: Path):
        """Tests that symbol-only WRF declarations are not treated as structured use."""
        concept_id = "decisions/require-kg-interaction-for-wrf-physics-changes"
        gate_receipt: Dict[str, Any] = {
            "gate_passed": 1,
            "domain": "wrf_single_physics",
            "okf_bundle_root": "wiki",
            "knowledge_context_receipts": [
                {
                    "source": (
                        "wiki/decisions/" "require-kg-interaction-for-wrf-physics-changes.md"
                    ),
                    "okf_concept_id": concept_id,
                    "okf_type": "Decision",
                    "okf_title": "Require KG Interaction",
                    "sha256": "source-sha",
                    "chars": 12,
                }
            ],
        }
        exporter = EvolvedCodeGraphExporter(
            root=tmp_path / "corpus",
            knowledge_gate_receipt=gate_receipt,
        )
        model_msg = "\n".join(
            [
                "KNOWLEDGE USE:",
                f"- {concept_id}: symbol=kernel; reason=preserves decision.",
                "<<<<<<< SEARCH",
                "old",
                "=======",
                "new",
                ">>>>>>> REPLACE",
            ]
        )

        record = exporter.export_program(
            _make_program(
                code="subroutine kernel()\nend subroutine kernel\n",
                language="fortran",
                model_msg=model_msg,
            ),
            role="candidate",
        )

        assert record is not None
        metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
        traceability = metadata["knowledge_use"]["context_declared_traceability"][0]
        assert traceability["traceability_present"] == 0
        assert traceability["evidence_traceability_required"] == 1
        assert "missing evidence_traceability_field" in traceability["rejection"]

    def test_export_rejects_unknown_diff_reference(self, tmp_path: Path):
        """Tests that Graphify does not mark fake diff references as traceable."""
        concept_id = "decisions/require-kg-interaction-for-wrf-physics-changes"
        gate_receipt: Dict[str, Any] = {
            "gate_passed": 1,
            "domain": "wrf_single_physics",
            "okf_bundle_root": "wiki",
            "knowledge_context_receipts": [
                {
                    "source": (
                        "wiki/decisions/" "require-kg-interaction-for-wrf-physics-changes.md"
                    ),
                    "okf_concept_id": concept_id,
                    "okf_type": "Decision",
                    "okf_title": "Require KG Interaction",
                    "sha256": "source-sha",
                    "chars": 12,
                }
            ],
        }
        exporter = EvolvedCodeGraphExporter(
            root=tmp_path / "corpus",
            knowledge_gate_receipt=gate_receipt,
        )
        model_msg = "\n".join(
            [
                "KNOWLEDGE USE:",
                f"- {concept_id}: symbol=kernel; diff=SEARCH_REPLACE_3; reason=preserves decision.",
                "<<<<<<< SEARCH",
                "old",
                "=======",
                "new",
                ">>>>>>> REPLACE",
            ]
        )

        record = exporter.export_program(
            _make_program(
                code="subroutine kernel()\nend subroutine kernel\n",
                language="fortran",
                model_msg=model_msg,
            ),
            role="candidate",
        )

        assert record is not None
        metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
        traceability = metadata["knowledge_use"]["context_declared_traceability"][0]
        assert traceability["traceability_present"] == 0
        assert "SEARCH/REPLACE block 3" in traceability["rejection"]
        assert traceability["evidence_validation"]["validated_evidence_fields"] == []

    def test_export_validates_declared_metric_against_eval_metrics(self, tmp_path: Path):
        """Tests that metric declarations must reference actual evaluator metrics."""
        concept_id = "decisions/require-kg-interaction-for-wrf-physics-changes"
        gate_receipt: Dict[str, Any] = {
            "gate_passed": 1,
            "domain": "wrf_single_physics",
            "okf_bundle_root": "wiki",
            "knowledge_context_receipts": [
                {
                    "source": (
                        "wiki/decisions/" "require-kg-interaction-for-wrf-physics-changes.md"
                    ),
                    "okf_concept_id": concept_id,
                    "okf_type": "Decision",
                    "okf_title": "Require KG Interaction",
                    "sha256": "source-sha",
                    "chars": 12,
                }
            ],
        }
        exporter = EvolvedCodeGraphExporter(
            root=tmp_path / "corpus",
            knowledge_gate_receipt=gate_receipt,
        )
        valid_msg = "\n".join(
            [
                "KNOWLEDGE USE:",
                f"- {concept_id}: symbol=kernel; metric=max_abs_error; reason=preserves decision.",
                "<<<<<<< SEARCH",
                "old",
                "=======",
                "new",
                ">>>>>>> REPLACE",
            ]
        )
        invalid_msg = valid_msg.replace("max_abs_error", "missing_metric")

        valid_record = exporter.export_program(
            _make_program(
                code="subroutine kernel()\nend subroutine kernel\n",
                language="fortran",
                model_msg=valid_msg,
                eval_metrics={"max_abs_error": 0.0},
            ),
            role="candidate",
        )
        assert valid_record is not None
        valid_metadata = json.loads(valid_record.metadata_path.read_text(encoding="utf-8"))
        invalid_record = exporter.export_program(
            _make_program(
                code="subroutine kernel()\nend subroutine kernel\n",
                language="fortran",
                model_msg=invalid_msg,
                eval_metrics={"max_abs_error": 0.0},
            ),
            role="candidate",
        )

        valid_traceability = valid_metadata["knowledge_use"]["context_declared_traceability"][0]
        assert valid_traceability["traceability_present"] == 1
        assert valid_traceability["evidence_validation"]["validated_evidence_fields"] == ["metric"]

        assert invalid_record is not None
        invalid_metadata = json.loads(invalid_record.metadata_path.read_text(encoding="utf-8"))
        invalid_traceability = invalid_metadata["knowledge_use"]["context_declared_traceability"][0]
        assert invalid_traceability["traceability_present"] == 0
        assert "missing_metric" in invalid_traceability["rejection"]

    def test_export_rejects_placeholder_traceability_values(self, tmp_path: Path):
        """Tests that Graphify does not score placeholder reason fields as structured."""
        concept_id = "decisions/require-kg-interaction-for-wrf-physics-changes"
        gate_receipt: Dict[str, Any] = {
            "gate_passed": 1,
            "domain": "wrf_single_physics",
            "okf_bundle_root": "wiki",
            "knowledge_context_receipts": [
                {
                    "source": (
                        "wiki/decisions/" "require-kg-interaction-for-wrf-physics-changes.md"
                    ),
                    "okf_concept_id": concept_id,
                    "okf_type": "Decision",
                    "okf_title": "Require KG Interaction",
                    "sha256": "source-sha",
                    "chars": 12,
                }
            ],
        }
        exporter = EvolvedCodeGraphExporter(
            root=tmp_path / "corpus",
            knowledge_gate_receipt=gate_receipt,
        )
        model_msg = "\n".join(
            [
                "KNOWLEDGE USE:",
                f"- {concept_id}: symbol=kernel; reason=n/a.",
                "<<<<<<< SEARCH",
                "old",
                "=======",
                "new",
                ">>>>>>> REPLACE",
            ]
        )

        record = exporter.export_program(
            _make_program(
                code="subroutine kernel()\nend subroutine kernel\n",
                language="fortran",
                model_msg=model_msg,
            ),
            role="candidate",
        )

        assert record is not None
        metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
        traceability = metadata["knowledge_use"]["context_declared_traceability"][0]
        assert traceability["traceability_present"] == 0
        assert traceability["placeholder_fields"] == ["reason"]
        assert "placeholder reason" in traceability["rejection"]

    def test_export_does_not_treat_acceptance_policy_as_semantic_gate(self, tmp_path: Path):
        """Tests that Graphify does not infer semantic validation from policy acceptance."""
        concept_id = "decisions/require-kg-interaction-for-wrf-physics-changes"
        gate_receipt: Dict[str, Any] = {
            "gate_passed": 1,
            "domain": "wrf_single_physics",
            "okf_bundle_root": "wiki",
            "knowledge_context_receipts": [
                {
                    "source": (
                        "wiki/decisions/" "require-kg-interaction-for-wrf-physics-changes.md"
                    ),
                    "okf_concept_id": concept_id,
                    "okf_type": "Decision",
                    "okf_title": "Require KG Interaction",
                    "sha256": "source-sha",
                    "chars": 12,
                }
            ],
        }
        exporter = EvolvedCodeGraphExporter(
            root=tmp_path / "corpus",
            knowledge_gate_receipt=gate_receipt,
        )
        model_msg = "\n".join(
            [
                "KNOWLEDGE USE:",
                f"- {concept_id}: symbol=f; diff=SEARCH_REPLACE_1; reason=preserves the configured decision.",
                "<<<<<<< SEARCH",
                "old",
                "=======",
                "new",
                ">>>>>>> REPLACE",
            ]
        )

        record = exporter.export_program(
            _make_program(
                language="fortran",
                model_msg=model_msg,
                eval_metrics={"acceptance_policy_passed": 1},
            ),
            role="candidate",
        )

        assert record is not None
        metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
        knowledge_use = metadata["knowledge_use"]
        assert knowledge_use["policy_evidence"]["acceptance_policy_passed"] == 1.0
        assert knowledge_use["policy_evidence"]["semantic_gate_reported"] == 0.0
        assert knowledge_use["assessment"]["gate_alignment_score"] == 0.0
        assert knowledge_use["assessment"]["declared_traceability_score"] == 1.0
        assert knowledge_use["assessment"]["overall_declared_use_score"] == 0.75
        assert knowledge_use["assessment"]["overall_knowledge_use_score"] is None

    def test_export_does_not_infer_knowledge_use_without_declaration(self, tmp_path: Path):
        """Tests that OKF exposure alone is not counted as model knowledge use."""
        concept_id = "decisions/require-kg-interaction-for-wrf-physics-changes"
        gate_receipt: Dict[str, Any] = {
            "gate_passed": 1,
            "domain": "wrf_single_physics",
            "okf_bundle_root": "wiki",
            "knowledge_context_sha256": "context-sha",
            "knowledge_context_receipts": [
                {
                    "source": (
                        "wiki/decisions/" "require-kg-interaction-for-wrf-physics-changes.md"
                    ),
                    "okf_concept_id": concept_id,
                    "okf_type": "Decision",
                    "okf_title": "Require KG Interaction",
                    "sha256": "source-sha",
                    "chars": 12,
                }
            ],
        }
        exporter = EvolvedCodeGraphExporter(
            root=tmp_path / "corpus",
            knowledge_gate_receipt=gate_receipt,
        )
        model_msg = "\n".join(
            [
                "<<<<<<< SEARCH",
                f"! incidental mention of {concept_id}",
                "=======",
                "! code only",
                ">>>>>>> REPLACE",
            ]
        )

        record = exporter.export_program(
            _make_program(
                language="fortran",
                model_msg=model_msg,
                eval_metrics={"semantic_gate_passed": 1},
            ),
            role="candidate",
        )

        assert record is not None
        metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
        knowledge_use = metadata["knowledge_use"]
        assert knowledge_use["context_available"][0]["concept_id"] == concept_id
        assert knowledge_use["context_declared_used"] == []
        assert knowledge_use["declaration_present"] == 0
        assert knowledge_use["assessment"]["assessment_status"] == "no_declared_usage"

    def test_export_requires_exact_declared_concept_id(self, tmp_path: Path):
        """Tests that declared OKF usage does not use substring matches."""
        concept_id = "decisions/require-kg-interaction-for-wrf-physics-changes"
        gate_receipt: Dict[str, Any] = {
            "gate_passed": 1,
            "domain": "wrf_single_physics",
            "okf_bundle_root": "wiki",
            "knowledge_context_receipts": [
                {
                    "source": (
                        "wiki/decisions/" "require-kg-interaction-for-wrf-physics-changes.md"
                    ),
                    "okf_concept_id": concept_id,
                    "okf_type": "Decision",
                    "okf_title": "Require KG Interaction",
                    "sha256": "source-sha",
                    "chars": 12,
                }
            ],
        }
        exporter = EvolvedCodeGraphExporter(
            root=tmp_path / "corpus",
            knowledge_gate_receipt=gate_receipt,
        )
        model_msg = "\n".join(
            [
                "KNOWLEDGE USE:",
                f"- {concept_id}-draft: mentions an adjacent but different concept.",
                "<<<<<<< SEARCH",
                "old",
                "=======",
                "new",
                ">>>>>>> REPLACE",
            ]
        )

        record = exporter.export_program(
            _make_program(language="fortran", model_msg=model_msg),
            role="candidate",
        )

        assert record is not None
        metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
        knowledge_use = metadata["knowledge_use"]
        assert knowledge_use["context_declared_used"] == []
        assert knowledge_use["declaration_present"] == 1
        assert knowledge_use["assessment"]["assessment_status"] == "declared_usage_unmatched"

    def test_export_requires_concept_id_at_start_of_usage_line(self, tmp_path: Path):
        """Tests that incidental concept mentions inside prose are not declarations."""
        concept_id = "decisions/require-kg-interaction-for-wrf-physics-changes"
        gate_receipt: Dict[str, Any] = {
            "gate_passed": 1,
            "domain": "wrf_single_physics",
            "okf_bundle_root": "wiki",
            "knowledge_context_receipts": [
                {
                    "source": (
                        "wiki/decisions/" "require-kg-interaction-for-wrf-physics-changes.md"
                    ),
                    "okf_concept_id": concept_id,
                    "okf_type": "Decision",
                    "okf_title": "Require KG Interaction",
                    "sha256": "source-sha",
                    "chars": 12,
                }
            ],
        }
        exporter = EvolvedCodeGraphExporter(
            root=tmp_path / "corpus",
            knowledge_gate_receipt=gate_receipt,
        )
        model_msg = "\n".join(
            [
                "KNOWLEDGE USE:",
                f"- I used {concept_id}: diff=SEARCH_REPLACE_1; reason=claimed but unstructured.",
                "<<<<<<< SEARCH",
                "old",
                "=======",
                "new",
                ">>>>>>> REPLACE",
            ]
        )

        record = exporter.export_program(
            _make_program(language="fortran", model_msg=model_msg),
            role="candidate",
        )

        assert record is not None
        metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
        knowledge_use = metadata["knowledge_use"]
        assert knowledge_use["context_declared_used"] == []
        assert knowledge_use["declaration_present"] == 1
        assert knowledge_use["assessment"]["assessment_status"] == "declared_usage_unmatched"

    def test_export_ignores_knowledge_use_after_first_diff(self, tmp_path: Path):
        """Tests that declarations after SEARCH/REPLACE blocks are not counted."""
        concept_id = "decisions/require-kg-interaction-for-wrf-physics-changes"
        gate_receipt: Dict[str, Any] = {
            "gate_passed": 1,
            "domain": "wrf_single_physics",
            "okf_bundle_root": "wiki",
            "knowledge_context_receipts": [
                {
                    "source": (
                        "wiki/decisions/" "require-kg-interaction-for-wrf-physics-changes.md"
                    ),
                    "okf_concept_id": concept_id,
                    "okf_type": "Decision",
                    "okf_title": "Require KG Interaction",
                    "sha256": "source-sha",
                    "chars": 12,
                }
            ],
        }
        exporter = EvolvedCodeGraphExporter(
            root=tmp_path / "corpus",
            knowledge_gate_receipt=gate_receipt,
        )
        model_msg = "\n".join(
            [
                "<<<<<<< SEARCH",
                "old",
                "=======",
                "new",
                ">>>>>>> REPLACE",
                "KNOWLEDGE USE:",
                f"- {concept_id}: late declaration should not count.",
            ]
        )

        record = exporter.export_program(
            _make_program(language="fortran", model_msg=model_msg),
            role="candidate",
        )

        assert record is not None
        metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
        knowledge_use = metadata["knowledge_use"]
        assert knowledge_use["context_declared_used"] == []
        assert knowledge_use["declaration_present"] == 0
        assert knowledge_use["assessment"]["assessment_status"] == "no_declared_usage"

    def test_positive_mode_skips_zero_fitness(self, tmp_path: Path):
        """Tests that positive mode filters failed candidates."""
        exporter = EvolvedCodeGraphExporter(root=tmp_path / "corpus", mode="positive")

        record = exporter.export_program(_make_program(fitness=0.0), role="candidate")

        assert record is None
        assert not (tmp_path / "corpus").exists()

    def test_invalid_mode_raises(self, tmp_path: Path):
        """Tests that unsupported export modes are rejected."""
        exporter = EvolvedCodeGraphExporter(root=tmp_path / "corpus", mode="bad-mode")

        with pytest.raises(ValueError, match="GRAPHIFY_EXPORT.mode"):
            exporter.export_program(_make_program(), role="candidate")
