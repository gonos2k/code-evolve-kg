# ===--------------------------------------------------------------------------------------===#
#
# Part of the CodeEvolve Project, under the Apache License v2.0.
# See https://github.com/inter-co/science-codeevolve/blob/main/LICENSE for license information.
# SPDX-License-Identifier: Apache-2.0
#
# ===--------------------------------------------------------------------------------------===#
#
# This file implements unit tests for file-based knowledge-gate preflight.
#
# ===--------------------------------------------------------------------------------------===#

import hashlib
import json
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from codeevolve.prompt.knowledge_gate import (
    KnowledgeGateReceipt,
    run_knowledge_gate,
    validate_candidate_acceptance_policy,
    validate_candidate_acceptance_policy_by_kind,
)


def _sha256_text(text: str) -> str:
    """Returns the SHA-256 digest for test text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _prepare_gate_files(tmp_path: Path) -> Path:
    """Creates source, context, and fixture files required by the gate."""
    wrf_root: Path = tmp_path / "WRF"
    phys_dir: Path = wrf_root / "phys"
    phys_dir.mkdir(parents=True)
    (phys_dir / "module_microphysics_driver.F").write_text("driver\n", encoding="utf-8")
    (phys_dir / "module_mp_thompson.F").write_text("scheme\n", encoding="utf-8")

    similar_dir: Path = tmp_path / "evidence" / "similar"
    similar_dir.mkdir(parents=True)
    (similar_dir / "module_mp_thompson.F").write_text("similar code evidence", encoding="utf-8")

    context_path: Path = (
        tmp_path / "wiki" / "decisions" / "require-kg-interaction-for-wrf-physics-changes.md"
    )
    context_path.parent.mkdir(parents=True)
    context_path.write_text(
        "\n".join(
            [
                "---",
                "type: Decision",
                "title: Require KG Interaction",
                "---",
                "# Require KG Interaction",
                "WRF physics changes require KG decisions.",
            ]
        ),
        encoding="utf-8",
    )

    train_path: Path = tmp_path / "input" / "fixtures" / "train" / "case.npz"
    holdout_path: Path = tmp_path / "input" / "fixtures" / "holdout" / "case.npz"
    train_path.parent.mkdir(parents=True)
    holdout_path.parent.mkdir(parents=True)
    train_path.write_bytes(b"train")
    holdout_path.write_bytes(b"holdout")
    return wrf_root


def _make_valid_manifest(tmp_path: Path) -> Dict[str, Any]:
    """Creates a valid WRF single-physics evidence manifest."""
    wrf_root: Path = _prepare_gate_files(tmp_path)
    return {
        "schema_version": 1,
        "target": {
            "wrf_version": "v4.8.0",
            "wrf_commit": "abcdef123456",
            "wrf_source_root": str(wrf_root),
            "physics_family": "microphysics",
            "namelist_option": "mp_physics",
            "namelist_value": 8,
            "scheme_module": "phys/module_mp_thompson.F",
            "driver_module": "phys/module_microphysics_driver.F",
            "entrypoint": "mp_thompson",
        },
        "sources": [
            {
                "id": "wrf-users-guide-physics",
                "kind": "official_doc",
                "url": "https://www2.mmm.ucar.edu/wrf/users/wrf_users_guide/build/html/physics.html",
            },
            {
                "id": "wrf-microphysics-driver",
                "kind": "raw_wrf_code",
                "repo": "https://github.com/wrf-model/WRF",
                "commit": "abcdef123456",
                "path": "phys/module_microphysics_driver.F",
            },
            {
                "id": "wrf-thompson-scheme",
                "kind": "raw_wrf_code",
                "repo": "https://github.com/wrf-model/WRF",
                "commit": "abcdef123456",
                "path": "phys/module_mp_thompson.F",
            },
            {
                "id": "scheme-paper",
                "kind": "literature",
                "doi": "10.0000/example",
                "citation": "Example et al. 2026",
            },
            {
                "id": "similar-microphysics-code",
                "kind": "similar_code",
                "repo": "https://github.com/example/wrf-fork",
                "commit": "123456abcdef",
                "path": "phys/module_mp_thompson.F",
                "local_path": "evidence/similar/module_mp_thompson.F",
                "sha256": _sha256_text("similar code evidence"),
            },
        ],
        "kg": {
            "context_paths": ["wiki/decisions/require-kg-interaction-for-wrf-physics-changes.md"],
            "required_decisions": ["require-kg-interaction-for-wrf-physics-changes"],
        },
        "fixtures": {
            "train": [{"name": "case_train_0001", "path": "input/fixtures/train/case.npz"}],
            "holdout": [{"name": "case_holdout_0001", "path": "input/fixtures/holdout/case.npz"}],
        },
    }


def _write_manifest(tmp_path: Path, manifest: Dict[str, Any]) -> Path:
    """Writes a YAML manifest for tests."""
    manifest_path: Path = tmp_path / "wrf_evidence.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return manifest_path


def _make_config(manifest_path: Path) -> Dict[str, Any]:
    """Creates a valid gate-enabled CodeEvolve config subset."""
    return {
        "KNOWLEDGE_GATE": {
            "enabled": True,
            "domain": "wrf_single_physics",
            "manifest": str(manifest_path),
            "receipt_output": "knowledge_gate/receipt.json",
        },
        "KNOWLEDGE_CONTEXT": {
            "enabled": True,
            "required": True,
            "paths": ["wiki/decisions/require-kg-interaction-for-wrf-physics-changes.md"],
        },
        "GRAPHIFY_EXPORT": {
            "enabled": True,
            "required": True,
            "knowledge_links": ["[[require-kg-interaction-for-wrf-physics-changes]]"],
        },
    }


class TestKnowledgeGate:
    """Test suite for KNOWLEDGE_GATE preflight checks."""

    def test_no_gate_returns_none(self, tmp_path: Path):
        """Tests that omitted KNOWLEDGE_GATE keeps existing behavior unchanged."""
        assert run_knowledge_gate({}, {"out_dir": tmp_path}, [tmp_path]) is None

    def test_valid_wrf_gate_writes_receipt_and_prompt_context(self, tmp_path: Path):
        """Tests that a valid WRF evidence manifest writes an auditable receipt."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        config: Dict[str, Any] = _make_config(manifest_path)

        receipt: KnowledgeGateReceipt = run_knowledge_gate(
            config,
            {"out_dir": tmp_path / "out"},
            [tmp_path],
        )

        assert receipt.output_path == tmp_path / "out" / "knowledge_gate" / "receipt.json"
        assert receipt.output_path.exists()
        receipt_data = json.loads(receipt.output_path.read_text(encoding="utf-8"))
        assert receipt_data["gate_passed"] == 1
        assert receipt_data["domain"] == "wrf_single_physics"
        assert receipt_data["wrf_target"]["wrf_commit"] == "abcdef123456"
        assert receipt_data["source_counts"]["raw_wrf_code"] == 2
        assert len(receipt_data["source_receipts"]) == 5
        raw_receipts = [
            item for item in receipt_data["source_receipts"] if item["kind"] == "raw_wrf_code"
        ]
        assert all("sha256" in item for item in raw_receipts)
        assert receipt_data["fixture_summary"]["train_cases"] == 1
        assert receipt_data["fixture_summary"]["holdout_cases"] == 1
        assert receipt_data["fixture_summary"]["traceable_train_fixture_names"] == [
            "case_train_0001"
        ]
        assert receipt_data["fixture_summary"]["traceable_train_fixture_names_truncated"] == 0
        assert receipt_data["fixture_summary"]["fixture_receipts_sha256"]
        assert receipt_data["fixture_summary"]["cases"]["train"][0]["sha256"]
        assert receipt_data["knowledge_context_sha256"]
        assert receipt_data["knowledge_context_receipts"][0]["sha256"]
        assert receipt_data["okf_required"] == 1
        assert receipt_data["okf_bundle_root"] == "wiki"
        assert (
            receipt_data["knowledge_context_receipts"][0]["okf_concept_id"]
            == "decisions/require-kg-interaction-for-wrf-physics-changes"
        )
        assert receipt_data["required_decision_concept_ids"] == [
            "decisions/require-kg-interaction-for-wrf-physics-changes"
        ]
        assert receipt_data["required_decision_concepts_by_id"] == {
            "require-kg-interaction-for-wrf-physics-changes": [
                "decisions/require-kg-interaction-for-wrf-physics-changes"
            ]
        }
        assert receipt.receipt_sha256
        assert "WRF Knowledge Gate Receipt" in receipt.prompt_context
        assert "abcdef123456" in receipt.prompt_context
        assert "okf_concept_ids" in receipt.prompt_context
        assert "decisions/require-kg-interaction-for-wrf-physics-changes" in receipt.prompt_context
        assert "case_train_0001" in receipt.prompt_context
        assert "case_holdout_0001" not in receipt.prompt_context
        assert "resolved_path" not in receipt.prompt_context

    def test_missing_manifest_fails_fast(self, tmp_path: Path):
        """Tests that enabled gates require an evidence manifest."""
        config: Dict[str, Any] = _make_config(tmp_path / "missing.yaml")

        with pytest.raises(FileNotFoundError, match="manifest not found"):
            run_knowledge_gate(config, {"out_dir": tmp_path / "out"}, [tmp_path])

    def test_optional_missing_manifest_returns_none(self, tmp_path: Path):
        """Tests that explicit optional gates can be skipped when evidence is absent."""
        config: Dict[str, Any] = _make_config(tmp_path / "missing.yaml")
        config["KNOWLEDGE_GATE"]["required"] = False

        assert run_knowledge_gate(config, {"out_dir": tmp_path / "out"}, [tmp_path]) is None

    def test_insufficient_sources_raise(self, tmp_path: Path):
        """Tests that WRF gates require literature and similar-code evidence."""
        manifest: Dict[str, Any] = _make_valid_manifest(tmp_path)
        manifest["sources"] = manifest["sources"][:3]
        manifest_path: Path = _write_manifest(tmp_path, manifest)

        with pytest.raises(ValueError, match="source evidence is insufficient"):
            run_knowledge_gate(
                _make_config(manifest_path), {"out_dir": tmp_path / "out"}, [tmp_path]
            )

    def test_official_doc_url_must_be_http(self, tmp_path: Path):
        """Tests that official documentation sources need auditable http(s) URLs."""
        manifest: Dict[str, Any] = _make_valid_manifest(tmp_path)
        manifest["sources"][0]["url"] = "file:///private/docs/physics.html"
        manifest_path: Path = _write_manifest(tmp_path, manifest)

        with pytest.raises(ValueError, match="official doc .* url"):
            run_knowledge_gate(
                _make_config(manifest_path), {"out_dir": tmp_path / "out"}, [tmp_path]
            )

    def test_literature_doi_must_have_doi_shape(self, tmp_path: Path):
        """Tests that DOI locators are syntax-checked without network resolution."""
        manifest: Dict[str, Any] = _make_valid_manifest(tmp_path)
        manifest["sources"][3]["doi"] = "not-a-doi"
        manifest_path: Path = _write_manifest(tmp_path, manifest)

        with pytest.raises(ValueError, match="literature source .* doi"):
            run_knowledge_gate(
                _make_config(manifest_path), {"out_dir": tmp_path / "out"}, [tmp_path]
            )

    def test_placeholder_target_raises(self, tmp_path: Path):
        """Tests that exact WRF target placeholders are rejected."""
        manifest: Dict[str, Any] = _make_valid_manifest(tmp_path)
        manifest["target"]["wrf_commit"] = "exact-git-sha"
        manifest_path: Path = _write_manifest(tmp_path, manifest)

        with pytest.raises(ValueError, match="placeholder fields"):
            run_knowledge_gate(
                _make_config(manifest_path), {"out_dir": tmp_path / "out"}, [tmp_path]
            )

    def test_missing_required_context_config_raises(self, tmp_path: Path):
        """Tests that WRF gates require configured static KG prompt context."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        config: Dict[str, Any] = _make_config(manifest_path)
        config.pop("KNOWLEDGE_CONTEXT")

        with pytest.raises(ValueError, match="KNOWLEDGE_CONTEXT"):
            run_knowledge_gate(config, {"out_dir": tmp_path / "out"}, [tmp_path])

    def test_missing_graphify_export_config_raises(self, tmp_path: Path):
        """Tests that WRF gates require Graphify export links."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        config: Dict[str, Any] = _make_config(manifest_path)
        config.pop("GRAPHIFY_EXPORT")

        with pytest.raises(ValueError, match="GRAPHIFY_EXPORT"):
            run_knowledge_gate(config, {"out_dir": tmp_path / "out"}, [tmp_path])

    def test_graphify_knowledge_links_reject_local_paths(self, tmp_path: Path):
        """Tests that WRF gate Graphify links cannot expose local paths."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        config: Dict[str, Any] = _make_config(manifest_path)
        config["GRAPHIFY_EXPORT"]["knowledge_links"] = [
            f"[secret]({tmp_path / 'private' / 'kg-secret-case.md'})"
        ]

        with pytest.raises(ValueError, match="absolute local paths"):
            run_knowledge_gate(config, {"out_dir": tmp_path / "out"}, [tmp_path])

    @pytest.mark.parametrize(
        "link",
        [
            "https:///Users/alice/private.md",
            "http://127.0.0.1:8000/internal",
            "https://user:token@example.com/wiki",
            "[safe](wiki/page.md) /workspace/private.md",
            "[[wiki/page|/srv/company/private.md]]",
        ],
    )
    def test_graphify_knowledge_links_reject_export_bypasses(self, tmp_path: Path, link: str):
        """Tests that WRF gate rejects non-exportable Graphify links."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        config: Dict[str, Any] = _make_config(manifest_path)
        config["GRAPHIFY_EXPORT"]["knowledge_links"] = [link]

        with pytest.raises(ValueError, match="GRAPHIFY_EXPORT.knowledge_links"):
            run_knowledge_gate(config, {"out_dir": tmp_path / "out"}, [tmp_path])

    def test_missing_holdout_fixture_raises(self, tmp_path: Path):
        """Tests that WRF gates require train and holdout fixture separation."""
        manifest: Dict[str, Any] = _make_valid_manifest(tmp_path)
        manifest["fixtures"].pop("holdout")
        manifest_path: Path = _write_manifest(tmp_path, manifest)

        with pytest.raises(ValueError, match="train and holdout"):
            run_knowledge_gate(
                _make_config(manifest_path), {"out_dir": tmp_path / "out"}, [tmp_path]
            )

    def test_missing_context_file_raises_before_prompt_sampler(self, tmp_path: Path):
        """Tests that context file existence is checked by the gate itself."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        config: Dict[str, Any] = _make_config(manifest_path)
        config["KNOWLEDGE_CONTEXT"]["paths"] = ["wiki/missing.md"]

        with pytest.raises(FileNotFoundError, match="KNOWLEDGE_CONTEXT"):
            run_knowledge_gate(config, {"out_dir": tmp_path / "out"}, [tmp_path])

    def test_okf_context_receipt_records_type(self, tmp_path: Path):
        """Tests that required OKF context is validated during preflight."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        context_path: Path = (
            tmp_path / "wiki" / "decisions" / "require-kg-interaction-for-wrf-physics-changes.md"
        )
        context_path.write_text(
            "\n".join(
                [
                    "---",
                    "type: Decision",
                    "title: Require KG Interaction",
                    "---",
                    "# Require KG Interaction",
                    "WRF physics changes require KG decisions.",
                ]
            ),
            encoding="utf-8",
        )
        config: Dict[str, Any] = _make_config(manifest_path)
        config["KNOWLEDGE_CONTEXT"]["require_okf"] = True

        receipt: KnowledgeGateReceipt = run_knowledge_gate(
            config,
            {"out_dir": tmp_path / "out"},
            [tmp_path],
        )

        receipt_data = json.loads(receipt.output_path.read_text(encoding="utf-8"))
        context_receipt = receipt_data["knowledge_context_receipts"][0]
        assert receipt_data["okf_bundle_root"] == "wiki"
        assert (
            context_receipt["okf_concept_id"]
            == "decisions/require-kg-interaction-for-wrf-physics-changes"
        )
        assert context_receipt["okf_type"] == "Decision"
        assert context_receipt["okf_title"] == "Require KG Interaction"

    def test_wrf_context_requires_okf_by_default(self, tmp_path: Path):
        """Tests that WRF context validation requires OKF frontmatter by default."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        context_path: Path = (
            tmp_path / "wiki" / "decisions" / "require-kg-interaction-for-wrf-physics-changes.md"
        )
        context_path.write_text("WRF physics changes require KG decisions.\n", encoding="utf-8")
        config: Dict[str, Any] = _make_config(manifest_path)

        with pytest.raises(ValueError, match="missing YAML frontmatter"):
            run_knowledge_gate(config, {"out_dir": tmp_path / "out"}, [tmp_path])

    def test_wrf_okf_context_cannot_be_inline_only(self, tmp_path: Path):
        """Tests that inline context alone cannot satisfy WRF OKF concept receipts."""
        manifest: Dict[str, Any] = _make_valid_manifest(tmp_path)
        manifest["kg"]["context_paths"] = []
        manifest_path: Path = _write_manifest(tmp_path, manifest)
        config: Dict[str, Any] = _make_config(manifest_path)
        config["KNOWLEDGE_CONTEXT"].pop("paths")
        config["KNOWLEDGE_CONTEXT"]["inline"] = ["WRF physics changes require KG decisions."]

        with pytest.raises(ValueError, match="okf_concept_id"):
            run_knowledge_gate(config, {"out_dir": tmp_path / "out"}, [tmp_path])

    def test_wrf_disabling_okf_context_requires_explicit_override(self, tmp_path: Path):
        """Tests that WRF OKF requirements cannot be silently disabled."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        config: Dict[str, Any] = _make_config(manifest_path)
        config["KNOWLEDGE_GATE"]["require_okf_context"] = False

        with pytest.raises(ValueError, match="allow_non_okf_context"):
            run_knowledge_gate(config, {"out_dir": tmp_path / "out"}, [tmp_path])

    def test_wrf_disabling_knowledge_context_requires_explicit_override(self, tmp_path: Path):
        """Tests that WRF runs cannot silently skip all knowledge context."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        config: Dict[str, Any] = _make_config(manifest_path)
        config["KNOWLEDGE_GATE"]["require_knowledge_context"] = False

        with pytest.raises(ValueError, match="allow_non_okf_context"):
            run_knowledge_gate(config, {"out_dir": tmp_path / "out"}, [tmp_path])

    def test_wrf_non_okf_context_override_records_justification(self, tmp_path: Path):
        """Tests that explicit non-OKF WRF runs leave an auditable receipt."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        context_path: Path = (
            tmp_path / "wiki" / "decisions" / "require-kg-interaction-for-wrf-physics-changes.md"
        )
        context_path.write_text(
            "Plain non-OKF context for a generic comparison run.\n",
            encoding="utf-8",
        )
        config: Dict[str, Any] = _make_config(manifest_path)
        config["KNOWLEDGE_GATE"]["require_okf_context"] = False
        config["KNOWLEDGE_GATE"]["allow_non_okf_context"] = True
        config["KNOWLEDGE_GATE"][
            "non_okf_context_justification"
        ] = "Generic comparison run without an OKF bundle."

        receipt: KnowledgeGateReceipt = run_knowledge_gate(
            config,
            {"out_dir": tmp_path / "out"},
            [tmp_path],
        )

        receipt_data = json.loads(receipt.output_path.read_text(encoding="utf-8"))
        assert receipt_data["okf_required"] == 0
        assert receipt_data["non_okf_context_allowed"] == 1
        assert (
            receipt_data["non_okf_context_justification"]
            == "Generic comparison run without an OKF bundle."
        )
        assert "okf_concept_id" not in receipt_data["knowledge_context_receipts"][0]
        assert receipt_data["semantic_change_policy"]["candidate_enforcement"] == [
            "require_configured_kg_decision_ids"
        ]

    def test_wrf_disabled_knowledge_context_override_records_empty_context(self, tmp_path: Path):
        """Tests that explicit non-KG WRF comparison runs remain auditable."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        config: Dict[str, Any] = _make_config(manifest_path)
        config["KNOWLEDGE_GATE"]["require_knowledge_context"] = False
        config["KNOWLEDGE_GATE"]["allow_non_okf_context"] = True
        config["KNOWLEDGE_GATE"][
            "non_okf_context_justification"
        ] = "Generic comparison run without selected KG context."

        receipt: KnowledgeGateReceipt = run_knowledge_gate(
            config,
            {"out_dir": tmp_path / "out"},
            [tmp_path],
        )

        receipt_data = json.loads(receipt.output_path.read_text(encoding="utf-8"))
        assert receipt_data["knowledge_context_receipts"] == []
        assert receipt_data["okf_required"] == 0
        assert receipt_data["non_okf_context_allowed"] == 1
        assert receipt_data["semantic_change_policy"]["candidate_enforcement"] == [
            "require_configured_kg_decision_ids"
        ]

    def test_generic_gate_defaults_to_allow_without_kg_decision(self, tmp_path: Path):
        """Tests that non-WRF gates do not inherit WRF semantic strictness."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        config: Dict[str, Any] = _make_config(manifest_path)
        config["KNOWLEDGE_GATE"]["domain"] = "generic"

        receipt: KnowledgeGateReceipt = run_knowledge_gate(
            config,
            {"out_dir": tmp_path / "out"},
            [tmp_path],
        )

        receipt_data = json.loads(receipt.output_path.read_text(encoding="utf-8"))
        assert receipt_data["semantic_change_policy"] == {
            "default": "allow_without_kg_decision",
            "candidate_enforcement": [],
        }

    def test_required_okf_context_missing_type_raises(self, tmp_path: Path):
        """Tests that OKF context validation rejects missing type frontmatter."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        context_path: Path = (
            tmp_path / "wiki" / "decisions" / "require-kg-interaction-for-wrf-physics-changes.md"
        )
        context_path.write_text(
            "\n".join(
                [
                    "---",
                    "title: Missing Type",
                    "---",
                    "# Missing Type",
                ]
            ),
            encoding="utf-8",
        )
        config: Dict[str, Any] = _make_config(manifest_path)

        with pytest.raises(ValueError, match="frontmatter requires non-empty type"):
            run_knowledge_gate(config, {"out_dir": tmp_path / "out"}, [tmp_path])

    def test_missing_raw_wrf_source_file_raises(self, tmp_path: Path):
        """Tests that raw WRF source paths are verified against wrf_source_root."""
        manifest: Dict[str, Any] = _make_valid_manifest(tmp_path)
        manifest["sources"][1]["path"] = "phys/missing_driver.F"
        manifest_path: Path = _write_manifest(tmp_path, manifest)

        with pytest.raises(FileNotFoundError, match="raw WRF source file"):
            run_knowledge_gate(
                _make_config(manifest_path), {"out_dir": tmp_path / "out"}, [tmp_path]
            )

    def test_raw_wrf_sources_must_include_target_files(self, tmp_path: Path):
        """Tests that raw WRF evidence must cover the selected scheme and driver."""
        manifest: Dict[str, Any] = _make_valid_manifest(tmp_path)
        wrf_root: Path = Path(manifest["target"]["wrf_source_root"])
        (wrf_root / "phys" / "module_other_scheme.F").write_text("other\n", encoding="utf-8")
        manifest["sources"][2]["path"] = "phys/module_other_scheme.F"
        manifest_path: Path = _write_manifest(tmp_path, manifest)

        with pytest.raises(ValueError, match="scheme_module"):
            run_knowledge_gate(
                _make_config(manifest_path), {"out_dir": tmp_path / "out"}, [tmp_path]
            )

    def test_raw_wrf_source_commit_must_match_target(self, tmp_path: Path):
        """Tests that raw WRF code evidence is pinned to the target commit."""
        manifest: Dict[str, Any] = _make_valid_manifest(tmp_path)
        manifest["sources"][1]["commit"] = "123456abcdef"
        manifest_path: Path = _write_manifest(tmp_path, manifest)

        with pytest.raises(ValueError, match="commit must match"):
            run_knowledge_gate(
                _make_config(manifest_path), {"out_dir": tmp_path / "out"}, [tmp_path]
            )

    def test_similar_code_requires_local_snapshot_when_digests_required(self, tmp_path: Path):
        """Tests that similar-code evidence cannot be only a self-attested digest."""
        manifest: Dict[str, Any] = _make_valid_manifest(tmp_path)
        manifest["sources"][4].pop("local_path")
        manifest_path: Path = _write_manifest(tmp_path, manifest)

        with pytest.raises(ValueError, match="requires local_path"):
            run_knowledge_gate(
                _make_config(manifest_path), {"out_dir": tmp_path / "out"}, [tmp_path]
            )

    def test_required_kg_decision_ids_are_mandatory_for_wrf(self, tmp_path: Path):
        """Tests that WRF runs require explicit KG decision records."""
        manifest: Dict[str, Any] = _make_valid_manifest(tmp_path)
        manifest["kg"]["required_decisions"] = []
        manifest_path: Path = _write_manifest(tmp_path, manifest)

        with pytest.raises(ValueError, match="requires kg.required_decisions"):
            run_knowledge_gate(
                _make_config(manifest_path), {"out_dir": tmp_path / "out"}, [tmp_path]
            )

    def test_required_kg_decision_must_be_exposed_as_okf_concept(self, tmp_path: Path):
        """Tests that KG decision links cannot replace exposed OKF decision context."""
        manifest: Dict[str, Any] = _make_valid_manifest(tmp_path)
        unrelated_context: Path = tmp_path / "wiki" / "concepts" / "unrelated.md"
        unrelated_context.parent.mkdir(parents=True, exist_ok=True)
        unrelated_context.write_text(
            "\n".join(
                [
                    "---",
                    "type: Concept",
                    "title: Unrelated Concept",
                    "---",
                    "# Unrelated Concept",
                    "This page is not the required WRF decision.",
                ]
            ),
            encoding="utf-8",
        )
        manifest["kg"]["context_paths"] = ["wiki/concepts/unrelated.md"]
        manifest_path: Path = _write_manifest(tmp_path, manifest)
        config: Dict[str, Any] = _make_config(manifest_path)
        config["KNOWLEDGE_CONTEXT"]["paths"] = ["wiki/concepts/unrelated.md"]
        config["GRAPHIFY_EXPORT"]["knowledge_links"] = [
            "[[require-kg-interaction-for-wrf-physics-changes]]"
        ]

        with pytest.raises(ValueError, match="not exposed as OKF Decision concept ids"):
            run_knowledge_gate(config, {"out_dir": tmp_path / "out"}, [tmp_path])

    def test_required_kg_decision_must_have_decision_type(self, tmp_path: Path):
        """Tests that a matching concept id is not enough without type: Decision."""
        manifest: Dict[str, Any] = _make_valid_manifest(tmp_path)
        context_path: Path = (
            tmp_path / "wiki" / "decisions" / "require-kg-interaction-for-wrf-physics-changes.md"
        )
        context_path.write_text(
            "\n".join(
                [
                    "---",
                    "type: Concept",
                    "title: Same Identifier But Not A Decision",
                    "---",
                    "# Same Identifier But Not A Decision",
                    "This page has the required id but is not a decision record.",
                ]
            ),
            encoding="utf-8",
        )
        manifest_path: Path = _write_manifest(tmp_path, manifest)

        with pytest.raises(ValueError, match="not exposed as OKF Decision concept ids"):
            run_knowledge_gate(
                _make_config(manifest_path), {"out_dir": tmp_path / "out"}, [tmp_path]
            )

    def test_required_kg_decision_must_be_in_manifest_context_paths(self, tmp_path: Path):
        """Tests that extra config context cannot override manifest KG context paths."""
        manifest: Dict[str, Any] = _make_valid_manifest(tmp_path)
        unrelated_context: Path = tmp_path / "wiki" / "decisions" / "unrelated-decision.md"
        unrelated_context.parent.mkdir(parents=True, exist_ok=True)
        unrelated_context.write_text(
            "\n".join(
                [
                    "---",
                    "type: Decision",
                    "title: Unrelated Decision",
                    "---",
                    "# Unrelated Decision",
                    "This is not the required WRF decision.",
                ]
            ),
            encoding="utf-8",
        )
        manifest["kg"]["context_paths"] = ["wiki/decisions/unrelated-decision.md"]
        manifest_path: Path = _write_manifest(tmp_path, manifest)
        config: Dict[str, Any] = _make_config(manifest_path)
        config["KNOWLEDGE_CONTEXT"]["paths"] = [
            "wiki/decisions/unrelated-decision.md",
            "wiki/decisions/require-kg-interaction-for-wrf-physics-changes.md",
        ]

        with pytest.raises(ValueError, match="not exposed as OKF Decision concept ids"):
            run_knowledge_gate(config, {"out_dir": tmp_path / "out"}, [tmp_path])

    def test_train_and_holdout_fixture_paths_must_be_disjoint(self, tmp_path: Path):
        """Tests that visible train and holdout fixtures cannot be the same file."""
        manifest: Dict[str, Any] = _make_valid_manifest(tmp_path)
        manifest["fixtures"]["holdout"][0]["path"] = "input/fixtures/train/case.npz"
        manifest_path: Path = _write_manifest(tmp_path, manifest)

        with pytest.raises(ValueError, match="disjoint"):
            run_knowledge_gate(
                _make_config(manifest_path), {"out_dir": tmp_path / "out"}, [tmp_path]
            )

    def test_static_policy_scans_evolve_block_and_strips_fortran_comments(self):
        """Tests that static scans avoid fixed code, comments, and strings."""
        receipt: Dict[str, Any] = {
            "static_policy": {
                "enabled": True,
                "forbidden_patterns": {
                    "execute_command_line": r"\bexecute_command_line\b",
                },
                "scan_scope": "evolve_block",
                "strip_fortran_comments": True,
                "evolve_start_marker": "! EVOLVE-BLOCK-START",
                "evolve_end_marker": "! EVOLVE-BLOCK-END",
            },
            "semantic_change_policy": {"default": "allow_without_kg_decision"},
        }
        code: str = "\n".join(
            [
                "subroutine helper()",
                "  call execute_command_line('outside fixed block')",
                "end subroutine helper",
                "! EVOLVE-BLOCK-START",
                "subroutine kernel()",
                "  ! call execute_command_line('comment only')",
                "  print *, 'execute_command_line in string only'",
                "end subroutine kernel",
                "! EVOLVE-BLOCK-END",
            ]
        )

        assert validate_candidate_acceptance_policy(code, receipt) == []

    def test_candidate_acceptance_policy_reports_rejection_kinds(self):
        """Tests that static and KG-decision rejections remain distinguishable."""
        receipt: Dict[str, Any] = {
            "static_policy": {
                "enabled": True,
                "forbidden_patterns": {
                    "execute_command_line": r"\bexecute_command_line\b",
                },
                "scan_scope": "whole_file",
            },
            "semantic_change_policy": {"default": "reject_without_kg_decision"},
            "kg_decision_ids": [],
            "required_decisions_present": 0,
        }
        code: str = "subroutine kernel()\n  call execute_command_line('date')\nend\n"

        rejections = validate_candidate_acceptance_policy_by_kind(code, receipt)

        assert len(rejections["static"]) == 1
        assert len(rejections["knowledge"]) == 1

    def test_candidate_acceptance_policy_requires_declared_okf_use(self):
        """Tests that configured KG decisions do not replace candidate-level OKF use."""
        concept_id: str = "decisions/require-kg-interaction-for-wrf-physics-changes"
        receipt: Dict[str, Any] = {
            "static_policy": {"enabled": False},
            "semantic_change_policy": {
                "default": "reject_without_kg_decision",
                "candidate_enforcement": [
                    "require_configured_kg_decision_ids",
                    "require_declared_okf_concept_use",
                ],
            },
            "kg_decision_ids": ["require-kg-interaction-for-wrf-physics-changes"],
            "required_decisions_present": 1,
            "kg_context_paths": [
                "wiki/decisions/require-kg-interaction-for-wrf-physics-changes.md"
            ],
            "required_decision_concepts_by_id": {
                "require-kg-interaction-for-wrf-physics-changes": [concept_id]
            },
            "required_decision_concept_ids": [concept_id],
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
        code: str = "subroutine kernel()\nend\n"

        rejected = validate_candidate_acceptance_policy_by_kind(
            code,
            receipt,
            model_msg="<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE",
            require_model_msg_knowledge_use=True,
        )

        assert rejected["static"] == []
        assert len(rejected["knowledge"]) == 1
        assert "KNOWLEDGE USE" in rejected["knowledge"][0]

        accepted = validate_candidate_acceptance_policy_by_kind(
            code,
            receipt,
            model_msg="\n".join(
                [
                    "KNOWLEDGE USE:",
                    f"- {concept_id}: symbol=kernel; reason=required WRF semantic-change decision.",
                    "<<<<<<< SEARCH",
                    "old",
                    "=======",
                    "new",
                    ">>>>>>> REPLACE",
                ]
            ),
            require_model_msg_knowledge_use=True,
        )

        assert accepted == {"static": [], "knowledge": []}

    def test_candidate_acceptance_policy_requires_each_required_decision(self):
        """Tests that one declared decision cannot satisfy multiple required decisions."""
        first_concept_id: str = "decisions/require-kg-interaction-for-wrf-physics-changes"
        second_concept_id: str = "decisions/require-fixture-parity-before-benchmark"
        receipt: Dict[str, Any] = {
            "domain": "wrf_single_physics",
            "static_policy": {"enabled": False},
            "semantic_change_policy": {
                "default": "reject_without_kg_decision",
                "candidate_enforcement": [
                    "require_configured_kg_decision_ids",
                    "require_declared_okf_concept_use",
                ],
            },
            "kg_decision_ids": [
                "require-kg-interaction-for-wrf-physics-changes",
                "require-fixture-parity-before-benchmark",
            ],
            "required_decisions_present": 1,
            "kg_context_paths": [
                "wiki/decisions/require-kg-interaction-for-wrf-physics-changes.md",
                "wiki/decisions/require-fixture-parity-before-benchmark.md",
            ],
            "required_decision_concepts_by_id": {
                "require-kg-interaction-for-wrf-physics-changes": [first_concept_id],
                "require-fixture-parity-before-benchmark": [second_concept_id],
            },
            "required_decision_concept_ids": [first_concept_id, second_concept_id],
            "knowledge_context_receipts": [
                {
                    "source": (
                        "wiki/decisions/" "require-kg-interaction-for-wrf-physics-changes.md"
                    ),
                    "okf_concept_id": first_concept_id,
                    "okf_type": "Decision",
                    "okf_title": "Require KG Interaction",
                    "sha256": "source-sha-1",
                    "chars": 12,
                },
                {
                    "source": "wiki/decisions/require-fixture-parity-before-benchmark.md",
                    "okf_concept_id": second_concept_id,
                    "okf_type": "Decision",
                    "okf_title": "Require Fixture Parity",
                    "sha256": "source-sha-2",
                    "chars": 12,
                },
            ],
        }
        one_declared_msg: str = "\n".join(
            [
                "KNOWLEDGE USE:",
                f"- {first_concept_id}: diff=SEARCH_REPLACE_1; reason=preserves decision.",
                "<<<<<<< SEARCH",
                "old",
                "=======",
                "new",
                ">>>>>>> REPLACE",
            ]
        )
        both_declared_msg: str = "\n".join(
            [
                "KNOWLEDGE USE:",
                f"- {first_concept_id}: diff=SEARCH_REPLACE_1; reason=preserves first decision.",
                f"- {second_concept_id}: diff=SEARCH_REPLACE_1; reason=preserves second decision.",
                "<<<<<<< SEARCH",
                "old",
                "=======",
                "new",
                ">>>>>>> REPLACE",
            ]
        )

        rejected = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg=one_declared_msg,
            require_model_msg_knowledge_use=True,
        )
        accepted = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg=both_declared_msg,
            require_model_msg_knowledge_use=True,
        )

        assert len(rejected["knowledge"]) == 1
        assert "require-fixture-parity-before-benchmark" in rejected["knowledge"][0]
        assert accepted == {"static": [], "knowledge": []}

    def test_candidate_acceptance_policy_requires_required_decision_receipt_map(self):
        """Tests that stale receipts without scoped decision maps fail closed."""
        concept_id: str = "decisions/require-kg-interaction-for-wrf-physics-changes"
        receipt: Dict[str, Any] = {
            "domain": "wrf_single_physics",
            "static_policy": {"enabled": False},
            "semantic_change_policy": {
                "default": "reject_without_kg_decision",
                "candidate_enforcement": [
                    "require_configured_kg_decision_ids",
                    "require_declared_okf_concept_use",
                ],
            },
            "kg_decision_ids": ["require-kg-interaction-for-wrf-physics-changes"],
            "required_decisions_present": 1,
            "kg_context_paths": [
                "wiki/decisions/require-kg-interaction-for-wrf-physics-changes.md"
            ],
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

        rejections = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg="\n".join(
                [
                    "KNOWLEDGE USE:",
                    f"- {concept_id}: diff=SEARCH_REPLACE_1; reason=preserves decision.",
                    "<<<<<<< SEARCH",
                    "old",
                    "=======",
                    "new",
                    ">>>>>>> REPLACE",
                ]
            ),
            require_model_msg_knowledge_use=True,
        )

        assert len(rejections["knowledge"]) == 1
        assert "required KG decisions" in rejections["knowledge"][0]

    def test_candidate_acceptance_policy_rejects_unstructured_okf_use(self):
        """Tests that concept-id mentions alone are not enough for candidate use."""
        concept_id: str = "decisions/require-kg-interaction-for-wrf-physics-changes"
        receipt: Dict[str, Any] = {
            "static_policy": {"enabled": False},
            "semantic_change_policy": {
                "default": "reject_without_kg_decision",
                "candidate_enforcement": [
                    "require_configured_kg_decision_ids",
                    "require_declared_okf_concept_use",
                ],
            },
            "kg_decision_ids": ["require-kg-interaction-for-wrf-physics-changes"],
            "required_decisions_present": 1,
            "kg_context_paths": [
                "wiki/decisions/require-kg-interaction-for-wrf-physics-changes.md"
            ],
            "required_decision_concepts_by_id": {
                "require-kg-interaction-for-wrf-physics-changes": [concept_id]
            },
            "required_decision_concept_ids": [concept_id],
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

        rejections = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg="\n".join(
                [
                    "KNOWLEDGE USE:",
                    f"- {concept_id}: required WRF semantic-change decision.",
                    "<<<<<<< SEARCH",
                    "old",
                    "=======",
                    "new",
                    ">>>>>>> REPLACE",
                ]
            ),
            require_model_msg_knowledge_use=True,
        )

        assert len(rejections["knowledge"]) == 1
        assert "traceability" in rejections["knowledge"][0]

    def test_candidate_acceptance_policy_rejects_empty_traceability_fields(self):
        """Tests that empty reason and trace fields do not satisfy OKF usage."""
        concept_id: str = "decisions/require-kg-interaction-for-wrf-physics-changes"
        receipt: Dict[str, Any] = {
            "static_policy": {"enabled": False},
            "semantic_change_policy": {
                "default": "reject_without_kg_decision",
                "candidate_enforcement": [
                    "require_configured_kg_decision_ids",
                    "require_declared_okf_concept_use",
                ],
            },
            "kg_decision_ids": ["require-kg-interaction-for-wrf-physics-changes"],
            "required_decisions_present": 1,
            "kg_context_paths": [
                "wiki/decisions/require-kg-interaction-for-wrf-physics-changes.md"
            ],
            "required_decision_concepts_by_id": {
                "require-kg-interaction-for-wrf-physics-changes": [concept_id]
            },
            "required_decision_concept_ids": [concept_id],
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

        rejections = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg="\n".join(
                [
                    "KNOWLEDGE USE:",
                    f"- {concept_id}: reason=; symbol=;",
                    "<<<<<<< SEARCH",
                    "old",
                    "=======",
                    "new",
                    ">>>>>>> REPLACE",
                ]
            ),
            require_model_msg_knowledge_use=True,
        )

        assert len(rejections["knowledge"]) == 1
        assert "missing reason, traceability_field" in rejections["knowledge"][0]

    def test_candidate_acceptance_policy_rejects_missing_code_symbol(self):
        """Tests that declared code symbols must exist in the candidate."""
        concept_id: str = "decisions/require-kg-interaction-for-wrf-physics-changes"
        receipt: Dict[str, Any] = {
            "static_policy": {"enabled": False},
            "semantic_change_policy": {
                "default": "reject_without_kg_decision",
                "candidate_enforcement": ["require_declared_okf_concept_use"],
            },
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

        rejections = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg="\n".join(
                [
                    "KNOWLEDGE USE:",
                    f"- {concept_id}: symbol=missing_kernel; reason=preserves decision.",
                    "<<<<<<< SEARCH",
                    "old",
                    "=======",
                    "new",
                    ">>>>>>> REPLACE",
                ]
            ),
            require_model_msg_knowledge_use=True,
        )

        assert len(rejections["knowledge"]) == 1
        assert "not present in candidate code" in rejections["knowledge"][0]

    def test_candidate_acceptance_policy_rejects_placeholder_traceability_values(self):
        """Tests that placeholder field values do not satisfy OKF usage."""
        concept_id: str = "decisions/require-kg-interaction-for-wrf-physics-changes"
        receipt: Dict[str, Any] = {
            "static_policy": {"enabled": False},
            "semantic_change_policy": {
                "default": "reject_without_kg_decision",
                "candidate_enforcement": ["require_declared_okf_concept_use"],
            },
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

        rejections = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg="\n".join(
                [
                    "KNOWLEDGE USE:",
                    f"- {concept_id}: symbol=kernel; reason=todo.",
                    "<<<<<<< SEARCH",
                    "old",
                    "=======",
                    "new",
                    ">>>>>>> REPLACE",
                ]
            ),
            require_model_msg_knowledge_use=True,
        )

        assert len(rejections["knowledge"]) == 1
        assert "placeholder reason" in rejections["knowledge"][0]

    def test_candidate_acceptance_policy_ignores_non_required_placeholder_fields(self):
        """Tests that placeholder optional fields do not poison sufficient declarations."""
        concept_id: str = "decisions/require-kg-interaction-for-wrf-physics-changes"
        receipt: Dict[str, Any] = {
            "static_policy": {"enabled": False},
            "semantic_change_policy": {
                "default": "allow_without_kg_decision",
                "candidate_enforcement": ["require_declared_okf_concept_use"],
            },
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

        rejections = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg="\n".join(
                [
                    "KNOWLEDGE USE:",
                    f"- {concept_id}: symbol=kernel; metric=n/a; reason=preserves decision.",
                    "<<<<<<< SEARCH",
                    "old",
                    "=======",
                    "new",
                    ">>>>>>> REPLACE",
                ]
            ),
            require_model_msg_knowledge_use=True,
        )

        assert rejections == {"static": [], "knowledge": []}

    def test_wrf_candidate_acceptance_policy_requires_evidence_traceability(self):
        """Tests that WRF strict mode rejects symbol-only OKF usage declarations."""
        concept_id: str = "decisions/require-kg-interaction-for-wrf-physics-changes"
        receipt: Dict[str, Any] = {
            "domain": "wrf_single_physics",
            "static_policy": {"enabled": False},
            "semantic_change_policy": {
                "default": "reject_without_kg_decision",
                "candidate_enforcement": ["require_declared_okf_concept_use"],
            },
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

        rejected = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg="\n".join(
                [
                    "KNOWLEDGE USE:",
                    f"- {concept_id}: symbol=kernel; reason=preserves decision.",
                    "<<<<<<< SEARCH",
                    "old",
                    "=======",
                    "new",
                    ">>>>>>> REPLACE",
                ]
            ),
            require_model_msg_knowledge_use=True,
        )
        accepted = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg="\n".join(
                [
                    "KNOWLEDGE USE:",
                    f"- {concept_id}: symbol=kernel; diff=SEARCH_REPLACE_1; reason=preserves decision.",
                    "<<<<<<< SEARCH",
                    "old",
                    "=======",
                    "new",
                    ">>>>>>> REPLACE",
                ]
            ),
            require_model_msg_knowledge_use=True,
        )

        assert len(rejected["knowledge"]) == 1
        assert "missing evidence_traceability_field" in rejected["knowledge"][0]
        assert accepted == {"static": [], "knowledge": []}

    def test_wrf_candidate_acceptance_policy_rejects_unknown_diff_reference(self):
        """Tests that WRF declarations cannot cite non-existent diff blocks."""
        concept_id: str = "decisions/require-kg-interaction-for-wrf-physics-changes"
        receipt: Dict[str, Any] = {
            "domain": "wrf_single_physics",
            "static_policy": {"enabled": False},
            "semantic_change_policy": {
                "default": "reject_without_kg_decision",
                "candidate_enforcement": ["require_declared_okf_concept_use"],
            },
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

        rejections = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg="\n".join(
                [
                    "KNOWLEDGE USE:",
                    f"- {concept_id}: symbol=kernel; diff=SEARCH_REPLACE_2; reason=preserves decision.",
                    "<<<<<<< SEARCH",
                    "old",
                    "=======",
                    "new",
                    ">>>>>>> REPLACE",
                ]
            ),
            require_model_msg_knowledge_use=True,
        )

        assert len(rejections["knowledge"]) == 1
        assert "SEARCH/REPLACE block 2" in rejections["knowledge"][0]

    def test_wrf_candidate_acceptance_policy_rejects_metric_only_before_evaluation(self):
        """Tests that metric-only WRF declarations cannot pass the pre-eval gate."""
        concept_id: str = "decisions/require-kg-interaction-for-wrf-physics-changes"
        receipt: Dict[str, Any] = {
            "domain": "wrf_single_physics",
            "static_policy": {"enabled": False},
            "semantic_change_policy": {
                "default": "reject_without_kg_decision",
                "candidate_enforcement": ["require_declared_okf_concept_use"],
            },
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

        rejections = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg="\n".join(
                [
                    "KNOWLEDGE USE:",
                    f"- {concept_id}: symbol=kernel; metric=max_abs_error; reason=preserves decision.",
                    "<<<<<<< SEARCH",
                    "old",
                    "=======",
                    "new",
                    ">>>>>>> REPLACE",
                ]
            ),
            require_model_msg_knowledge_use=True,
        )

        assert len(rejections["knowledge"]) == 1
        assert "cannot be validated before evaluator metrics exist" in rejections["knowledge"][0]

    def test_wrf_candidate_acceptance_policy_accepts_fixture_case_reference(self):
        """Tests that WRF declarations can cite a configured fixture case."""
        concept_id: str = "decisions/require-kg-interaction-for-wrf-physics-changes"
        receipt: Dict[str, Any] = {
            "domain": "wrf_single_physics",
            "static_policy": {"enabled": False},
            "semantic_change_policy": {
                "default": "reject_without_kg_decision",
                "candidate_enforcement": ["require_declared_okf_concept_use"],
            },
            "fixture_summary": {
                "traceable_train_fixture_names": ["case_train_0001"],
                "traceable_train_fixture_names_truncated": 0,
                "cases": {
                    "train": [{"name": "case_train_0001", "path": "fixtures/train/case.npz"}],
                    "holdout": [],
                    "private_holdout": [],
                },
            },
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

        rejections = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg="\n".join(
                [
                    "KNOWLEDGE USE:",
                    f"- {concept_id}: symbol=kernel; fixture=case_train_0001; reason=preserves decision.",
                    "<<<<<<< SEARCH",
                    "old",
                    "=======",
                    "new",
                    ">>>>>>> REPLACE",
                ]
            ),
            require_model_msg_knowledge_use=True,
        )

        assert rejections == {"static": [], "knowledge": []}

    def test_wrf_candidate_acceptance_policy_rejects_fixture_without_traceable_names(self):
        """Tests that fixture cases alone do not prove the name was exposed to the model."""
        concept_id: str = "decisions/require-kg-interaction-for-wrf-physics-changes"
        receipt: Dict[str, Any] = {
            "domain": "wrf_single_physics",
            "static_policy": {"enabled": False},
            "semantic_change_policy": {
                "default": "reject_without_kg_decision",
                "candidate_enforcement": ["require_declared_okf_concept_use"],
            },
            "fixture_summary": {
                "cases": {
                    "train": [{"name": "case_train_0001", "path": "fixtures/train/case.npz"}],
                    "holdout": [],
                    "private_holdout": [],
                }
            },
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

        rejections = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg="\n".join(
                [
                    "KNOWLEDGE USE:",
                    f"- {concept_id}: symbol=kernel; fixture=case_train_0001; reason=preserves decision.",
                    "<<<<<<< SEARCH",
                    "old",
                    "=======",
                    "new",
                    ">>>>>>> REPLACE",
                ]
            ),
            require_model_msg_knowledge_use=True,
        )

        assert len(rejections["knowledge"]) == 1
        assert "traceable train fixture names" in rejections["knowledge"][0]

    def test_wrf_candidate_acceptance_policy_rejects_unexposed_train_fixture(self):
        """Tests that WRF fixture declarations must use exposed train fixture names."""
        concept_id: str = "decisions/require-kg-interaction-for-wrf-physics-changes"
        receipt: Dict[str, Any] = {
            "domain": "wrf_single_physics",
            "static_policy": {"enabled": False},
            "semantic_change_policy": {
                "default": "reject_without_kg_decision",
                "candidate_enforcement": ["require_declared_okf_concept_use"],
            },
            "fixture_summary": {
                "traceable_train_fixture_names": [
                    f"case_train_{index:04d}" for index in range(1, 21)
                ],
                "traceable_train_fixture_names_truncated": 1,
                "cases": {
                    "train": [{"name": f"case_train_{index:04d}"} for index in range(1, 22)],
                    "holdout": [],
                    "private_holdout": [],
                },
            },
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

        accepted = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg="\n".join(
                [
                    "KNOWLEDGE USE:",
                    f"- {concept_id}: symbol=kernel; fixture=case_train_0020; reason=preserves decision.",
                    "<<<<<<< SEARCH",
                    "old",
                    "=======",
                    "new",
                    ">>>>>>> REPLACE",
                ]
            ),
            require_model_msg_knowledge_use=True,
        )
        rejected = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg="\n".join(
                [
                    "KNOWLEDGE USE:",
                    f"- {concept_id}: symbol=kernel; fixture=case_train_0021; reason=preserves decision.",
                    "<<<<<<< SEARCH",
                    "old",
                    "=======",
                    "new",
                    ">>>>>>> REPLACE",
                ]
            ),
            require_model_msg_knowledge_use=True,
        )

        assert accepted == {"static": [], "knowledge": []}
        assert len(rejected["knowledge"]) == 1
        assert "case_train_0021" in rejected["knowledge"][0]

    def test_wrf_gate_limits_traceable_train_fixtures_to_prompt_exposure(self, tmp_path: Path):
        """Tests that fixture traceability uses the bounded names shown to the model."""
        manifest: Dict[str, Any] = _make_valid_manifest(tmp_path)
        manifest["fixtures"]["train"] = [
            {"name": f"case_train_{index:04d}"} for index in range(1, 22)
        ]
        manifest_path: Path = _write_manifest(tmp_path, manifest)
        config: Dict[str, Any] = _make_config(manifest_path)
        config["KNOWLEDGE_GATE"]["require_fixture_files"] = False

        receipt: KnowledgeGateReceipt = run_knowledge_gate(
            config,
            {"out_dir": tmp_path / "out"},
            [tmp_path],
        )

        receipt_data = json.loads(receipt.output_path.read_text(encoding="utf-8"))
        assert len(receipt_data["fixture_summary"]["traceable_train_fixture_names"]) == 20
        assert (
            receipt_data["fixture_summary"]["traceable_train_fixture_names"][-1]
            == "case_train_0020"
        )
        assert receipt_data["fixture_summary"]["traceable_train_fixture_names_truncated"] == 1
        assert "case_train_0020" in receipt.prompt_context
        assert "case_train_0021" not in receipt.prompt_context

    def test_wrf_candidate_acceptance_policy_rejects_ambiguous_fixture_basename(self):
        """Tests that WRF fixture declarations must use case names, not filenames."""
        concept_id: str = "decisions/require-kg-interaction-for-wrf-physics-changes"
        receipt: Dict[str, Any] = {
            "domain": "wrf_single_physics",
            "static_policy": {"enabled": False},
            "semantic_change_policy": {
                "default": "reject_without_kg_decision",
                "candidate_enforcement": ["require_declared_okf_concept_use"],
            },
            "fixture_summary": {
                "traceable_train_fixture_names": ["case_train_0001"],
                "traceable_train_fixture_names_truncated": 0,
                "cases": {
                    "train": [{"name": "case_train_0001", "path": "fixtures/train/case.npz"}],
                    "holdout": [{"name": "case_holdout_0001", "path": "fixtures/holdout/case.npz"}],
                    "private_holdout": [],
                },
            },
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

        rejections = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg="\n".join(
                [
                    "KNOWLEDGE USE:",
                    f"- {concept_id}: symbol=kernel; fixture=case.npz; reason=preserves decision.",
                    "<<<<<<< SEARCH",
                    "old",
                    "=======",
                    "new",
                    ">>>>>>> REPLACE",
                ]
            ),
            require_model_msg_knowledge_use=True,
        )

        assert len(rejections["knowledge"]) == 1
        assert "fixture='case.npz' is not present in fixture receipts" in rejections["knowledge"][0]

        holdout_rejections = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg="\n".join(
                [
                    "KNOWLEDGE USE:",
                    f"- {concept_id}: symbol=kernel; fixture=case_holdout_0001; reason=preserves decision.",
                    "<<<<<<< SEARCH",
                    "old",
                    "=======",
                    "new",
                    ">>>>>>> REPLACE",
                ]
            ),
            require_model_msg_knowledge_use=True,
        )

        assert len(holdout_rejections["knowledge"]) == 1
        assert "case_holdout_0001" in holdout_rejections["knowledge"][0]

    def test_train_fixture_names_must_be_unique_after_normalization(self, tmp_path: Path):
        """Tests that equivalent fixture aliases fail preflight before prompting."""
        manifest: Dict[str, Any] = _make_valid_manifest(tmp_path)
        manifest["fixtures"]["train"] = [
            {"name": "case-a", "path": "input/fixtures/train/case.npz"},
            {"name": "case_a", "path": "input/fixtures/train/case.npz"},
        ]
        manifest_path: Path = _write_manifest(tmp_path, manifest)

        with pytest.raises(ValueError, match="duplicate normalized train fixture name"):
            run_knowledge_gate(
                _make_config(manifest_path), {"out_dir": tmp_path / "out"}, [tmp_path]
            )

    def test_wrf_partial_semantic_policy_keeps_default_okf_use_enforcement(self, tmp_path: Path):
        """Tests that partial WRF semantic policy cannot drop OKF usage enforcement."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        config: Dict[str, Any] = _make_config(manifest_path)
        config["KNOWLEDGE_GATE"]["semantic_change_policy"] = {
            "default": "reject_without_kg_decision"
        }

        receipt: KnowledgeGateReceipt = run_knowledge_gate(
            config,
            {"out_dir": tmp_path / "out"},
            [tmp_path],
        )

        receipt_data = json.loads(receipt.output_path.read_text(encoding="utf-8"))
        assert receipt_data["semantic_change_policy"]["candidate_enforcement"] == [
            "require_configured_kg_decision_ids",
            "require_declared_okf_concept_use",
        ]

        rejections = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt_data,
            model_msg="<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE",
            require_model_msg_knowledge_use=True,
        )

        assert len(rejections["knowledge"]) == 1
        assert "KNOWLEDGE USE" in rejections["knowledge"][0]

    def test_wrf_semantic_allow_policy_requires_explicit_override(self, tmp_path: Path):
        """Tests that WRF strict semantic policy cannot be silently disabled."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        config: Dict[str, Any] = _make_config(manifest_path)
        config["KNOWLEDGE_GATE"]["semantic_change_policy"] = {
            "default": "allow_without_kg_decision"
        }

        with pytest.raises(ValueError, match="allow_semantic_policy_override"):
            run_knowledge_gate(config, {"out_dir": tmp_path / "out"}, [tmp_path])

    def test_wrf_semantic_allow_policy_override_records_justification(self, tmp_path: Path):
        """Tests that explicit WRF semantic-policy opt-outs are auditable."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        config: Dict[str, Any] = _make_config(manifest_path)
        config["KNOWLEDGE_GATE"]["allow_semantic_policy_override"] = True
        config["KNOWLEDGE_GATE"][
            "semantic_policy_justification"
        ] = "Generic comparison run that only measures static acceptance wiring."
        config["KNOWLEDGE_GATE"]["semantic_change_policy"] = {
            "default": "allow_without_kg_decision"
        }

        receipt: KnowledgeGateReceipt = run_knowledge_gate(
            config,
            {"out_dir": tmp_path / "out"},
            [tmp_path],
        )

        receipt_data = json.loads(receipt.output_path.read_text(encoding="utf-8"))
        assert receipt_data["semantic_change_policy"]["candidate_enforcement"] == []
        assert receipt_data["semantic_change_policy"]["semantic_policy_override_allowed"] == 1
        assert (
            receipt_data["semantic_change_policy"]["semantic_policy_justification"]
            == "Generic comparison run that only measures static acceptance wiring."
        )

    def test_unknown_candidate_enforcement_raises(self, tmp_path: Path):
        """Tests that enforcement typos do not silently disable policy checks."""
        manifest_path: Path = _write_manifest(tmp_path, _make_valid_manifest(tmp_path))
        config: Dict[str, Any] = _make_config(manifest_path)
        config["KNOWLEDGE_GATE"]["semantic_change_policy"] = {
            "candidate_enforcement": ["require_declared_okf_concept_use_typo"]
        }

        with pytest.raises(ValueError, match="unsupported"):
            run_knowledge_gate(config, {"out_dir": tmp_path / "out"}, [tmp_path])

    def test_candidate_enforcement_runs_independent_of_default_policy(self):
        """Tests that explicit enforcement is not skipped by the default policy value."""
        concept_id: str = "decisions/require-kg-interaction-for-wrf-physics-changes"
        receipt: Dict[str, Any] = {
            "static_policy": {"enabled": False},
            "semantic_change_policy": {
                "default": "allow_without_kg_decision",
                "candidate_enforcement": ["require_declared_okf_concept_use"],
            },
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

        rejections = validate_candidate_acceptance_policy_by_kind(
            "subroutine kernel()\nend\n",
            receipt,
            model_msg="<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE",
            require_model_msg_knowledge_use=True,
        )

        assert rejections["static"] == []
        assert len(rejections["knowledge"]) == 1
        assert "KNOWLEDGE USE" in rejections["knowledge"][0]

    def test_static_policy_rejects_missing_evolve_block_when_scoped(self):
        """Tests that scoped static policy fails closed if markers disappear."""
        receipt: Dict[str, Any] = {
            "static_policy": {
                "enabled": True,
                "forbidden_patterns": {},
                "scan_scope": "evolve_block",
                "evolve_start_marker": "! EVOLVE-BLOCK-START",
                "evolve_end_marker": "! EVOLVE-BLOCK-END",
            },
            "semantic_change_policy": {"default": "allow_without_kg_decision"},
        }

        rejections = validate_candidate_acceptance_policy("subroutine kernel()\nend\n", receipt)

        assert "could not find EVOLVE block markers" in rejections[0]
