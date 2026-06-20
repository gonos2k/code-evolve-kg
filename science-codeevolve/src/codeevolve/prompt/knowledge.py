# ===--------------------------------------------------------------------------------------===#
#
# Part of the CodeEvolve Project, under the Apache License v2.0.
# See https://github.com/inter-co/science-codeevolve/blob/main/LICENSE for license information.
# SPDX-License-Identifier: Apache-2.0
#
# ===--------------------------------------------------------------------------------------===#
#
# This file implements optional knowledge-context loading for LLM prompts.
#
# ===--------------------------------------------------------------------------------------===#

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional

import yaml


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
    """Converts a scalar or list configuration value to a string list.

    Args:
        value: The configuration value to normalize.
        key: The configuration key name, used in error messages.

    Returns:
        A list of strings.

    Raises:
        ValueError: If the value cannot be interpreted as a string list.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise ValueError(f"KNOWLEDGE_CONTEXT.{key} must be a string or list of strings.")


def _dedupe_base_dirs(base_dirs: Iterable[Path]) -> List[Path]:
    """Returns base directories without duplicates while preserving order."""
    deduped: List[Path] = []
    seen: set[str] = set()
    for base_dir in base_dirs:
        try:
            key: str = str(base_dir.expanduser().resolve())
        except OSError:
            key = str(base_dir.expanduser())
        if key not in seen:
            seen.add(key)
            deduped.append(base_dir)
    return deduped


def _resolve_context_path(raw_path: str, base_dirs: Iterable[Path]) -> Optional[Path]:
    """Resolves a configured knowledge-context path against candidate base dirs."""
    expanded_path: Path = Path(raw_path).expanduser()
    if expanded_path.is_absolute():
        return expanded_path if expanded_path.exists() else None

    for base_dir in _dedupe_base_dirs(base_dirs):
        candidate: Path = base_dir.expanduser() / expanded_path
        if candidate.exists():
            return candidate
    return None


def _quote_context_text(text: str) -> str:
    """Formats source text as an indented block that cannot close a Markdown fence."""
    stripped: str = text.strip()
    if not stripped:
        return "    (empty)"
    return "\n".join(f"    {line}" if line else "" for line in stripped.splitlines())


def _context_digest(text: str) -> str:
    """Returns a stable digest for a knowledge-context chunk."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def okf_concept_id_from_source(source: str, *, bundle_root: str = "wiki") -> str:
    """Converts a source path into an OKF concept id.

    Args:
        source: Markdown source path, usually from ``KNOWLEDGE_CONTEXT.paths``.
        bundle_root: Optional bundle root prefix to strip from concept ids.

    Returns:
        Bundle-relative OKF concept id without the ``.md`` suffix.
    """
    normalized_source: str = str(source).strip().replace("\\", "/")
    source_path: PurePosixPath = PurePosixPath(normalized_source)
    root_path: PurePosixPath = PurePosixPath(str(bundle_root).strip().replace("\\", "/"))
    source_parts: tuple[str, ...] = source_path.parts
    root_parts: tuple[str, ...] = root_path.parts
    if root_parts and source_parts[: len(root_parts)] == root_parts:
        source_path = PurePosixPath(*source_parts[len(root_parts) :])
    if source_path.suffix == ".md":
        source_path = source_path.with_suffix("")
    return source_path.as_posix()


def parse_okf_frontmatter(text: str, *, label: str) -> Dict[str, Any]:
    """Parses the YAML frontmatter of an OKF-style Markdown document.

    Args:
        text: Markdown document text.
        label: Source label used in error messages.

    Returns:
        Parsed frontmatter mapping.

    Raises:
        ValueError: If frontmatter is missing, malformed, or not a mapping.
    """
    lines: List[str] = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{label} is not OKF-compatible: missing YAML frontmatter.")

    end_index: Optional[int] = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index is None:
        raise ValueError(f"{label} is not OKF-compatible: unterminated YAML frontmatter.")

    try:
        frontmatter: Any = yaml.safe_load("\n".join(lines[1:end_index])) or {}
    except yaml.YAMLError as err:
        raise ValueError(f"{label} is not OKF-compatible: invalid YAML frontmatter.") from err
    if not isinstance(frontmatter, dict):
        raise ValueError(f"{label} is not OKF-compatible: frontmatter must be a mapping.")
    return frontmatter


def validate_okf_document(text: str, *, label: str) -> Dict[str, Any]:
    """Validates the minimal OKF v0.1 concept-document contract.

    OKF is intentionally permissive. For CodeEvolve prompt context we only
    require parseable frontmatter and a non-empty ``type`` field, while
    preserving producer-specific extension fields.

    Args:
        text: Markdown document text.
        label: Source label used in error messages.

    Returns:
        Parsed OKF frontmatter.

    Raises:
        ValueError: If the document lacks the minimal OKF fields.
    """
    frontmatter: Dict[str, Any] = parse_okf_frontmatter(text, label=label)
    if not str(frontmatter.get("type", "")).strip():
        raise ValueError(f"{label} is not OKF-compatible: frontmatter requires non-empty type.")
    return frontmatter


def load_knowledge_context(config: Dict[str, Any], base_dirs: Iterable[Path]) -> Optional[str]:
    """Loads optional knowledge context configured for LLM prompt construction.

    ``KNOWLEDGE_CONTEXT`` is intentionally file-based. CodeEvolve stays decoupled
    from any specific knowledge-base implementation while allowing projects to
    inject selected KG/wiki/source pages into each code-generation prompt.

    Supported configuration:

    ```yaml
    KNOWLEDGE_CONTEXT:
      enabled: true
      title: "WRF KG Context"
      required: true
      require_okf: true
      okf_bundle_root: wiki
      max_chars: 12000
      paths:
        - wiki/overview.md
      inline:
        - "Additional fixed instruction."
    ```

    Args:
        config: Full CodeEvolve configuration dictionary.
        base_dirs: Directories used to resolve relative context paths.

    Returns:
        Formatted context string, or ``None`` when no context is configured.

    Raises:
        FileNotFoundError: If required context files are missing.
        ValueError: If the context configuration is invalid.
    """
    context_cfg: Any = config.get("KNOWLEDGE_CONTEXT")
    if context_cfg is None:
        return None
    if not isinstance(context_cfg, dict):
        raise ValueError("KNOWLEDGE_CONTEXT must be a mapping.")
    if not _as_bool(context_cfg.get("enabled"), True):
        return None

    title: str = str(context_cfg.get("title", "Knowledge Context"))
    required: bool = _as_bool(context_cfg.get("required"), False)
    require_okf: bool = _as_bool(context_cfg.get("require_okf"), False)
    okf_bundle_root: str = str(context_cfg.get("okf_bundle_root", "wiki"))
    max_chars: int = int(context_cfg.get("max_chars", 12000))
    if max_chars < 500:
        raise ValueError("KNOWLEDGE_CONTEXT.max_chars must be at least 500.")

    context_paths: List[str] = _as_string_list(context_cfg.get("paths"), "paths")
    inline_entries: List[str] = _as_string_list(context_cfg.get("inline"), "inline")

    chunks: List[str] = []
    receipts: List[str] = []
    missing_paths: List[str] = []
    empty_sources: List[str] = []
    for context_path in context_paths:
        resolved_path: Optional[Path] = _resolve_context_path(context_path, base_dirs)
        if resolved_path is None or not resolved_path.is_file():
            missing_paths.append(context_path)
            continue

        text: str = resolved_path.read_text(encoding="utf-8")
        if not text.strip():
            empty_sources.append(context_path)
            continue
        okf_frontmatter: Optional[Dict[str, Any]] = None
        if require_okf:
            okf_frontmatter = validate_okf_document(text, label=f"KNOWLEDGE_CONTEXT {context_path}")
        digest: str = _context_digest(text)
        receipts.extend(
            [
                f"- source: {context_path}",
                f"  sha256: {digest}",
                f"  chars: {len(text)}",
            ]
        )
        if okf_frontmatter is not None:
            okf_concept_id: str = okf_concept_id_from_source(
                context_path,
                bundle_root=okf_bundle_root,
            )
            receipts.extend(
                [
                    f"  okf_concept_id: {okf_concept_id}",
                    f"  okf_type: {okf_frontmatter.get('type')}",
                    f"  okf_title: {okf_frontmatter.get('title', '')}",
                ]
            )
        chunks.append(
            "\n".join(
                [
                    f"### Source: {context_path}",
                    f"Receipt: sha256={digest}, chars={len(text)}",
                    _quote_context_text(text),
                ]
            )
        )

    if missing_paths and required:
        raise FileNotFoundError(
            "Required KNOWLEDGE_CONTEXT paths were not found: " + ", ".join(missing_paths)
        )
    if empty_sources and required:
        raise ValueError(
            "Required KNOWLEDGE_CONTEXT sources were empty: " + ", ".join(empty_sources)
        )

    for index, inline_entry in enumerate(inline_entries, start=1):
        source_name: str = f"inline:{index}"
        if not inline_entry.strip():
            if required:
                raise ValueError(f"Required KNOWLEDGE_CONTEXT source was empty: {source_name}")
            continue
        digest = _context_digest(inline_entry)
        receipts.extend(
            [
                f"- source: {source_name}",
                f"  sha256: {digest}",
                f"  chars: {len(inline_entry)}",
            ]
        )
        chunks.append(
            "\n".join(
                [
                    f"### Inline Context {index}",
                    f"Receipt: sha256={digest}, chars={len(inline_entry)}",
                    _quote_context_text(inline_entry),
                ]
            )
        )

    if not chunks:
        if required:
            raise ValueError("KNOWLEDGE_CONTEXT is required but no context was loaded.")
        return None

    context: str = "\n\n".join(
        [
            f"## {title}",
            "This is static CodeEvolve knowledge context loaded from configured files, not a live KG query.",
            "Use this project knowledge while proposing SEARCH/REPLACE changes.",
            "If you use OKF context, add a `KNOWLEDGE USE:` section before the first SEARCH/REPLACE block.",
            "In that section, each declaration line must start with an exposed `okf_concept_id` and include `reason=` plus traceability such as `symbol=`, `diff=`, or `fixture=`. If none is relevant, write `KNOWLEDGE USE: none`.",
            "For WRF single-physics candidates, `symbol=` alone is not enough. Use a generated diff reference such as `diff=SEARCH_REPLACE_1` or an exposed train fixture name from the WRF gate receipt. Do not rely on `metric=` alone for pre-evaluation acceptance.",
            "Treat it as synthesized guidance: raw sources, fixed drivers, and evaluator results remain authoritative.",
            "If this context conflicts with the code contract or correctness gate, preserve the contract and correctness gate.",
            "For WRF physics changes that alter physical semantics, require a KG challenge or decision record before accepting the change.",
            "### Context Receipt",
            *receipts,
            *chunks,
        ]
    )

    if len(context) <= max_chars:
        return context

    truncation_note: str = "\n\n[Knowledge context truncated by KNOWLEDGE_CONTEXT.max_chars.]"
    return context[: max_chars - len(truncation_note)].rstrip() + truncation_note
