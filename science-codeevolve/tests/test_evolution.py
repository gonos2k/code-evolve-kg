# ===--------------------------------------------------------------------------------------===#
#
# Part of the CodeEvolve Project, under the Apache License v2.0.
# See https://github.com/inter-co/science-codeevolve/blob/main/LICENSE for license information.
# SPDX-License-Identifier: Apache-2.0
#
# ===--------------------------------------------------------------------------------------===#
#
# This file implements unit tests for the evolution module helper functions.
#
# ===--------------------------------------------------------------------------------------===#

import json
import logging
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

import pytest

import codeevolve.evolution as evolution_module
from codeevolve.database import Program, ProgramDatabase
from codeevolve.evolution import (
    _get_knowledge_context_base_dirs,
    _get_markers,
    _initialize_from_checkpoint,
    _initialize_new_run,
    evaluate_and_store,
    select_parents,
    setup_codeevolve_components,
)
from codeevolve.utils.graphify_export import EvolvedCodeGraphExporter

# ---------------------------------------------------------------------------
# _get_markers
# ---------------------------------------------------------------------------


class TestGetMarkers:
    """Test suite for the _get_markers helper function."""

    def test_default_markers(self):
        """Tests that default markers are returned when not configured."""
        evolve_config: Dict[str, Any] = {}
        markers: Tuple[str, str, str, str] = _get_markers(evolve_config)
        assert markers[0] == "# EVOLVE-BLOCK-START"
        assert markers[1] == "# EVOLVE-BLOCK-END"
        assert markers[2] == "# PROMPT-BLOCK-START"
        assert markers[3] == "# PROMPT-BLOCK-END"

    def test_custom_markers(self):
        """Tests that custom markers override defaults."""
        evolve_config: Dict[str, Any] = {
            "markers": {
                "evolve_start_marker": "// BEGIN",
                "evolve_end_marker": "// FINISH",
                "mp_start_marker": "/* PSTART */",
                "mp_end_marker": "/* PEND */",
            },
        }
        markers: Tuple[str, str, str, str] = _get_markers(evolve_config)
        assert markers[0] == "// BEGIN"
        assert markers[1] == "// FINISH"
        assert markers[2] == "/* PSTART */"
        assert markers[3] == "/* PEND */"

    def test_partial_custom_markers(self):
        """Tests that unset markers fall back to defaults."""
        evolve_config: Dict[str, Any] = {
            "markers": {
                "evolve_start_marker": "// BEGIN",
            },
        }
        markers: Tuple[str, str, str, str] = _get_markers(evolve_config)
        assert markers[0] == "// BEGIN"
        assert markers[1] == "# EVOLVE-BLOCK-END"


# ---------------------------------------------------------------------------
# _get_knowledge_context_base_dirs
# ---------------------------------------------------------------------------


class TestKnowledgeContextBaseDirs:
    """Test suite for knowledge-context base directory resolution."""

    def test_includes_input_dir_and_ancestry(self, tmp_path):
        """Tests that problem-local and project-root context paths can resolve."""
        inpt_dir = tmp_path / "problems" / "wrf_single_physics" / "input"
        inpt_dir.mkdir(parents=True)
        cfg_path = tmp_path / "outputs" / "config.yaml"
        cfg_path.parent.mkdir()
        out_dir = tmp_path / "outputs"
        args = {"inpt_dir": inpt_dir, "cfg_path": cfg_path, "out_dir": out_dir}

        base_dirs = _get_knowledge_context_base_dirs(args)

        assert inpt_dir in base_dirs
        assert inpt_dir.parent in base_dirs
        assert inpt_dir.parent.parent in base_dirs
        assert cfg_path.parent in base_dirs
        assert out_dir in base_dirs


# ---------------------------------------------------------------------------
# evaluate_and_store
# ---------------------------------------------------------------------------


class TestEvaluateAndStore:
    """Test suite for evaluating and storing child solutions."""

    @pytest.mark.asyncio
    async def test_exports_evaluated_program_to_graphify_corpus(self, tmp_path):
        """Tests that evaluated programs are exported when Graphify export is configured."""

        class FakeEvaluator:
            def execute(self, prog, timeout_s=None):
                return 0, "", "", "", {"fitness": 2.0}

        sol_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        prompt_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        prompt: Program = Program(id="prompt-1", code="prompt", language="text", fitness=1.0)
        prompt_db.add(prompt)
        sol_db.add(
            Program(
                id="parent-1",
                code="subroutine kernel()\nend subroutine\n",
                language="fortran",
                fitness=1.0,
                returncode=0,
                eval_metrics={"fitness": 1.0},
                features={"fitness": 1.0},
            )
        )
        child: Program = Program(
            id="child-1",
            code="def f():\n    return 2\n",
            language="python",
            island_found=0,
            iteration_found=1,
            generation=1,
            prompt_id=prompt.id,
        )
        exporter = EvolvedCodeGraphExporter(
            root=tmp_path / "graphify-evolve-corpus",
            knowledge_links=["[[wrf-single-physics-optimization]]"],
        )

        improved = await evaluate_and_store(
            child_sol=child,
            prompt=prompt,
            evaluator=FakeEvaluator(),
            sol_db=sol_db,
            prompt_db=prompt_db,
            embedding=None,
            evolve_config={"fitness_key": "fitness"},
            evolve_state={"tok_usage": [], "errors": []},
            epoch=1,
            logger=logging.getLogger("test_evaluate_and_store"),
            graphify_exporter=exporter,
        )

        assert improved is True
        exported_files = list((tmp_path / "graphify-evolve-corpus").glob("**/*.py"))
        assert len(exported_files) == 1
        metadata_files = list((tmp_path / "graphify-evolve-corpus").glob("**/*.json"))
        assert len(metadata_files) == 1

    @pytest.mark.asyncio
    async def test_knowledge_gate_pass_does_not_imply_semantic_gate(self, tmp_path):
        """Tests that acceptance policy pass is separate from evaluator semantic gates."""

        class FakeEvaluator:
            def execute(self, prog, timeout_s=None):
                return 0, "", "", "", {"fitness": 2.0, "correct": 1.0}

        sol_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        prompt_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        prompt: Program = Program(id="prompt-1", code="prompt", language="text", fitness=1.0)
        prompt_db.add(prompt)
        sol_db.add(
            Program(
                id="parent-1",
                code="subroutine kernel()\nend subroutine\n",
                language="fortran",
                fitness=1.0,
                returncode=0,
                eval_metrics={"fitness": 1.0},
                features={"fitness": 1.0},
            )
        )
        child: Program = Program(
            id="child-1",
            code="subroutine kernel()\nend subroutine\n",
            language="fortran",
            island_found=0,
            iteration_found=1,
            generation=1,
            prompt_id=prompt.id,
        )

        improved = await evaluate_and_store(
            child_sol=child,
            prompt=prompt,
            evaluator=FakeEvaluator(),
            sol_db=sol_db,
            prompt_db=prompt_db,
            embedding=None,
            evolve_config={"fitness_key": "fitness"},
            evolve_state={"tok_usage": [], "errors": []},
            epoch=1,
            logger=logging.getLogger("test_acceptance_policy"),
            knowledge_gate_receipt={
                "static_policy": {"enabled": False},
                "semantic_change_policy": {"default": "allow_without_kg_decision"},
            },
        )

        assert improved is True
        assert child.eval_metrics["acceptance_policy_passed"] == 1.0
        assert "semantic_gate_passed" not in child.eval_metrics

    @pytest.mark.asyncio
    async def test_knowledge_gate_static_policy_rejects_before_evaluator(self, tmp_path):
        """Tests that gate static policy turns forbidden code into a candidate failure."""

        class FailingIfCalledEvaluator:
            def execute(self, prog, timeout_s=None):
                raise AssertionError("Evaluator should not run for static policy rejection")

        sol_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        prompt_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        prompt: Program = Program(id="prompt-1", code="prompt", language="text", fitness=1.0)
        prompt_db.add(prompt)
        sol_db.add(
            Program(
                id="parent-1",
                code="subroutine kernel()\nend subroutine\n",
                language="fortran",
                fitness=1.0,
                returncode=0,
                eval_metrics={"fitness": 1.0},
                features={"fitness": 1.0},
            )
        )
        child: Program = Program(
            id="child-1",
            code="subroutine kernel()\n  call execute_command_line('date')\nend subroutine\n",
            language="fortran",
            island_found=0,
            iteration_found=1,
            generation=1,
            prompt_id=prompt.id,
        )
        knowledge_gate_receipt: Dict[str, Any] = {
            "static_policy": {
                "enabled": True,
                "failure_code": 16,
                "forbidden_patterns": {
                    "execute_command_line": r"\bexecute_command_line\b",
                },
            }
        }

        improved = await evaluate_and_store(
            child_sol=child,
            prompt=prompt,
            evaluator=FailingIfCalledEvaluator(),
            sol_db=sol_db,
            prompt_db=prompt_db,
            embedding=None,
            evolve_config={"fitness_key": "fitness"},
            evolve_state={"tok_usage": [], "errors": []},
            epoch=1,
            logger=logging.getLogger("test_static_policy"),
            knowledge_gate_receipt=knowledge_gate_receipt,
        )

        assert improved is False
        assert child.returncode == 0
        assert child.fitness == 0.0
        assert child.eval_metrics["failure_code"] == 16.0
        assert child.eval_metrics["acceptance_policy_passed"] == 0.0
        assert child.eval_metrics["static_policy_rejections"] == 1.0
        assert child.eval_metrics["knowledge_policy_rejections"] == 0.0
        assert "semantic_gate_passed" not in child.eval_metrics
        assert "execute_command_line" in child.warning

    @pytest.mark.asyncio
    async def test_knowledge_gate_semantic_policy_rejects_without_decisions(self):
        """Tests that semantic policy cannot be bypassed by disabling static checks."""

        class FailingIfCalledEvaluator:
            def execute(self, prog, timeout_s=None):
                raise AssertionError("Evaluator should not run for semantic policy rejection")

        sol_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        prompt_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        prompt: Program = Program(id="prompt-1", code="prompt", language="text", fitness=1.0)
        prompt_db.add(prompt)
        sol_db.add(
            Program(
                id="parent-1",
                code="subroutine kernel()\nend subroutine\n",
                language="fortran",
                fitness=1.0,
                returncode=0,
                eval_metrics={"fitness": 1.0},
                features={"fitness": 1.0},
            )
        )
        child: Program = Program(
            id="child-1",
            code="subroutine kernel()\nend subroutine\n",
            language="fortran",
            island_found=0,
            iteration_found=1,
            generation=1,
            prompt_id=prompt.id,
        )

        improved = await evaluate_and_store(
            child_sol=child,
            prompt=prompt,
            evaluator=FailingIfCalledEvaluator(),
            sol_db=sol_db,
            prompt_db=prompt_db,
            embedding=None,
            evolve_config={"fitness_key": "fitness"},
            evolve_state={"tok_usage": [], "errors": []},
            epoch=1,
            logger=logging.getLogger("test_semantic_policy"),
            knowledge_gate_receipt={
                "static_policy": {"enabled": False, "failure_code": 16},
                "semantic_change_policy": {"default": "reject_without_kg_decision"},
                "kg_decision_ids": [],
                "required_decisions_present": 0,
            },
        )

        assert improved is False
        assert child.fitness == 0.0
        assert child.eval_metrics["failure_code"] == 17.0
        assert child.eval_metrics["acceptance_policy_passed"] == 0.0
        assert child.eval_metrics["static_policy_rejections"] == 0.0
        assert child.eval_metrics["knowledge_policy_rejections"] == 1.0
        assert "semantic_gate_passed" not in child.eval_metrics
        assert "semantic_change_policy" in child.warning

    @pytest.mark.asyncio
    async def test_knowledge_gate_rejects_generated_candidate_without_okf_use(self):
        """Tests that generated WRF candidates must declare exposed OKF usage."""

        class FailingIfCalledEvaluator:
            def execute(self, prog, timeout_s=None):
                raise AssertionError("Evaluator should not run for missing OKF use")

        concept_id: str = "decisions/require-kg-interaction-for-wrf-physics-changes"
        sol_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        prompt_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        prompt: Program = Program(id="prompt-1", code="prompt", language="text", fitness=1.0)
        prompt_db.add(prompt)
        sol_db.add(
            Program(
                id="parent-1",
                code="subroutine kernel()\nend subroutine\n",
                language="fortran",
                fitness=1.0,
                returncode=0,
                eval_metrics={"fitness": 1.0},
                features={"fitness": 1.0},
            )
        )
        child: Program = Program(
            id="child-1",
            code="subroutine kernel()\nend subroutine\n",
            language="fortran",
            island_found=0,
            iteration_found=1,
            generation=1,
            prompt_id=prompt.id,
            model_msg="<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE",
        )

        improved = await evaluate_and_store(
            child_sol=child,
            prompt=prompt,
            evaluator=FailingIfCalledEvaluator(),
            sol_db=sol_db,
            prompt_db=prompt_db,
            embedding=None,
            evolve_config={"fitness_key": "fitness"},
            evolve_state={"tok_usage": [], "errors": []},
            epoch=1,
            logger=logging.getLogger("test_missing_okf_use"),
            knowledge_gate_receipt={
                "static_policy": {"enabled": False, "failure_code": 16},
                "semantic_change_policy": {
                    "default": "reject_without_kg_decision",
                    "candidate_enforcement": [
                        "require_configured_kg_decision_ids",
                        "require_declared_okf_concept_use",
                    ],
                },
                "kg_decision_ids": ["require-kg-interaction-for-wrf-physics-changes"],
                "required_decisions_present": 1,
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
            },
        )

        assert improved is False
        assert child.fitness == 0.0
        assert child.eval_metrics["failure_code"] == 17.0
        assert child.eval_metrics["acceptance_policy_passed"] == 0.0
        assert child.eval_metrics["static_policy_rejections"] == 0.0
        assert child.eval_metrics["knowledge_policy_rejections"] == 1.0
        assert "semantic_gate_passed" not in child.eval_metrics
        assert "KNOWLEDGE USE" in child.warning


# ---------------------------------------------------------------------------
# initialization and resume Graphify export
# ---------------------------------------------------------------------------


class TestGraphifyInitializationExport:
    """Test suite for Graphify export during run initialization."""

    def test_knowledge_gate_runs_before_llm_setup(self, tmp_path, monkeypatch):
        """Tests that missing evidence stops setup before any LLM components are built."""
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(
            "\n".join(
                [
                    "EVOLVE_CONFIG:",
                    "  fitness_key: fitness",
                    "KNOWLEDGE_GATE:",
                    "  enabled: true",
                    "  required: true",
                    "  domain: wrf_single_physics",
                    "  manifest: missing_wrf_evidence.yaml",
                ]
            ),
            encoding="utf-8",
        )
        ensemble_called = False

        def fail_if_called(*args):
            nonlocal ensemble_called
            ensemble_called = True
            raise AssertionError("LLM setup should not run before knowledge gate")

        monkeypatch.setattr(evolution_module, "get_logger", lambda **kwargs: logging.getLogger("x"))
        monkeypatch.setattr(evolution_module, "_create_ensembles", fail_if_called)

        with pytest.raises(FileNotFoundError, match="KNOWLEDGE_GATE manifest"):
            setup_codeevolve_components(
                args={
                    "cfg_path": cfg_path,
                    "logs_dir": tmp_path,
                    "load_ckpt": 0,
                    "out_dir": tmp_path,
                },
                isl_data=SimpleNamespace(id=0),
                global_data=SimpleNamespace(
                    start_time=SimpleNamespace(value=0),
                    log_queue=None,
                ),
            )

        assert ensemble_called is False

    def test_initial_solution_export_records_prompt_id(self, tmp_path):
        """Tests that the initial solution metadata links back to the initial prompt."""

        class FakeEvaluator:
            def execute(self, prog):
                return 0, "", "", "", {"fitness": 1.0}

        inpt_dir = tmp_path / "input"
        source_dir = inpt_dir / "src"
        source_dir.mkdir(parents=True)
        (source_dir / "init.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        exporter = EvolvedCodeGraphExporter(root=tmp_path / "graphify-evolve-corpus")

        _, _, _, init_prompt, init_sol = _initialize_new_run(
            config={
                "SYS_MSG": "prompt",
                "CODEBASE_PATH": "src",
                "INIT_FILE_DATA": {"filename": "init.py", "language": "python"},
            },
            evolve_config={"fitness_key": "fitness"},
            args={"inpt_dir": inpt_dir},
            isl_id=0,
            evaluator=FakeEvaluator(),
            logger=logging.getLogger("test_initial_graphify_export"),
            graphify_exporter=exporter,
        )

        assert init_sol.prompt_id == init_prompt.id
        metadata_files = list((tmp_path / "graphify-evolve-corpus").glob("**/metadata/*.json"))
        assert len(metadata_files) == 1
        metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
        assert metadata["role"] == "initial"
        assert metadata["prompt_id"] == init_prompt.id
        assert metadata["prompt_program_id"] == init_prompt.id

    def test_initial_solution_evaluation_failure_raises(self, tmp_path):
        """Tests that infrastructure failures stop a new run before DB insertion."""

        class FailingEvaluator:
            def execute(self, prog):
                return 2, "", "", "compiler not found", {}

        inpt_dir = tmp_path / "input"
        source_dir = inpt_dir / "src"
        source_dir.mkdir(parents=True)
        (source_dir / "init.py").write_text("def f():\n    return 1\n", encoding="utf-8")

        with pytest.raises(RuntimeError, match="Initial solution evaluation failed"):
            _initialize_new_run(
                config={
                    "SYS_MSG": "prompt",
                    "CODEBASE_PATH": "src",
                    "INIT_FILE_DATA": {"filename": "init.py", "language": "python"},
                },
                evolve_config={"fitness_key": "fitness"},
                args={"inpt_dir": inpt_dir},
                isl_id=0,
                evaluator=FailingEvaluator(),
                logger=logging.getLogger("test_initial_fail_fast"),
            )

    def test_initial_solution_policy_rejection_raises_before_evaluator(self, tmp_path):
        """Tests that seed code cannot bypass the knowledge-gate candidate policy."""

        class FailingIfCalledEvaluator:
            def execute(self, prog):
                raise AssertionError("Evaluator should not run for rejected initial solution")

        inpt_dir = tmp_path / "input"
        source_dir = inpt_dir / "src"
        source_dir.mkdir(parents=True)
        (source_dir / "init.f90").write_text(
            "subroutine kernel()\n  call execute_command_line('date')\nend subroutine\n",
            encoding="utf-8",
        )

        with pytest.raises(RuntimeError, match="Initial solution rejected by knowledge gate"):
            _initialize_new_run(
                config={
                    "SYS_MSG": "prompt",
                    "CODEBASE_PATH": "src",
                    "INIT_FILE_DATA": {"filename": "init.f90", "language": "fortran"},
                },
                evolve_config={"fitness_key": "fitness"},
                args={"inpt_dir": inpt_dir},
                isl_id=0,
                evaluator=FailingIfCalledEvaluator(),
                logger=logging.getLogger("test_initial_policy_rejection"),
                knowledge_gate_receipt={
                    "static_policy": {
                        "enabled": True,
                        "failure_code": 16,
                        "forbidden_patterns": {
                            "execute_command_line": r"\bexecute_command_line\b",
                        },
                    },
                    "semantic_change_policy": {"default": "allow_without_kg_decision"},
                },
            )

    def test_initial_solution_missing_fitness_key_raises(self, tmp_path):
        """Tests that missing initial fitness metric is treated as setup failure."""

        class MissingFitnessEvaluator:
            def execute(self, prog):
                return 0, "", "", "", {"score": 1.0}

        inpt_dir = tmp_path / "input"
        source_dir = inpt_dir / "src"
        source_dir.mkdir(parents=True)
        (source_dir / "init.py").write_text("def f():\n    return 1\n", encoding="utf-8")

        with pytest.raises(KeyError, match="fitness"):
            _initialize_new_run(
                config={
                    "SYS_MSG": "prompt",
                    "CODEBASE_PATH": "src",
                    "INIT_FILE_DATA": {"filename": "init.py", "language": "python"},
                },
                evolve_config={"fitness_key": "fitness"},
                args={"inpt_dir": inpt_dir},
                isl_id=0,
                evaluator=MissingFitnessEvaluator(),
                logger=logging.getLogger("test_initial_missing_fitness"),
            )

    def test_checkpoint_resume_exports_current_best(self, tmp_path, monkeypatch):
        """Tests that checkpoint-loaded best code is seeded into the Graphify corpus."""
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(
            "\n".join(
                [
                    "EVOLVE_CONFIG:",
                    "  fitness_key: fitness",
                    "GRAPHIFY_EXPORT:",
                    "  enabled: true",
                    "  root: graphify-evolve-corpus",
                ]
            ),
            encoding="utf-8",
        )
        prompt_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        sol_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        init_prompt = Program(id="prompt-ckpt", code="prompt", language="text")
        init_sol = Program(
            id="sol-ckpt",
            code="def f():\n    return 3\n",
            language="python",
            fitness=3.0,
            returncode=0,
            eval_metrics={"fitness": 3.0},
            features={"fitness": 3.0},
            island_found=0,
            iteration_found=5,
            generation=5,
            prompt_id=init_prompt.id,
        )
        prompt_db.add(init_prompt)
        sol_db.add(init_sol)
        monkeypatch.setattr(evolution_module, "get_logger", lambda **kwargs: logging.getLogger("x"))
        monkeypatch.setattr(evolution_module, "_create_ensembles", lambda *args: (None, None))
        monkeypatch.setattr(evolution_module, "_create_prompt_sampler", lambda *args: None)
        monkeypatch.setattr(evolution_module, "_create_evaluator", lambda *args: None)
        monkeypatch.setattr(evolution_module, "_create_embedding", lambda *args: None)
        monkeypatch.setattr(evolution_module, "_create_exploration_scheduler", lambda *args: None)
        monkeypatch.setattr(evolution_module, "_create_timeout_scheduler", lambda *args: None)
        monkeypatch.setattr(
            evolution_module,
            "_initialize_from_checkpoint",
            lambda *args: (prompt_db, sol_db, {}, init_prompt, init_sol, None, None),
        )

        setup_codeevolve_components(
            args={
                "cfg_path": cfg_path,
                "logs_dir": tmp_path,
                "load_ckpt": 5,
                "out_dir": tmp_path,
            },
            isl_data=SimpleNamespace(id=0),
            global_data=SimpleNamespace(
                start_time=SimpleNamespace(value=0),
                log_queue=None,
            ),
        )

        metadata_files = list((tmp_path / "graphify-evolve-corpus").glob("**/metadata/*.json"))
        assert len(metadata_files) == 1
        metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
        assert metadata["role"] == "checkpoint_best"
        assert metadata["prompt_id"] == init_prompt.id

    def test_checkpoint_initialization_preserves_solution_prompt_id(self, monkeypatch):
        """Tests that checkpoint resume does not rewrite solution provenance."""
        prompt_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        original_prompt = Program(
            id="prompt-original",
            code="original prompt",
            language="text",
            fitness=1.0,
        )
        best_prompt = Program(
            id="prompt-best",
            code="best prompt",
            language="text",
            fitness=10.0,
        )
        prompt_db.add(original_prompt)
        prompt_db.add(best_prompt)
        sol_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        best_solution = Program(
            id="sol-best",
            code="def f():\n    return 4\n",
            language="python",
            fitness=4.0,
            prompt_id=original_prompt.id,
        )
        sol_db.add(best_solution)
        monkeypatch.setattr(
            evolution_module,
            "load_ckpt",
            lambda *args: (prompt_db, sol_db, {}, None, None),
        )

        _, _, _, init_prompt, init_sol, _, _ = _initialize_from_checkpoint(
            {"load_ckpt": 5, "ckpt_dir": "unused"},
            exploration_scheduler=None,
            timeout_scheduler=None,
        )

        assert prompt_db.best_prog_id == best_prompt.id
        assert init_sol.prompt_id == original_prompt.id
        assert init_sol.original_prompt_id == original_prompt.id
        assert init_sol.resolved_prompt_id == original_prompt.id
        assert init_sol.prompt_fallback_used is False
        assert init_prompt.id == original_prompt.id

    def test_checkpoint_initialization_falls_back_without_rewriting_prompt_id(self, monkeypatch):
        """Tests that missing resume prompt records can be audited downstream."""
        prompt_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        best_prompt = Program(
            id="prompt-best",
            code="best prompt",
            language="text",
            fitness=10.0,
        )
        prompt_db.add(best_prompt)
        sol_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        best_solution = Program(
            id="sol-best",
            code="def f():\n    return 4\n",
            language="python",
            fitness=4.0,
            prompt_id="prompt-missing",
        )
        sol_db.add(best_solution)
        monkeypatch.setattr(
            evolution_module,
            "load_ckpt",
            lambda *args: (prompt_db, sol_db, {}, None, None),
        )

        _, _, _, init_prompt, init_sol, _, _ = _initialize_from_checkpoint(
            {"load_ckpt": 5, "ckpt_dir": "unused"},
            exploration_scheduler=None,
            timeout_scheduler=None,
        )

        assert init_sol.prompt_id == "prompt-missing"
        assert init_sol.original_prompt_id == "prompt-missing"
        assert init_sol.resolved_prompt_id == best_prompt.id
        assert init_sol.prompt_fallback_used is True
        assert init_prompt.id == best_prompt.id

    def test_checkpoint_initialization_records_missing_prompt_id_fallback(self, monkeypatch):
        """Tests that legacy checkpoints without prompt IDs keep fallback audit data."""
        prompt_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        best_prompt = Program(
            id="prompt-best",
            code="best prompt",
            language="text",
            fitness=10.0,
        )
        prompt_db.add(best_prompt)
        sol_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        best_solution = Program(
            id="sol-best",
            code="def f():\n    return 4\n",
            language="python",
            fitness=4.0,
            prompt_id=None,
        )
        sol_db.add(best_solution)
        monkeypatch.setattr(
            evolution_module,
            "load_ckpt",
            lambda *args: (prompt_db, sol_db, {}, None, None),
        )

        _, _, _, init_prompt, init_sol, _, _ = _initialize_from_checkpoint(
            {"load_ckpt": 5, "ckpt_dir": "unused"},
            exploration_scheduler=None,
            timeout_scheduler=None,
        )

        assert init_sol.prompt_id is None
        assert init_sol.original_prompt_id is None
        assert init_sol.resolved_prompt_id == best_prompt.id
        assert init_sol.prompt_fallback_used is True
        assert init_prompt.id == best_prompt.id


# ---------------------------------------------------------------------------
# select_parents
# ---------------------------------------------------------------------------


class TestSelectParents:
    """Test suite for the select_parents function."""

    def _make_prog(self, id: str, fitness: float = 0.0) -> Program:
        """Helper to create a minimal evaluated program."""
        prog: Program = Program(
            id=id,
            code=f"# {id}",
            language="python",
            fitness=fitness,
            island_found=0,
            iteration_found=0,
            generation=0,
            returncode=0,
            eval_metrics={"fitness": fitness},
            features={"fitness": fitness},
        )
        prog.prog_msg = f"Program {id}"
        return prog

    def test_init_pop_returns_initial_programs(self):
        """Tests that during init population, initial programs are selected."""
        sol_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)
        prompt_db: ProgramDatabase = ProgramDatabase(id=0, seed=42)

        init_sol: Program = self._make_prog("init_sol", fitness=1.0)
        init_prompt: Program = Program(id="init_prompt", code="prompt", language="text")

        sol_db.add(init_sol)
        prompt_db.add(init_prompt)

        evolve_config: Dict[str, Any] = {
            "num_inspirations": 0,
            "selection": {"policy": "tournament", "kwargs": {"tournament_size": 3}},
        }
        logger: logging.Logger = logging.getLogger("test_select")

        parent_sol: Program
        parent_prompt: Program
        inspirations: List[Program]
        parent_sol, parent_prompt, inspirations = select_parents(
            sol_db=sol_db,
            prompt_db=prompt_db,
            init_sol=init_sol,
            init_prompt=init_prompt,
            evolve_config=evolve_config,
            gen_init_pop=True,
            exploration=False,
            logger=logger,
        )

        assert parent_sol.id == "init_sol"
        assert parent_prompt.id == "init_prompt"
        assert inspirations == []
