# ===--------------------------------------------------------------------------------------===#
#
# Part of the CodeEvolve Project, under the Apache License v2.0.
# See https://github.com/inter-co/science-codeevolve/blob/main/LICENSE for license information.
# SPDX-License-Identifier: Apache-2.0
#
# ===--------------------------------------------------------------------------------------===#
#
# This file verifies that CodeEvolve KG support stays file-based.
#
# ===--------------------------------------------------------------------------------------===#

import ast
import re
import tomllib
from pathlib import Path
from typing import List, Set

REPO_ROOT: Path = Path(__file__).resolve().parents[1]
SOURCE_ROOT: Path = Path(__file__).resolve().parents[1] / "src" / "codeevolve"
SCANNED_RUNTIME_ROOTS: List[Path] = [
    SOURCE_ROOT,
    REPO_ROOT / "problems" / "wrf_single_physics",
]
FORBIDDEN_MODULE_SEGMENTS: Set[str] = {
    "codex_apps",
    "kg",
    "kg_challenge",
    "kg_connect",
    "kg_ingest",
    "kg_init",
    "kg_lint",
    "kg_mcp",
    "kg_query",
    "kg_update",
    "mcp",
}
FORBIDDEN_RUNTIME_FRAGMENTS: Set[str] = {
    "/kg",
    "codex_apps",
    "kg-challenge",
    "kg-connect",
    "kg-ingest",
    "kg-init",
    "kg-lint",
    "kg-mcp",
    "kg-query",
    "kg-update",
    "kg_challenge",
    "kg_connect",
    "kg_ingest",
    "kg_init",
    "kg_lint",
    "kg_mcp",
    "kg_query",
    "kg_update",
    "list_mcp_resources",
    "mcp__",
    "read_mcp_resource",
}
FORBIDDEN_STRING_TOKENS: Set[str] = FORBIDDEN_RUNTIME_FRAGMENTS
FORBIDDEN_DEPENDENCY_NAMES: Set[str] = FORBIDDEN_MODULE_SEGMENTS.union(
    {
        "codex-apps",
        "fastmcp",
        "kg-challenge",
        "kg-connect",
        "kg-ingest",
        "kg-init",
        "kg-lint",
        "kg-mcp",
        "kg-query",
        "kg-update",
        "model-context-protocol",
    }
)


def _normalized_distribution_name(requirement: str) -> str:
    """Extracts and normalizes a dependency distribution name."""
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", requirement)
    return re.sub(r"[-.]+", "_", match.group(1).lower()) if match else ""


def _normalized_identifier(value: str) -> str:
    """Normalizes names for boundary-based KG/MCP token checks."""
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()


def _contains_forbidden_token(value: str, forbidden_values: Set[str]) -> bool:
    """Returns whether a value contains a forbidden token on identifier boundaries."""
    normalized: str = _normalized_identifier(value)
    if not normalized:
        return False
    for forbidden_value in forbidden_values:
        forbidden: str = _normalized_identifier(forbidden_value)
        if not forbidden:
            continue
        if re.search(rf"(^|_){re.escape(forbidden)}($|_)", normalized):
            return True
    return False


def _forbidden_module_match(module_name: str) -> bool:
    """Returns whether an import path references generic KG or MCP modules."""
    return _contains_forbidden_token(module_name, FORBIDDEN_MODULE_SEGMENTS)


def _iter_scanned_files() -> List[Path]:
    """Returns runtime files covered by the KG separation contract."""
    files: List[Path] = []
    for root in SCANNED_RUNTIME_ROOTS:
        if root.is_dir():
            files.extend(path for path in root.rglob("*") if path.is_file())
    return sorted(files)


class TestCodeEvolveKgSeparation:
    """Tests that CodeEvolve does not depend on generic KG skill runtimes."""

    def test_codeevolve_runtime_does_not_import_generic_kg_or_mcp_modules(self):
        """Tests that KG support remains a file/config/receipt contract."""
        violations: List[str] = []
        for source_path in sorted(path for path in _iter_scanned_files() if path.suffix == ".py"):
            module = ast.parse(source_path.read_text(encoding="utf-8"))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if _forbidden_module_match(alias.name):
                            violations.append(f"{source_path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if _forbidden_module_match(node.module):
                        violations.append(f"{source_path}: from {node.module} import ...")
                    for alias in node.names:
                        if _forbidden_module_match(alias.name):
                            violations.append(
                                f"{source_path}: from {node.module} import {alias.name}"
                            )

        assert violations == []

    def test_codeevolve_runtime_paths_do_not_define_generic_kg_or_mcp_adapters(self):
        """Tests that generic KG/MCP adapters are not added under CodeEvolve paths."""
        violations: List[str] = []
        for source_path in _iter_scanned_files():
            relative_parts: List[str] = list(source_path.relative_to(REPO_ROOT).parts)
            for part in relative_parts:
                if _contains_forbidden_token(Path(part).stem, FORBIDDEN_MODULE_SEGMENTS):
                    violations.append(f"{source_path}: path segment {part!r}")

        assert violations == []

    def test_codeevolve_runtime_does_not_call_generic_kg_or_mcp_tools_directly(self):
        """Tests that CodeEvolve core does not reach into KG or MCP tools."""
        violations: List[str] = []
        for source_path in (path for path in _iter_scanned_files() if path.suffix == ".py"):
            text: str = source_path.read_text(encoding="utf-8")
            for fragment in FORBIDDEN_STRING_TOKENS:
                if fragment in text:
                    violations.append(f"{source_path}: contains {fragment!r}")

        assert violations == []

    def test_package_metadata_does_not_depend_on_generic_kg_or_mcp_packages(self):
        """Tests that packaging metadata keeps CodeEvolve KG support decoupled."""
        pyproject_path: Path = REPO_ROOT / "pyproject.toml"
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        project = pyproject["project"]
        requirement_groups: List[str] = list(project.get("dependencies", []))
        optional_dependencies = project.get("optional-dependencies", {})
        for requirements in optional_dependencies.values():
            requirement_groups.extend(requirements)

        violations: List[str] = []
        for requirement in requirement_groups:
            normalized: str = _normalized_distribution_name(requirement)
            if _contains_forbidden_token(normalized, FORBIDDEN_DEPENDENCY_NAMES):
                violations.append(requirement)

        assert violations == []

    def test_lockfile_does_not_contain_generic_kg_or_mcp_packages(self):
        """Tests that locked environments do not pull in generic KG/MCP clients."""
        lock_path: Path = REPO_ROOT / "uv.lock"
        if not lock_path.exists():
            return

        lock_data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
        violations: List[str] = []
        for package in lock_data.get("package", []):
            if not isinstance(package, dict):
                continue
            name: str = str(package.get("name", ""))
            normalized: str = _normalized_distribution_name(name)
            if _contains_forbidden_token(normalized, FORBIDDEN_DEPENDENCY_NAMES):
                violations.append(name)

        assert violations == []
