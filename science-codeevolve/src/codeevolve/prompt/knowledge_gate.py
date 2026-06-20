# ===--------------------------------------------------------------------------------------===#
#
# Part of the CodeEvolve Project, under the Apache License v2.0.
# See https://github.com/inter-co/science-codeevolve/blob/main/LICENSE for license information.
# SPDX-License-Identifier: Apache-2.0
#
# ===--------------------------------------------------------------------------------------===#
#
# This file implements file-based knowledge-gate preflight checks.
#
# ===--------------------------------------------------------------------------------------===#

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import urlparse

import yaml

from codeevolve.prompt.knowledge import okf_concept_id_from_source, validate_okf_document
from codeevolve.utils.constants import DEFAULT_EVOLVE_END_MARKER, DEFAULT_EVOLVE_START_MARKER
from codeevolve.utils.knowledge_use import (
    declared_okf_concept_use,
    declared_usage_traceability_rejection,
    okf_context_available_from_receipts,
    required_decision_concepts_by_id,
)

DEFAULT_WRF_MIN_SOURCES: Dict[str, int] = {
    "official_docs": 1,
    "raw_wrf_code": 2,
    "literature": 1,
    "similar_code": 1,
}
_SOURCE_KIND_ALIASES: Dict[str, str] = {
    "official_doc": "official_docs",
    "official_docs": "official_docs",
    "raw_wrf_code": "raw_wrf_code",
    "wrf_code": "raw_wrf_code",
    "literature": "literature",
    "paper": "literature",
    "similar_code": "similar_code",
    "github_code": "similar_code",
}
_PLACEHOLDER_RE = re.compile(
    r"(v4\.x\.y|exact-git-sha|exact-commit|replace-with|/path/to|\.\.\.|placeholder|todo)",
    re.IGNORECASE,
)
_GIT_SHA_RE = re.compile(r"[0-9a-fA-F]{7,40}")
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}")
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
DEFAULT_WRF_FORBIDDEN_PATTERNS: Dict[str, str] = {
    "execute_command_line": r"\bexecute_command_line\b",
    "get_environment_variable": r"\bget_environment_variable\b",
    "iso_c_binding": r"\biso_c_binding\b",
    "fortran_open": r"(?i)(^|[^A-Za-z0-9_])open\s*\(",
    "fortran_read": r"(?i)(^|[^A-Za-z0-9_])read\s*\(",
    "fortran_write": r"(?i)(^|[^A-Za-z0-9_])write\s*\(",
    "openmp_directive": r"(?im)^\s*!\$omp\b",
}
_CONFIGURED_KG_DECISION_ENFORCEMENT = "require_configured_kg_decision_ids"
_DECLARED_OKF_USE_ENFORCEMENT = "require_declared_okf_concept_use"
_ALLOWED_CANDIDATE_ENFORCEMENTS: Set[str] = {
    _CONFIGURED_KG_DECISION_ENFORCEMENT,
    _DECLARED_OKF_USE_ENFORCEMENT,
}
MAX_TRACEABLE_TRAIN_FIXTURE_NAMES: int = 20


@dataclass(frozen=True)
class KnowledgeGateReceipt:
    """Result of a knowledge-gate preflight run.

    Attributes:
        data: JSON-serializable receipt data written to disk.
        output_path: Receipt file path.
        receipt_sha256: SHA-256 digest of the written receipt JSON.
        prompt_context: Short context block to prepend to LLM prompts.
    """

    data: Dict[str, Any]
    output_path: Path
    receipt_sha256: str
    prompt_context: str


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
    raise ValueError(f"{key} must be a string or list of strings.")


def _resolve_path(path_value: str, base_dirs: Iterable[Path]) -> Optional[Path]:
    """Resolves a configured path against candidate base directories."""
    candidate: Path = Path(path_value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve() if candidate.exists() else candidate

    for base_dir in base_dirs:
        resolved: Path = (base_dir / candidate).resolve()
        if resolved.exists():
            return resolved
    return None


def _sha256_bytes(content: bytes) -> str:
    """Returns a SHA-256 digest for bytes."""
    return hashlib.sha256(content).hexdigest()


def _sha256_path(path: Path) -> str:
    """Returns a SHA-256 digest for a file."""
    return _sha256_bytes(path.read_bytes())


def _validate_sha256(value: Any, *, label: str) -> str:
    """Validates and returns a SHA-256 digest string."""
    digest: str = str(value or "").strip()
    if _SHA256_RE.fullmatch(digest) is None:
        raise ValueError(f"{label} must be a 64-character sha256 digest.")
    return digest.lower()


def _validate_git_sha(value: Any, *, label: str) -> str:
    """Validates and returns an exact git SHA-like identifier."""
    commit: str = str(value or "").strip()
    if _is_placeholder(commit) or _GIT_SHA_RE.fullmatch(commit) is None:
        raise ValueError(f"{label} must be an exact git SHA.")
    return commit


def _validate_http_url(value: Any, *, label: str) -> str:
    """Validates source URL syntax without performing a network request."""
    url: str = str(value or "").strip()
    parsed = urlparse(url)
    if _is_placeholder(url) or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label} must be an http(s) URL.")
    return url


def _validate_doi(value: Any, *, label: str) -> str:
    """Validates DOI syntax without resolving DOI metadata."""
    doi: str = str(value or "").strip()
    if _is_placeholder(doi) or _DOI_RE.fullmatch(doi) is None:
        raise ValueError(f"{label} must look like a DOI, e.g. 10.1234/example.")
    return doi


def _json_bytes(data: Dict[str, Any]) -> bytes:
    """Serializes strict JSON as bytes."""
    return json.dumps(data, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")


def _is_placeholder(value: Any) -> bool:
    """Returns whether a config value appears to be a placeholder."""
    if value is None:
        return True
    text: str = str(value).strip()
    return not text or bool(_PLACEHOLDER_RE.search(text))


def _require_mapping(data: Dict[str, Any], key: str) -> Dict[str, Any]:
    """Gets a required mapping field from a dictionary."""
    value: Any = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"KNOWLEDGE_GATE manifest field {key!r} must be a mapping.")
    return value


def _source_locator_present(source: Dict[str, Any]) -> bool:
    """Returns whether a source entry has at least one reproducible locator."""
    return any(
        source.get(key)
        for key in ("url", "repo", "doi", "citation", "path", "local_path", "snapshot_path")
    )


def _resolve_existing_file(
    raw_path: str,
    *,
    base_dirs: Iterable[Path],
    label: str,
    required: bool,
) -> Optional[Path]:
    """Resolves and validates a configured file path."""
    if _is_placeholder(raw_path):
        if required:
            raise ValueError(f"{label} is missing or placeholder.")
        return None
    resolved_path: Optional[Path] = _resolve_path(raw_path, base_dirs)
    if resolved_path is None or not resolved_path.is_file():
        if required:
            raise FileNotFoundError(f"{label} not found: {raw_path}")
        return None
    return resolved_path


def _normalize_relative_source_path(value: Any, *, label: str) -> str:
    """Validates and normalizes a repository-relative source path."""
    if _is_placeholder(value):
        raise ValueError(f"{label} is missing or placeholder.")
    raw_path: str = str(value).strip().replace("\\", "/")
    path: PurePosixPath = PurePosixPath(raw_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must be a repository-relative path inside wrf_source_root.")
    normalized: str = path.as_posix()
    if normalized in {"", "."}:
        raise ValueError(f"{label} must name a source file.")
    return normalized


def _normalize_source_kind(kind: Any) -> str:
    """Normalizes source kind aliases to gate categories."""
    if not isinstance(kind, str):
        raise ValueError("KNOWLEDGE_GATE source kind must be a string.")
    normalized: Optional[str] = _SOURCE_KIND_ALIASES.get(kind.strip().lower())
    if normalized is None:
        raise ValueError(f"Unsupported KNOWLEDGE_GATE source kind: {kind}")
    return normalized


def _validate_target(
    target: Dict[str, Any],
    *,
    require_exact_target: bool,
    require_source_files: bool,
    manifest_path: Path,
) -> Dict[str, Any]:
    """Validates and summarizes the immutable WRF target contract."""
    required_fields: List[str] = [
        "wrf_version",
        "wrf_commit",
        "physics_family",
        "namelist_option",
        "namelist_value",
        "scheme_module",
        "driver_module",
        "entrypoint",
    ]
    if require_source_files:
        required_fields.append("wrf_source_root")
    missing: List[str] = [field for field in required_fields if _is_placeholder(target.get(field))]
    if missing:
        raise ValueError(
            "KNOWLEDGE_GATE target contains missing or placeholder fields: " + ", ".join(missing)
        )

    wrf_commit: str = str(target["wrf_commit"]).strip()
    if require_exact_target and _GIT_SHA_RE.fullmatch(wrf_commit) is None:
        raise ValueError(
            "KNOWLEDGE_GATE target.wrf_commit must be an exact git SHA "
            "when require_exact_target is true."
        )

    source_root_text: Optional[str] = None
    wrf_source_root_value: Any = target.get("wrf_source_root")
    if not _is_placeholder(wrf_source_root_value):
        source_root: Path = Path(str(wrf_source_root_value)).expanduser()
        if not source_root.is_absolute():
            source_root = (manifest_path.parent / source_root).resolve()
        if not source_root.is_dir():
            raise FileNotFoundError(
                f"KNOWLEDGE_GATE target.wrf_source_root not found: {source_root}"
            )
        source_root_text = str(source_root)

    scheme_module: str = _normalize_relative_source_path(
        target["scheme_module"], label="KNOWLEDGE_GATE target.scheme_module"
    )
    driver_module: str = _normalize_relative_source_path(
        target["driver_module"], label="KNOWLEDGE_GATE target.driver_module"
    )

    return {
        "wrf_version": str(target["wrf_version"]),
        "wrf_commit": wrf_commit,
        "wrf_source_root": source_root_text,
        "physics_family": str(target["physics_family"]),
        "namelist_option": str(target["namelist_option"]),
        "namelist_value": str(target["namelist_value"]),
        "scheme_module": scheme_module,
        "driver_module": driver_module,
        "entrypoint": str(target["entrypoint"]),
    }


def _validate_sources(
    manifest: Dict[str, Any],
    *,
    min_sources: Dict[str, int],
    target_summary: Dict[str, Any],
    require_source_files: bool,
    require_source_digests: bool,
    manifest_path: Path,
) -> Dict[str, Any]:
    """Validates evidence sources and returns count/id summaries."""
    sources_value: Any = manifest.get("sources")
    if not isinstance(sources_value, list) or not sources_value:
        raise ValueError("KNOWLEDGE_GATE manifest requires a non-empty sources list.")

    counts: Dict[str, int] = {
        "official_docs": 0,
        "raw_wrf_code": 0,
        "literature": 0,
        "similar_code": 0,
    }
    ids_by_kind: Dict[str, List[str]] = {key: [] for key in counts}
    source_receipts: List[Dict[str, Any]] = []
    target_commit: str = str(target_summary.get("wrf_commit", ""))
    source_root_value: Optional[str] = target_summary.get("wrf_source_root")
    source_root: Optional[Path] = Path(source_root_value) if source_root_value else None
    source_root_resolved: Optional[Path] = (
        source_root.resolve() if source_root is not None else None
    )
    raw_wrf_paths: Set[str] = set()

    for index, source in enumerate(sources_value, start=1):
        if not isinstance(source, dict):
            raise ValueError(f"KNOWLEDGE_GATE source #{index} must be a mapping.")
        if _is_placeholder(source.get("id")):
            raise ValueError(f"KNOWLEDGE_GATE source #{index} is missing id.")
        if not _source_locator_present(source):
            raise ValueError(f"KNOWLEDGE_GATE source {source['id']!r} lacks a locator.")
        kind: str = _normalize_source_kind(source.get("kind"))
        counts[kind] += 1
        ids_by_kind[kind].append(str(source["id"]))

        receipt: Dict[str, Any] = {
            "id": str(source["id"]),
            "kind": kind,
        }
        if kind in {"raw_wrf_code", "similar_code"}:
            commit: str = _validate_git_sha(
                source.get("commit"), label=f"KNOWLEDGE_GATE code source {source['id']!r} commit"
            )
            receipt["commit"] = commit
        if kind == "raw_wrf_code":
            source_rel_path: str = _normalize_relative_source_path(
                source.get("path"), label=f"KNOWLEDGE_GATE raw WRF source {source['id']!r} path"
            )
            raw_wrf_paths.add(source_rel_path)
            receipt["path"] = source_rel_path
            if commit != target_commit:
                raise ValueError(
                    f"KNOWLEDGE_GATE raw WRF source {source['id']!r} commit must match "
                    "target.wrf_commit."
                )
            if source_root is None and require_source_files:
                raise ValueError(
                    "KNOWLEDGE_GATE raw WRF source validation requires wrf_source_root."
                )
            if source_root_resolved is not None:
                source_path: Path = (source_root_resolved / source_rel_path).resolve()
                try:
                    source_path.relative_to(source_root_resolved)
                except ValueError as err:
                    raise ValueError(
                        f"KNOWLEDGE_GATE raw WRF source {source['id']!r} path escapes "
                        "target.wrf_source_root."
                    ) from err
                if not source_path.is_file():
                    if require_source_files:
                        raise FileNotFoundError(
                            f"KNOWLEDGE_GATE raw WRF source file not found: {source_path}"
                        )
                else:
                    digest: str = _sha256_path(source_path)
                    expected_digest: Optional[Any] = source.get("sha256")
                    if expected_digest is not None:
                        expected: str = _validate_sha256(
                            expected_digest,
                            label=f"KNOWLEDGE_GATE raw WRF source {source['id']!r} sha256",
                        )
                        if digest != expected:
                            raise ValueError(
                                f"KNOWLEDGE_GATE raw WRF source {source['id']!r} "
                                "sha256 mismatch."
                            )
                    receipt["sha256"] = digest
        elif kind == "similar_code":
            expected_digest = source.get("sha256")
            local_path_value: Optional[Any] = source.get("local_path")
            if local_path_value is None:
                local_path_value = source.get("snapshot_path")
            if local_path_value is not None:
                local_path: Path = Path(str(local_path_value)).expanduser()
                if not local_path.is_absolute():
                    local_path = manifest_path.parent / local_path
                if not local_path.is_file():
                    raise FileNotFoundError(
                        f"KNOWLEDGE_GATE similar code local_path not found: {local_path}"
                    )
                digest = _sha256_path(local_path)
                if expected_digest is not None:
                    expected = _validate_sha256(
                        expected_digest,
                        label=f"KNOWLEDGE_GATE similar code {source['id']!r} sha256",
                    )
                    if digest != expected:
                        raise ValueError(
                            f"KNOWLEDGE_GATE similar code {source['id']!r} sha256 mismatch."
                        )
                receipt["local_path"] = str(local_path)
                receipt["sha256"] = digest
            elif require_source_digests:
                raise ValueError(
                    f"KNOWLEDGE_GATE similar code {source['id']!r} requires local_path "
                    "or snapshot_path when require_source_digests is true."
                )
        elif kind == "official_docs":
            if _is_placeholder(source.get("url")):
                raise ValueError(f"KNOWLEDGE_GATE official doc {source['id']!r} needs url.")
            receipt["url"] = _validate_http_url(
                source.get("url"),
                label=f"KNOWLEDGE_GATE official doc {source['id']!r} url",
            )
        elif kind == "literature":
            if _is_placeholder(source.get("doi")) and _is_placeholder(source.get("citation")):
                raise ValueError(
                    f"KNOWLEDGE_GATE literature source {source['id']!r} needs DOI or citation."
                )
            if not _is_placeholder(source.get("doi")):
                receipt["doi"] = _validate_doi(
                    source.get("doi"),
                    label=f"KNOWLEDGE_GATE literature source {source['id']!r} doi",
                )
            if not _is_placeholder(source.get("citation")):
                receipt["citation"] = str(source["citation"])
        source_receipts.append(receipt)

    required_raw_paths: Set[str] = {
        str(target_summary.get("scheme_module", "")),
        str(target_summary.get("driver_module", "")),
    }
    required_raw_paths.discard("")
    missing_target_sources: List[str] = sorted(required_raw_paths.difference(raw_wrf_paths))
    if (raw_wrf_paths or int(min_sources.get("raw_wrf_code", 0)) > 0) and missing_target_sources:
        raise ValueError(
            "KNOWLEDGE_GATE raw WRF sources must include target scheme_module and "
            "driver_module paths: " + ", ".join(missing_target_sources)
        )

    deficient: List[str] = [
        f"{kind}={counts.get(kind, 0)}<{minimum}"
        for kind, minimum in min_sources.items()
        if counts.get(kind, 0) < int(minimum)
    ]
    if deficient:
        raise ValueError("KNOWLEDGE_GATE source evidence is insufficient: " + ", ".join(deficient))
    return {
        "source_counts": counts,
        "source_ids_by_kind": ids_by_kind,
        "source_receipts": source_receipts,
    }


def _validate_knowledge_context_config(
    config: Dict[str, Any],
    *,
    base_dirs: Iterable[Path],
    require_okf_context: bool,
) -> Dict[str, Any]:
    """Validates required knowledge prompt context and returns source receipts."""
    context_cfg: Any = config.get("KNOWLEDGE_CONTEXT")
    if not isinstance(context_cfg, dict) or not _as_bool(context_cfg.get("enabled"), True):
        raise ValueError("KNOWLEDGE_GATE requires enabled KNOWLEDGE_CONTEXT.")
    if not _as_bool(context_cfg.get("required"), False):
        raise ValueError("KNOWLEDGE_GATE requires KNOWLEDGE_CONTEXT.required=true.")
    require_okf: bool = _as_bool(context_cfg.get("require_okf"), False) or require_okf_context
    okf_bundle_root: str = str(context_cfg.get("okf_bundle_root", "wiki"))
    paths: List[str] = _as_string_list(context_cfg.get("paths"), "KNOWLEDGE_CONTEXT.paths")
    inline: List[str] = _as_string_list(context_cfg.get("inline"), "KNOWLEDGE_CONTEXT.inline")
    if not paths and not inline:
        raise ValueError("KNOWLEDGE_GATE requires non-empty KNOWLEDGE_CONTEXT paths or inline.")

    receipts: List[Dict[str, Any]] = []
    for context_path in paths:
        resolved_path: Optional[Path] = _resolve_existing_file(
            context_path,
            base_dirs=base_dirs,
            label=f"KNOWLEDGE_CONTEXT path {context_path!r}",
            required=True,
        )
        assert resolved_path is not None
        text: str = resolved_path.read_text(encoding="utf-8")
        if not text.strip():
            raise ValueError(f"KNOWLEDGE_CONTEXT path {context_path!r} is empty.")
        receipt: Dict[str, Any] = {
            "source": context_path,
            "resolved_path": str(resolved_path),
            "sha256": _sha256_bytes(text.encode("utf-8")),
            "chars": len(text),
        }
        if require_okf:
            okf_frontmatter: Dict[str, Any] = validate_okf_document(
                text,
                label=f"KNOWLEDGE_CONTEXT path {context_path!r}",
            )
            receipt["okf_concept_id"] = okf_concept_id_from_source(
                context_path,
                bundle_root=okf_bundle_root,
            )
            receipt["okf_type"] = str(okf_frontmatter.get("type"))
            if okf_frontmatter.get("title") is not None:
                receipt["okf_title"] = str(okf_frontmatter["title"])
            if okf_frontmatter.get("resource") is not None:
                receipt["okf_resource"] = str(okf_frontmatter["resource"])
        receipts.append(receipt)

    for index, inline_entry in enumerate(inline, start=1):
        if not inline_entry.strip():
            raise ValueError(f"KNOWLEDGE_CONTEXT inline:{index} is empty.")
        receipts.append(
            {
                "source": f"inline:{index}",
                "sha256": _sha256_bytes(inline_entry.encode("utf-8")),
                "chars": len(inline_entry),
            }
        )
    if require_okf and not any(receipt.get("okf_concept_id") for receipt in receipts):
        raise ValueError(
            "KNOWLEDGE_GATE requires at least one OKF-compatible "
            "KNOWLEDGE_CONTEXT path with an okf_concept_id."
        )
    digest_receipts: List[Dict[str, Any]] = [
        {key: value for key, value in receipt.items() if key != "resolved_path"}
        for receipt in receipts
    ]
    return {
        "knowledge_context_receipts": receipts,
        "okf_required": 1 if require_okf else 0,
        "okf_bundle_root": okf_bundle_root if require_okf else None,
        "knowledge_context_sha256": _sha256_bytes(
            json.dumps(digest_receipts, sort_keys=True, allow_nan=False).encode("utf-8")
        ),
    }


def _validate_graphify_export_config(config: Dict[str, Any]) -> None:
    """Validates that Graphify export is enabled for evolved-code linkage."""
    export_cfg: Any = config.get("GRAPHIFY_EXPORT")
    if not isinstance(export_cfg, dict) or not _as_bool(export_cfg.get("enabled"), True):
        raise ValueError("KNOWLEDGE_GATE requires enabled GRAPHIFY_EXPORT.")
    if not _as_bool(export_cfg.get("required"), True):
        raise ValueError("KNOWLEDGE_GATE requires GRAPHIFY_EXPORT.required=true.")
    knowledge_links: List[str] = _as_string_list(
        export_cfg.get("knowledge_links"), "GRAPHIFY_EXPORT.knowledge_links"
    )
    if not knowledge_links:
        raise ValueError("KNOWLEDGE_GATE requires GRAPHIFY_EXPORT.knowledge_links.")


def _exposed_okf_decision_concepts_by_id(
    *,
    knowledge_context_receipts: List[Dict[str, Any]],
    required_decisions: List[str],
    manifest_context_paths: Set[str],
) -> Dict[str, List[str]]:
    """Returns exposed OKF concept ids that satisfy each required decision id."""
    context_available: List[Dict[str, Any]] = okf_context_available_from_receipts(
        knowledge_context_receipts
    )
    return required_decision_concepts_by_id(
        context_available=context_available,
        decision_ids=required_decisions,
        manifest_context_paths=manifest_context_paths,
    )


def _validate_kg_links(
    manifest: Dict[str, Any],
    config: Dict[str, Any],
    *,
    require_kg_decisions: bool,
    require_decisions_as_okf_concepts: bool,
    knowledge_context_receipts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Validates KG context path and required decision references."""
    kg_cfg: Dict[str, Any] = manifest.get("kg", {})
    if kg_cfg and not isinstance(kg_cfg, dict):
        raise ValueError("KNOWLEDGE_GATE manifest field 'kg' must be a mapping.")

    manifest_context_paths: List[str] = _as_string_list(
        kg_cfg.get("context_paths"), "kg.context_paths"
    )
    required_decisions: List[str] = _as_string_list(
        kg_cfg.get("required_decisions"), "kg.required_decisions"
    )
    if require_kg_decisions and not required_decisions:
        raise ValueError("KNOWLEDGE_GATE requires kg.required_decisions for WRF runs.")
    context_cfg: Dict[str, Any] = config.get("KNOWLEDGE_CONTEXT", {})
    config_context_paths: List[str] = _as_string_list(
        context_cfg.get("paths"), "KNOWLEDGE_CONTEXT.paths"
    )

    missing_context_paths: List[str] = [
        path for path in manifest_context_paths if path not in config_context_paths
    ]
    if missing_context_paths:
        raise ValueError(
            "KNOWLEDGE_GATE kg.context_paths must be included in KNOWLEDGE_CONTEXT.paths: "
            + ", ".join(missing_context_paths)
        )

    required_decision_concepts_by_id: Dict[str, List[str]] = _exposed_okf_decision_concepts_by_id(
        knowledge_context_receipts=knowledge_context_receipts,
        required_decisions=required_decisions,
        manifest_context_paths=set(manifest_context_paths),
    )
    missing_decisions: List[str] = [
        decision
        for decision in required_decisions
        if not required_decision_concepts_by_id.get(decision)
    ]
    if require_decisions_as_okf_concepts and missing_decisions:
        raise ValueError(
            "KNOWLEDGE_GATE required KG decisions are not exposed as OKF Decision concept ids: "
            + ", ".join(missing_decisions)
        )
    required_decision_concept_ids: List[str] = list(
        dict.fromkeys(
            concept_id
            for concepts in required_decision_concepts_by_id.values()
            for concept_id in concepts
        )
    )

    return {
        "kg_decision_ids": required_decisions,
        "required_decision_concept_ids": required_decision_concept_ids,
        "required_decision_concepts_by_id": required_decision_concepts_by_id,
        "required_decisions_present": 1,
        "kg_context_paths": manifest_context_paths,
    }


def _validate_fixtures(
    manifest: Dict[str, Any],
    *,
    require_train_holdout: bool,
    require_fixture_files: bool,
    manifest_path: Path,
    base_dirs: Iterable[Path],
) -> Dict[str, Any]:
    """Validates fixture role separation and returns fixture receipts."""
    fixtures: Dict[str, Any] = manifest.get("fixtures", {})
    if fixtures and not isinstance(fixtures, dict):
        raise ValueError("KNOWLEDGE_GATE manifest field 'fixtures' must be a mapping.")

    train_cases: List[Dict[str, Any]] = _fixture_case_receipts(
        fixtures.get("train"),
        role="train",
        manifest_path=manifest_path,
        base_dirs=base_dirs,
        require_files=require_fixture_files,
    )
    holdout_cases: List[Dict[str, Any]] = _fixture_case_receipts(
        fixtures.get("holdout"),
        role="holdout",
        manifest_path=manifest_path,
        base_dirs=base_dirs,
        require_files=require_fixture_files,
    )
    private_holdout_cases: List[Dict[str, Any]] = _fixture_case_receipts(
        fixtures.get("private_holdout"),
        role="private_holdout",
        manifest_path=manifest_path,
        base_dirs=base_dirs,
        require_files=False,
    )

    if require_train_holdout and (not train_cases or not holdout_cases):
        raise ValueError("KNOWLEDGE_GATE requires both train and holdout fixtures.")

    train_paths: Set[str] = {
        str(case["resolved_path"]) for case in train_cases if case.get("resolved_path")
    }
    holdout_paths: Set[str] = {
        str(case["resolved_path"]) for case in holdout_cases if case.get("resolved_path")
    }
    overlap: Set[str] = train_paths.intersection(holdout_paths)
    if overlap:
        raise ValueError(
            "KNOWLEDGE_GATE train and holdout fixtures must be disjoint: "
            + ", ".join(sorted(overlap))
        )

    cases: Dict[str, List[Dict[str, Any]]] = {
        "train": train_cases,
        "holdout": holdout_cases,
        "private_holdout": private_holdout_cases,
    }
    traceable_train_fixture_names: List[str] = _fixture_names_for_prompt(
        {"cases": cases},
        role="train",
        max_names=MAX_TRACEABLE_TRAIN_FIXTURE_NAMES,
    )
    fixture_digest_entries: Dict[str, List[Dict[str, Any]]] = {
        role: [
            {key: value for key, value in receipt.items() if key != "resolved_path"}
            for receipt in receipts
        ]
        for role, receipts in cases.items()
    }
    return {
        "train_cases": len(train_cases),
        "holdout_cases": len(holdout_cases),
        "private_holdout_cases": len(private_holdout_cases),
        "traceable_train_fixture_names": traceable_train_fixture_names,
        "traceable_train_fixture_names_truncated": (
            1 if len(train_cases) > len(traceable_train_fixture_names) else 0
        ),
        "fixture_receipts_sha256": _sha256_bytes(
            json.dumps(fixture_digest_entries, sort_keys=True, allow_nan=False).encode("utf-8")
        ),
        "cases": cases,
    }


def _fixture_case_receipts(
    value: Any,
    *,
    role: str,
    manifest_path: Path,
    base_dirs: Iterable[Path],
    require_files: bool,
) -> List[Dict[str, Any]]:
    """Returns validated fixture case receipts."""
    if value is None:
        return []
    root: Optional[Path] = None
    cases_value: Any = value
    if isinstance(value, dict):
        root_value: Any = value.get("root")
        if root_value is not None and not _is_placeholder(root_value):
            root = Path(str(root_value)).expanduser()
            if not root.is_absolute():
                root = manifest_path.parent / root
        cases_value = value.get("cases", [])

    if not isinstance(cases_value, list):
        raise ValueError("KNOWLEDGE_GATE fixtures must be lists or mappings with cases.")

    receipts: List[Dict[str, Any]] = []
    seen_names: Set[str] = set()
    seen_normalized_names: Set[str] = set()
    seen_paths: Set[str] = set()
    for index, item in enumerate(cases_value, start=1):
        if isinstance(item, dict):
            name: str = str(item.get("name", f"{role}_{index}"))
            path_value: Any = item.get("path")
        else:
            name = str(item)
            path_value = item
        if _is_placeholder(name):
            raise ValueError(f"KNOWLEDGE_GATE {role} fixture #{index} needs a name.")
        if name in seen_names:
            raise ValueError(f"KNOWLEDGE_GATE duplicate {role} fixture name: {name}")
        seen_names.add(name)
        normalized_name: str = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
        if normalized_name in seen_normalized_names:
            raise ValueError(f"KNOWLEDGE_GATE duplicate normalized {role} fixture name: {name}")
        seen_normalized_names.add(normalized_name)

        receipt: Dict[str, Any] = {"name": name}
        if path_value is not None:
            raw_path: str = str(path_value)
            if _is_placeholder(raw_path):
                if require_files:
                    raise ValueError(f"KNOWLEDGE_GATE {role} fixture {name!r} path is placeholder.")
            else:
                fixture_path: Path = Path(raw_path).expanduser()
                if fixture_path.is_absolute():
                    candidates: List[Path] = [fixture_path]
                elif root is not None:
                    fixture_path = (root or manifest_path.parent) / fixture_path
                    candidates = [fixture_path]
                else:
                    candidates = [manifest_path.parent / fixture_path]
                    candidates.extend(base_dir / fixture_path for base_dir in base_dirs)
                resolved_fixture_path: Optional[Path] = None
                for candidate in candidates:
                    if candidate.is_file():
                        resolved_fixture_path = candidate
                        break
                if resolved_fixture_path is None:
                    if require_files:
                        raise FileNotFoundError(
                            f"KNOWLEDGE_GATE {role} fixture not found: {raw_path}"
                        )
                else:
                    resolved_key: str = str(resolved_fixture_path.resolve())
                    if resolved_key in seen_paths:
                        raise ValueError(
                            f"KNOWLEDGE_GATE duplicate {role} fixture path: {resolved_key}"
                        )
                    seen_paths.add(resolved_key)
                    receipt["path"] = raw_path
                    receipt["resolved_path"] = resolved_key
                    receipt["sha256"] = _sha256_path(resolved_fixture_path)
        elif require_files:
            raise ValueError(f"KNOWLEDGE_GATE {role} fixture {name!r} needs a path.")
        receipts.append(receipt)
    return receipts


def _fixture_names_for_prompt(
    fixture_summary: Dict[str, Any],
    *,
    role: str,
    max_names: int = MAX_TRACEABLE_TRAIN_FIXTURE_NAMES,
) -> List[str]:
    """Returns bounded fixture case names that may be shown to the model."""
    cases: Any = fixture_summary.get("cases", {})
    if not isinstance(cases, dict):
        return []
    role_cases: Any = cases.get(role, [])
    if not isinstance(role_cases, list):
        return []

    names: List[str] = []
    for receipt in role_cases:
        if not isinstance(receipt, dict):
            continue
        name: str = str(receipt.get("name", "")).strip()
        if name:
            names.append(name)
        if len(names) >= max_names:
            break
    return names


def _build_prompt_context(receipt_data: Dict[str, Any], receipt_sha256: str) -> str:
    """Builds a compact prompt block from gate receipt data."""
    wrf_target: Dict[str, Any] = receipt_data.get("wrf_target", {})
    source_counts: Dict[str, Any] = receipt_data.get("source_counts", {})
    fixture_summary: Dict[str, Any] = receipt_data.get("fixture_summary", {})
    okf_concept_ids: List[str] = [
        str(receipt["okf_concept_id"])
        for receipt in receipt_data.get("knowledge_context_receipts", [])
        if receipt.get("okf_concept_id")
    ]
    fixture_prompt_summary: Dict[str, Any] = {
        "train_cases": fixture_summary.get("train_cases", 0),
        "holdout_cases": fixture_summary.get("holdout_cases", 0),
        "private_holdout_cases": fixture_summary.get("private_holdout_cases", 0),
        "train_fixture_names": fixture_summary.get("traceable_train_fixture_names", []),
        "train_fixture_names_truncated": fixture_summary.get(
            "traceable_train_fixture_names_truncated", 0
        ),
        "fixture_receipts_sha256": fixture_summary.get("fixture_receipts_sha256"),
    }
    decisions: List[str] = receipt_data.get("kg_decision_ids", [])
    required_decision_concept_ids: List[str] = receipt_data.get("required_decision_concept_ids", [])
    lines: List[str] = [
        "## WRF Knowledge Gate Receipt",
        "This is a file-based CodeEvolve preflight receipt, not a live KG query.",
        f"- gate_passed: `{receipt_data.get('gate_passed')}`",
        f"- domain: `{receipt_data.get('domain')}`",
        f"- manifest_sha256: `{receipt_data.get('manifest_sha256')}`",
        f"- receipt_sha256: `{receipt_sha256}`",
        f"- wrf_commit: `{wrf_target.get('wrf_commit')}`",
        f"- physics_family: `{wrf_target.get('physics_family')}`",
        f"- scheme_module: `{wrf_target.get('scheme_module')}`",
        f"- driver_module: `{wrf_target.get('driver_module')}`",
        f"- entrypoint: `{wrf_target.get('entrypoint')}`",
        f"- source_counts: `{json.dumps(source_counts, sort_keys=True)}`",
        f"- fixture_summary: `{json.dumps(fixture_prompt_summary, sort_keys=True)}`",
        f"- okf_concept_ids: `{', '.join(okf_concept_ids)}`",
        f"- kg_decision_ids: `{', '.join(decisions)}`",
        f"- required_decision_concept_ids: `{', '.join(required_decision_concept_ids)}`",
        "Physical semantic changes still require a KG challenge or decision before acceptance.",
    ]
    return "\n".join(lines)


def _build_static_policy(
    gate_cfg: Dict[str, Any],
    *,
    domain: str,
    evolve_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Builds candidate static-policy settings stored in the gate receipt."""
    static_policy_cfg: Any = gate_cfg.get("static_policy", {})
    if static_policy_cfg and not isinstance(static_policy_cfg, dict):
        raise ValueError("KNOWLEDGE_GATE.static_policy must be a mapping.")
    static_policy: Dict[str, Any] = static_policy_cfg if isinstance(static_policy_cfg, dict) else {}

    forbidden_patterns: Dict[str, str] = (
        dict(DEFAULT_WRF_FORBIDDEN_PATTERNS) if domain == "wrf_single_physics" else {}
    )
    configured_patterns: Any = static_policy.get("forbidden_patterns")
    if configured_patterns is not None:
        if not isinstance(configured_patterns, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in configured_patterns.items()
        ):
            raise ValueError("KNOWLEDGE_GATE.static_policy.forbidden_patterns must be a mapping.")
        forbidden_patterns.update(configured_patterns)
    markers: Dict[str, str] = evolve_config.get("markers", {})
    return {
        "enabled": _as_bool(static_policy.get("enabled"), domain == "wrf_single_physics"),
        "failure_code": int(static_policy.get("failure_code", 16)),
        "knowledge_failure_code": int(static_policy.get("knowledge_failure_code", 17)),
        "mixed_failure_code": int(static_policy.get("mixed_failure_code", 18)),
        "forbidden_patterns": forbidden_patterns,
        "scan_scope": str(
            static_policy.get(
                "scan_scope", "evolve_block" if domain == "wrf_single_physics" else "whole_file"
            )
        ),
        "strip_fortran_comments": _as_bool(
            static_policy.get("strip_fortran_comments"), domain == "wrf_single_physics"
        ),
        "evolve_start_marker": markers.get("evolve_start_marker", DEFAULT_EVOLVE_START_MARKER),
        "evolve_end_marker": markers.get("evolve_end_marker", DEFAULT_EVOLVE_END_MARKER),
    }


def _default_candidate_enforcements(
    *,
    default_policy: str,
    domain: str,
    require_knowledge_context: bool,
    require_okf_context: bool,
) -> List[str]:
    """Returns default candidate semantic-policy enforcement modes."""
    if default_policy != "reject_without_kg_decision":
        return []
    enforcements: List[str] = [_CONFIGURED_KG_DECISION_ENFORCEMENT]
    if domain == "wrf_single_physics" and require_knowledge_context and require_okf_context:
        enforcements.append(_DECLARED_OKF_USE_ENFORCEMENT)
    return enforcements


def _validate_candidate_enforcements(enforcements: List[str], *, label: str) -> None:
    """Fails fast on unsupported semantic candidate enforcement modes."""
    unsupported: List[str] = [
        enforcement
        for enforcement in enforcements
        if enforcement not in _ALLOWED_CANDIDATE_ENFORCEMENTS
    ]
    if unsupported:
        raise ValueError(f"{label} contains unsupported value(s): {', '.join(unsupported)}")


def _build_semantic_change_policy(
    gate_cfg: Dict[str, Any],
    *,
    domain: str,
    require_knowledge_context: bool,
    require_okf_context: bool,
) -> Dict[str, Any]:
    """Builds candidate semantic-policy settings stored in the gate receipt."""
    configured_policy: Any = gate_cfg.get("semantic_change_policy")
    if configured_policy is not None and not isinstance(configured_policy, dict):
        raise ValueError("KNOWLEDGE_GATE.semantic_change_policy must be a mapping.")

    policy_default: str = (
        "reject_without_kg_decision"
        if domain == "wrf_single_physics"
        else "allow_without_kg_decision"
    )
    if isinstance(configured_policy, dict) and "default" in configured_policy:
        policy_default = str(configured_policy["default"])
    semantic_policy_override_allowed: bool = False
    semantic_policy_justification: str = ""
    if domain == "wrf_single_physics" and policy_default != "reject_without_kg_decision":
        semantic_policy_override_allowed = _as_bool(
            gate_cfg.get("allow_semantic_policy_override"), False
        )
        semantic_policy_justification = str(
            gate_cfg.get("semantic_policy_justification", "")
        ).strip()
        if not semantic_policy_override_allowed or _is_placeholder(semantic_policy_justification):
            raise ValueError(
                "WRF KNOWLEDGE_GATE semantic policy override requires "
                "allow_semantic_policy_override=true and semantic_policy_justification."
            )
    default_enforcements: List[str] = _default_candidate_enforcements(
        default_policy=policy_default,
        domain=domain,
        require_knowledge_context=require_knowledge_context,
        require_okf_context=require_okf_context,
    )
    semantic_policy: Dict[str, Any] = {
        "default": policy_default,
        "candidate_enforcement": default_enforcements,
    }
    if semantic_policy_override_allowed:
        semantic_policy["semantic_policy_override_allowed"] = 1
        semantic_policy["semantic_policy_justification"] = semantic_policy_justification
    if configured_policy is None:
        _validate_candidate_enforcements(
            semantic_policy["candidate_enforcement"],
            label="semantic_change_policy.candidate_enforcement",
        )
        return semantic_policy

    semantic_policy.update(configured_policy)
    configured_enforcements: List[str] = _as_string_list(
        configured_policy.get("candidate_enforcement"),
        "semantic_change_policy.candidate_enforcement",
    )
    semantic_policy["candidate_enforcement"] = list(
        dict.fromkeys(default_enforcements + configured_enforcements)
    )
    if semantic_policy_override_allowed:
        semantic_policy["semantic_policy_override_allowed"] = 1
        semantic_policy["semantic_policy_justification"] = semantic_policy_justification
    _validate_candidate_enforcements(
        semantic_policy["candidate_enforcement"],
        label="semantic_change_policy.candidate_enforcement",
    )
    return semantic_policy


def _extract_evolve_block(code: str, *, start_marker: str, end_marker: str) -> Optional[str]:
    """Extracts the configured EVOLVE block from candidate code."""
    start_index: int = code.find(start_marker)
    if start_index < 0:
        return None
    body_start: int = start_index + len(start_marker)
    end_index: int = code.find(end_marker, body_start)
    if end_index < 0:
        return None
    return code[body_start:end_index]


def _strip_fortran_comments_and_strings(code: str) -> str:
    """Removes Fortran comments and string contents for conservative token scans."""
    stripped_lines: List[str] = []
    for line in code.splitlines():
        output_chars: List[str] = []
        quote_char: Optional[str] = None
        index: int = 0
        while index < len(line):
            char: str = line[index]
            if quote_char is None and char == "!":
                break
            if quote_char is None and char in {"'", '"'}:
                quote_char = char
                output_chars.append(" ")
            elif quote_char == char:
                if index + 1 < len(line) and line[index + 1] == char:
                    index += 1
                else:
                    quote_char = None
                output_chars.append(" ")
            elif quote_char is None:
                output_chars.append(char)
            else:
                output_chars.append(" ")
            index += 1
        stripped_lines.append("".join(output_chars))
    return "\n".join(stripped_lines)


def validate_candidate_static_policy(code: str, receipt_data: Dict[str, Any]) -> List[str]:
    """Returns static-policy rejection reasons for candidate code.

    Args:
        code: Candidate source code.
        receipt_data: Knowledge-gate receipt data containing ``static_policy``.

    Returns:
        Rejection reason strings. An empty list means the candidate passed.
    """
    static_policy: Dict[str, Any] = receipt_data.get("static_policy", {})
    if not _as_bool(static_policy.get("enabled"), False):
        return []

    scan_code: str = code
    scan_scope: str = str(static_policy.get("scan_scope", "whole_file"))
    if scan_scope == "evolve_block":
        evolve_block: Optional[str] = _extract_evolve_block(
            code,
            start_marker=str(static_policy.get("evolve_start_marker", DEFAULT_EVOLVE_START_MARKER)),
            end_marker=str(static_policy.get("evolve_end_marker", DEFAULT_EVOLVE_END_MARKER)),
        )
        if evolve_block is None:
            return ["static_policy scan_scope='evolve_block' could not find EVOLVE block markers"]
        scan_code = evolve_block
    elif scan_scope != "whole_file":
        return [f"static_policy.scan_scope {scan_scope!r} is unsupported"]
    if _as_bool(static_policy.get("strip_fortran_comments"), False):
        scan_code = _strip_fortran_comments_and_strings(scan_code)

    rejections: List[str] = []
    forbidden_patterns: Dict[str, str] = static_policy.get("forbidden_patterns", {})
    if not isinstance(forbidden_patterns, dict):
        return ["static_policy.forbidden_patterns must be a mapping"]
    for name, pattern in forbidden_patterns.items():
        try:
            if re.search(str(pattern), scan_code):
                rejections.append(f"forbidden pattern {name!r} matched")
        except re.error as err:
            rejections.append(f"invalid forbidden pattern {name!r}: {err}")
    return rejections


def _semantic_policy_enforcements(semantic_policy: Dict[str, Any]) -> List[str]:
    """Returns candidate-level semantic policy enforcement modes."""
    enforcements: List[str] = _as_string_list(
        semantic_policy.get("candidate_enforcement"),
        "semantic_change_policy.candidate_enforcement",
    )
    if enforcements:
        _validate_candidate_enforcements(
            enforcements,
            label="semantic_change_policy.candidate_enforcement",
        )
        return enforcements
    if str(semantic_policy.get("default", "")) == "reject_without_kg_decision":
        return [_CONFIGURED_KG_DECISION_ENFORCEMENT]
    return []


def _required_decision_concepts_by_id_for_candidate(
    *,
    receipt_data: Dict[str, Any],
    context_available: List[Dict[str, Any]],
    decision_ids: List[str],
) -> Dict[str, List[str]]:
    """Returns candidate-valid required decision concepts, keyed by decision id."""
    manifest_context_paths: Set[str] = {
        str(path) for path in receipt_data.get("kg_context_paths", []) if str(path).strip()
    }
    if decision_ids and not manifest_context_paths:
        return {decision_id: [] for decision_id in decision_ids}
    return required_decision_concepts_by_id(
        context_available=context_available,
        decision_ids=decision_ids,
        manifest_context_paths=manifest_context_paths,
        configured_by_id=receipt_data.get("required_decision_concepts_by_id"),
        require_configured_by_id=bool(decision_ids),
    )


def _validate_declared_okf_concept_use(
    *,
    code: str,
    model_msg: Optional[str],
    receipt_data: Dict[str, Any],
) -> List[str]:
    """Returns rejection reasons for missing candidate-level OKF usage declarations."""
    context_available: List[Dict[str, Any]] = okf_context_available_from_receipts(
        receipt_data.get("knowledge_context_receipts", [])
    )
    if not context_available:
        return ["semantic_change_policy requires exposed OKF concept ids for candidate use"]

    declared, declaration_present, explicit_none = declared_okf_concept_use(
        model_msg=model_msg,
        context_available=context_available,
    )
    if not declaration_present:
        return [
            "semantic_change_policy requires a KNOWLEDGE USE section before the first "
            "SEARCH/REPLACE block"
        ]
    if explicit_none:
        return ["semantic_change_policy requires a relevant OKF concept declaration"]
    if not declared:
        return ["semantic_change_policy requires declared use of an exposed okf_concept_id"]

    weak_usage: List[str] = []
    require_evidence_traceability: bool = (
        str(receipt_data.get("domain", "")) == "wrf_single_physics"
    )
    for item in declared:
        rejection: Optional[str] = declared_usage_traceability_rejection(
            str(item["usage"]),
            code=code,
            model_msg=model_msg,
            fixture_summary=receipt_data.get("fixture_summary"),
            require_evidence_traceability=require_evidence_traceability,
        )
        if rejection:
            weak_usage.append(f"{item['concept_id']} ({rejection})")
    if weak_usage:
        return [
            "semantic_change_policy requires declared OKF use to include reason= and "
            "symbol=/diff=/fixture=/metric= traceability for: " + ", ".join(weak_usage)
        ]

    decision_ids: List[str] = receipt_data.get("kg_decision_ids", [])
    required_concepts_by_id: Dict[str, List[str]] = _required_decision_concepts_by_id_for_candidate(
        receipt_data=receipt_data,
        context_available=context_available,
        decision_ids=decision_ids,
    )
    if decision_ids:
        decisions_without_exposed_concepts: List[str] = [
            decision_id
            for decision_id in decision_ids
            if not required_concepts_by_id.get(decision_id)
        ]
        if decisions_without_exposed_concepts:
            return [
                "semantic_change_policy requires required KG decisions to be exposed as "
                "OKF Decision concept ids: " + ", ".join(decisions_without_exposed_concepts)
            ]

        declared_ids: Set[str] = {str(item["concept_id"]) for item in declared}
        missing_declared_decisions: List[str] = [
            decision_id
            for decision_id, concept_ids in required_concepts_by_id.items()
            if not declared_ids.intersection(concept_ids)
        ]
        if missing_declared_decisions:
            return [
                "semantic_change_policy requires declared use of every required KG decision "
                "okf_concept_id: " + ", ".join(missing_declared_decisions)
            ]
    return []


def validate_candidate_acceptance_policy_by_kind(
    code: str,
    receipt_data: Dict[str, Any],
    *,
    model_msg: Optional[str] = None,
    require_model_msg_knowledge_use: bool = False,
) -> Dict[str, List[str]]:
    """Returns candidate rejection reasons grouped by policy source."""
    static_rejections: List[str] = validate_candidate_static_policy(code, receipt_data)
    knowledge_rejections: List[str] = []
    semantic_policy: Dict[str, Any] = receipt_data.get("semantic_change_policy", {})
    enforcements: List[str] = _semantic_policy_enforcements(semantic_policy)
    decision_ids: List[str] = receipt_data.get("kg_decision_ids", [])
    required_decisions_present: bool = _as_bool(
        receipt_data.get("required_decisions_present"), False
    )
    if _CONFIGURED_KG_DECISION_ENFORCEMENT in enforcements and (
        not decision_ids or not required_decisions_present
    ):
        knowledge_rejections.append("semantic_change_policy requires configured KG decision ids")
    if _DECLARED_OKF_USE_ENFORCEMENT in enforcements and (
        require_model_msg_knowledge_use or model_msg is not None
    ):
        knowledge_rejections.extend(
            _validate_declared_okf_concept_use(
                code=code,
                model_msg=model_msg,
                receipt_data=receipt_data,
            )
        )
    return {
        "static": static_rejections,
        "knowledge": knowledge_rejections,
    }


def validate_candidate_acceptance_policy(
    code: str,
    receipt_data: Dict[str, Any],
    *,
    model_msg: Optional[str] = None,
    require_model_msg_knowledge_use: bool = False,
) -> List[str]:
    """Returns knowledge-gate rejection reasons for candidate acceptance."""
    rejections_by_kind: Dict[str, List[str]] = validate_candidate_acceptance_policy_by_kind(
        code,
        receipt_data,
        model_msg=model_msg,
        require_model_msg_knowledge_use=require_model_msg_knowledge_use,
    )
    return rejections_by_kind["static"] + rejections_by_kind["knowledge"]


def run_knowledge_gate(
    config: Dict[str, Any],
    args: Dict[str, Any],
    base_dirs: Iterable[Path],
) -> Optional[KnowledgeGateReceipt]:
    """Runs optional file-based knowledge-gate preflight checks.

    Args:
        config: Full CodeEvolve configuration dictionary.
        args: Runtime argument dictionary containing at least ``out_dir`` when the
            gate is enabled.
        base_dirs: Directories used to resolve relative manifest paths.

    Returns:
        A receipt when ``KNOWLEDGE_GATE`` is enabled, otherwise ``None``.

    Raises:
        FileNotFoundError: If a required manifest is missing.
        ValueError: If evidence, KG, Graphify, target, or fixture contracts are
            insufficient for the configured gate.
    """
    base_dir_list: List[Path] = list(base_dirs)
    gate_cfg: Any = config.get("KNOWLEDGE_GATE")
    if gate_cfg is None:
        return None
    if not isinstance(gate_cfg, dict):
        raise ValueError("KNOWLEDGE_GATE must be a mapping.")
    if not _as_bool(gate_cfg.get("enabled"), True):
        return None

    required: bool = _as_bool(gate_cfg.get("required"), True)
    domain: str = str(gate_cfg.get("domain", "generic"))
    manifest_value: Any = gate_cfg.get("manifest")
    if manifest_value is None or not str(manifest_value).strip():
        if not required:
            return None
        raise ValueError("KNOWLEDGE_GATE.manifest is required when the gate is enabled.")

    manifest_path: Optional[Path] = _resolve_path(str(manifest_value), base_dir_list)
    if manifest_path is None or not manifest_path.is_file():
        if not required:
            return None
        raise FileNotFoundError(f"KNOWLEDGE_GATE manifest not found: {manifest_value}")

    with manifest_path.open("r", encoding="utf-8") as manifest_file:
        manifest: Any = yaml.safe_load(manifest_file) or {}
    if not isinstance(manifest, dict):
        raise ValueError("KNOWLEDGE_GATE manifest must be a YAML mapping.")

    require_exact_target: bool = _as_bool(gate_cfg.get("require_exact_target"), True)
    require_knowledge_context: bool = _as_bool(
        gate_cfg.get("require_knowledge_context"), domain == "wrf_single_physics"
    )
    require_graphify_export: bool = _as_bool(
        gate_cfg.get("require_graphify_export"), domain == "wrf_single_physics"
    )
    require_train_holdout: bool = _as_bool(
        gate_cfg.get("require_train_holdout"), domain == "wrf_single_physics"
    )
    require_source_files: bool = _as_bool(
        gate_cfg.get("require_source_files"), domain == "wrf_single_physics"
    )
    require_source_digests: bool = _as_bool(
        gate_cfg.get("require_source_digests"), domain == "wrf_single_physics"
    )
    require_fixture_files: bool = _as_bool(
        gate_cfg.get("require_fixture_files"), domain == "wrf_single_physics"
    )
    require_kg_decisions: bool = _as_bool(
        gate_cfg.get("require_kg_decisions"), domain == "wrf_single_physics"
    )
    require_okf_context: bool = _as_bool(
        gate_cfg.get("require_okf_context"), domain == "wrf_single_physics"
    )
    allow_non_okf_context: bool = _as_bool(gate_cfg.get("allow_non_okf_context"), False)
    non_okf_context_justification: str = str(
        gate_cfg.get("non_okf_context_justification", "")
    ).strip()
    wrf_non_okf_context_requested: bool = domain == "wrf_single_physics" and (
        not require_knowledge_context or not require_okf_context
    )
    if wrf_non_okf_context_requested:
        if not allow_non_okf_context or _is_placeholder(non_okf_context_justification):
            raise ValueError(
                "WRF KNOWLEDGE_GATE disabling knowledge or OKF context requires "
                "allow_non_okf_context=true and non_okf_context_justification."
            )
    min_sources: Dict[str, int] = (
        dict(DEFAULT_WRF_MIN_SOURCES) if domain == "wrf_single_physics" else {}
    )
    min_sources.update(
        {str(key): int(value) for key, value in gate_cfg.get("min_sources", {}).items()}
    )

    knowledge_context_summary: Dict[str, Any] = {
        "knowledge_context_receipts": [],
        "okf_required": 0,
        "okf_bundle_root": None,
        "knowledge_context_sha256": None,
        "non_okf_context_allowed": 1 if allow_non_okf_context else 0,
        "non_okf_context_justification": non_okf_context_justification,
    }
    if require_knowledge_context:
        knowledge_context_summary = _validate_knowledge_context_config(
            config,
            base_dirs=base_dir_list,
            require_okf_context=require_okf_context,
        )
        knowledge_context_summary["non_okf_context_allowed"] = 1 if allow_non_okf_context else 0
        knowledge_context_summary["non_okf_context_justification"] = non_okf_context_justification
    if require_graphify_export:
        _validate_graphify_export_config(config)

    target_summary: Dict[str, Any] = _validate_target(
        _require_mapping(manifest, "target"),
        require_exact_target=require_exact_target,
        require_source_files=require_source_files,
        manifest_path=manifest_path,
    )
    source_summary: Dict[str, Any] = _validate_sources(
        manifest,
        min_sources=min_sources,
        target_summary=target_summary,
        require_source_files=require_source_files,
        require_source_digests=require_source_digests,
        manifest_path=manifest_path,
    )
    kg_summary: Dict[str, Any] = _validate_kg_links(
        manifest,
        config,
        require_kg_decisions=require_kg_decisions,
        require_decisions_as_okf_concepts=(
            require_kg_decisions and require_knowledge_context and require_okf_context
        ),
        knowledge_context_receipts=knowledge_context_summary["knowledge_context_receipts"],
    )
    fixture_summary: Dict[str, Any] = _validate_fixtures(
        manifest,
        require_train_holdout=require_train_holdout,
        require_fixture_files=require_fixture_files,
        manifest_path=manifest_path,
        base_dirs=base_dir_list,
    )
    static_policy: Dict[str, Any] = _build_static_policy(
        gate_cfg,
        domain=domain,
        evolve_config=config.get("EVOLVE_CONFIG", {}),
    )
    semantic_change_policy: Dict[str, Any] = _build_semantic_change_policy(
        gate_cfg,
        domain=domain,
        require_knowledge_context=require_knowledge_context,
        require_okf_context=require_okf_context,
    )

    receipt_data: Dict[str, Any] = {
        "schema_version": 1,
        "gate_passed": 1,
        "domain": domain,
        "manifest_path": str(manifest_path),
        "manifest_sha256": _sha256_path(manifest_path),
        "wrf_target": target_summary,
        "source_counts": source_summary["source_counts"],
        "source_ids_by_kind": source_summary["source_ids_by_kind"],
        "source_receipts": source_summary["source_receipts"],
        "fixture_summary": fixture_summary,
        "knowledge_context_receipts": knowledge_context_summary["knowledge_context_receipts"],
        "okf_required": knowledge_context_summary["okf_required"],
        "okf_bundle_root": knowledge_context_summary["okf_bundle_root"],
        "knowledge_context_sha256": knowledge_context_summary["knowledge_context_sha256"],
        "non_okf_context_allowed": knowledge_context_summary["non_okf_context_allowed"],
        "non_okf_context_justification": knowledge_context_summary["non_okf_context_justification"],
        "kg_context_paths": kg_summary["kg_context_paths"],
        "kg_decision_ids": kg_summary["kg_decision_ids"],
        "required_decision_concept_ids": kg_summary["required_decision_concept_ids"],
        "required_decision_concepts_by_id": kg_summary["required_decision_concepts_by_id"],
        "required_decisions_present": kg_summary["required_decisions_present"],
        "semantic_change_policy": semantic_change_policy,
        "static_policy": static_policy,
    }

    out_dir: Path = Path(args["out_dir"])
    receipt_output: Path = Path(str(gate_cfg.get("receipt_output", "knowledge_gate/receipt.json")))
    if not receipt_output.is_absolute():
        receipt_output = out_dir / receipt_output
    receipt_output.parent.mkdir(parents=True, exist_ok=True)
    receipt_output.write_bytes(_json_bytes(receipt_data))
    receipt_sha256: str = _sha256_path(receipt_output)
    prompt_context: str = _build_prompt_context(receipt_data, receipt_sha256)

    return KnowledgeGateReceipt(
        data=receipt_data,
        output_path=receipt_output,
        receipt_sha256=receipt_sha256,
        prompt_context=prompt_context,
    )
