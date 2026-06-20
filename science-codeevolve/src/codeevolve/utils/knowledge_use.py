# ===--------------------------------------------------------------------------------------===#
#
# Part of the CodeEvolve Project, under the Apache License v2.0.
# See https://github.com/inter-co/science-codeevolve/blob/main/LICENSE for license information.
# SPDX-License-Identifier: Apache-2.0
#
# ===--------------------------------------------------------------------------------------===#
#
# This file implements candidate-level OKF knowledge-use parsing helpers.
#
# ===--------------------------------------------------------------------------------------===#

import re
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional, Set, Tuple

_TRACEABILITY_FIELD_RE = re.compile(
    r"\b(?P<key>reason|symbol|module|subroutine|diff|fixture|metric)\s*=\s*"
    r"(?P<value>.*?)(?=(?:\s*[;,]\s*|\s+)"
    r"(?:reason|symbol|module|subroutine|diff|fixture|metric)\s*=|$)",
    flags=re.IGNORECASE,
)
_TRACEABILITY_KEYS: Tuple[str, ...] = (
    "symbol",
    "module",
    "subroutine",
    "diff",
    "fixture",
    "metric",
)
_CODE_TRACEABILITY_KEYS: Tuple[str, ...] = ("symbol", "module", "subroutine")
_EVIDENCE_TRACEABILITY_KEYS: Tuple[str, ...] = ("diff", "fixture", "metric")
_DIFF_REFERENCE_RE = re.compile(
    r"^(?:(?:search_?replace|diff|replace)_?)?(?P<index>[1-9][0-9]*)$",
    flags=re.IGNORECASE,
)
_TRACEABILITY_PLACEHOLDERS: Set[str] = {
    "-",
    "--",
    "...",
    "na",
    "n/a",
    "nil",
    "none",
    "null",
    "placeholder",
    "tbd",
    "todo",
    "unknown",
}
_REQUIRED_DECISION_OKF_TYPES: Set[str] = {"decision"}


def _normalized_evidence_value(value: str) -> str:
    """Normalizes traceability values for exact evidence-reference matching."""
    return re.sub(r"[^a-z0-9]+", "_", value.strip().strip("`'\".,;:").lower()).strip("_")


def _strip_usage_bullet(line: str) -> str:
    """Removes a leading Markdown bullet or numbered-list marker."""
    return re.sub(r"^\s*(?:[-*]|\d+[.)])\s+", "", line).strip()


def okf_context_available_from_receipts(receipts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Builds OKF context exposure records from knowledge-context receipts."""
    context_available: List[Dict[str, Any]] = []
    for receipt in receipts:
        concept_id: Optional[str] = receipt.get("okf_concept_id")
        if not concept_id:
            continue
        context_available.append(
            {
                "concept_id": str(concept_id),
                "type": str(receipt.get("okf_type", "")),
                "title": str(receipt.get("okf_title", "")),
                "resource": receipt.get("okf_resource"),
                "source": str(receipt.get("source", "")),
                "sha256": str(receipt.get("sha256", "")),
                "chars": receipt.get("chars", 0),
            }
        )
    return context_available


def okf_context_is_required_decision(context: Dict[str, Any]) -> bool:
    """Returns whether an exposed OKF context can satisfy a required decision."""
    return str(context.get("type", "")).strip().lower() in _REQUIRED_DECISION_OKF_TYPES


def okf_concept_id_matches_decision(concept_id: str, decision_id: str) -> bool:
    """Returns whether an OKF concept id appears to represent a decision id."""
    normalized_concept: str = concept_id.strip().strip("/").lower()
    normalized_decision: str = decision_id.strip().strip("/").lower()
    if not normalized_concept or not normalized_decision:
        return False
    if normalized_concept == normalized_decision:
        return True
    if normalized_concept.endswith(f"/{normalized_decision}"):
        return True
    return PurePosixPath(normalized_concept).stem == normalized_decision


def required_decision_concepts_by_id(
    *,
    context_available: List[Dict[str, Any]],
    decision_ids: List[str],
    manifest_context_paths: Optional[Set[str]] = None,
    configured_by_id: Optional[Any] = None,
    require_configured_by_id: bool = False,
) -> Dict[str, List[str]]:
    """Returns valid exposed OKF Decision concept ids for required decisions.

    Args:
        context_available: OKF context exposure records.
        decision_ids: Required KG decision identifiers.
        manifest_context_paths: Optional source-path allowlist from
            ``kg.context_paths``. When provided, only contexts from those sources
            can satisfy a required decision.
        configured_by_id: Optional receipt map to intersect with computed
            context-derived candidates.
        require_configured_by_id: If true, a missing or malformed receipt map
            returns no valid concepts. This keeps stale/manual receipts from
            widening required-decision matching after preflight.

    Returns:
        Mapping from required decision id to valid concept ids.
    """
    scoped_paths: Optional[Set[str]] = None
    if manifest_context_paths is not None:
        scoped_paths = {str(path) for path in manifest_context_paths if str(path).strip()}

    computed_by_id: Dict[str, List[str]] = {}
    for decision_id in decision_ids:
        computed_ids: List[str] = []
        for context in context_available:
            if scoped_paths is not None and str(context.get("source", "")) not in scoped_paths:
                continue
            concept_id: str = str(context.get("concept_id", ""))
            if okf_context_is_required_decision(context) and okf_concept_id_matches_decision(
                concept_id, decision_id
            ):
                computed_ids.append(concept_id)
        computed_by_id[decision_id] = list(dict.fromkeys(computed_ids))

    if not isinstance(configured_by_id, dict):
        if require_configured_by_id:
            return {decision_id: [] for decision_id in decision_ids}
        return computed_by_id

    valid_by_id: Dict[str, List[str]] = {}
    for decision_id in decision_ids:
        configured_ids: Any = configured_by_id.get(decision_id, [])
        if not isinstance(configured_ids, list):
            configured_ids = []
        computed_ids: Set[str] = set(computed_by_id.get(decision_id, []))
        valid_by_id[decision_id] = list(
            dict.fromkeys(
                str(concept_id)
                for concept_id in configured_ids
                if str(concept_id).strip() and str(concept_id) in computed_ids
            )
        )
    return valid_by_id


def extract_knowledge_use_lines(model_msg: Optional[str]) -> Optional[List[str]]:
    """Extracts lines from a model-declared KNOWLEDGE USE section."""
    if not model_msg:
        return None
    lines: List[str] = model_msg.splitlines()
    first_search_index: Optional[int] = None
    for index, line in enumerate(lines):
        if re.match(r"\s*<<<<<<<\s*SEARCH", line):
            first_search_index = index
            break
    declaration_lines: List[str] = (
        lines[:first_search_index] if first_search_index is not None else lines
    )
    for index, line in enumerate(declaration_lines):
        match = re.match(r"\s*KNOWLEDGE USE\s*:\s*(.*)$", line, flags=re.IGNORECASE)
        if match is None:
            continue
        use_lines: List[str] = []
        first_line: str = match.group(1).strip()
        if first_line:
            use_lines.append(first_line)
        for following_line in declaration_lines[index + 1 :]:
            if re.match(r"\s*##\s+\w", following_line) and use_lines:
                break
            if following_line.strip():
                use_lines.append(following_line.strip())
        return use_lines
    return None


def line_mentions_concept_id(line: str, concept_id: str) -> bool:
    """Returns whether a line mentions an exact OKF concept id."""
    pattern: str = r"(?<![A-Za-z0-9_./-])" + re.escape(concept_id) + r"(?![A-Za-z0-9_./-])"
    return re.search(pattern, line) is not None


def line_declares_concept_id(line: str, concept_id: str) -> bool:
    """Returns whether a KNOWLEDGE USE line starts with an exact OKF concept id."""
    normalized_line: str = _strip_usage_bullet(line)
    pattern: str = r"^" + re.escape(concept_id) + r"(?![A-Za-z0-9_./-])"
    return re.search(pattern, normalized_line) is not None


def knowledge_use_traceability_fields(usage: str) -> Dict[str, str]:
    """Returns non-empty structured fields from a declared knowledge-use line."""
    fields: Dict[str, str] = {}
    for match in _TRACEABILITY_FIELD_RE.finditer(usage):
        key: str = match.group("key").lower()
        value: str = match.group("value").strip().strip(";,")
        if value:
            fields[key] = value
    return fields


def _is_placeholder_traceability_value(value: str) -> bool:
    """Returns whether a traceability value is only a placeholder."""
    normalized: str = re.sub(r"\s+", " ", value.strip().strip("`'\".,;:")).lower()
    if not normalized:
        return True
    if normalized in _TRACEABILITY_PLACEHOLDERS:
        return True
    if re.match(r"^(todo|tbd|unknown|placeholder|none|null|nil|n/?a)\b", normalized):
        return True
    return normalized.startswith("replace with") or normalized.startswith("replace-with")


def declared_usage_traceability(usage: str) -> Dict[str, Any]:
    """Returns structured traceability assessment for a declared usage line."""
    fields: Dict[str, str] = knowledge_use_traceability_fields(usage)
    placeholder_fields: List[str] = [
        key for key, value in fields.items() if _is_placeholder_traceability_value(value)
    ]
    usable_fields: Dict[str, str] = {
        key: value for key, value in fields.items() if key not in placeholder_fields
    }
    missing: List[str] = []
    if not usable_fields.get("reason"):
        missing.append("reason")
    if not any(usable_fields.get(key) for key in _TRACEABILITY_KEYS):
        missing.append("traceability_field")
    return {
        "fields": fields,
        "usable_fields": usable_fields,
        "placeholder_fields": placeholder_fields,
        "traceability_present": 0 if missing else 1,
        "missing": missing,
    }


def declared_usage_has_traceability(usage: str) -> bool:
    """Returns whether a usage line has non-empty reason and traceability fields."""
    return bool(declared_usage_traceability(usage)["traceability_present"])


def _search_replace_block_count(model_msg: Optional[str]) -> int:
    """Returns the number of generated SEARCH/REPLACE blocks."""
    if not model_msg:
        return 0
    return len(re.findall(r"(?m)^\s*<<<<<<<\s*SEARCH\b", model_msg))


def _diff_reference_index(value: str) -> Optional[int]:
    """Returns the referenced SEARCH/REPLACE block index, if parseable."""
    normalized: str = _normalized_evidence_value(value)
    match = _DIFF_REFERENCE_RE.match(normalized)
    if match is None:
        return None
    return int(match.group("index"))


def _fixture_reference_values(fixture_summary: Optional[Dict[str, Any]]) -> Set[str]:
    """Returns exact fixture identifiers that declarations may reference."""
    values: Set[str] = set()
    if not fixture_summary:
        return values
    traceable_names: Any = fixture_summary.get("traceable_train_fixture_names")
    if not isinstance(traceable_names, list):
        return values
    for raw_name in traceable_names:
        if not raw_name:
            continue
        name: str = str(raw_name)
        values.add(_normalized_evidence_value(name))
        values.add(_normalized_evidence_value(f"train:{name}"))
        values.add(_normalized_evidence_value(f"train/{name}"))
    values.discard("")
    return values


def _metric_reference_values(eval_metrics: Optional[Dict[str, Any]]) -> Set[str]:
    """Returns exact evaluator metric keys that declarations may reference."""
    if eval_metrics is None:
        return set()
    return {
        normalized
        for normalized in (_normalized_evidence_value(str(key)) for key in eval_metrics.keys())
        if normalized
    }


def declared_usage_evidence_validation(
    usage: str,
    *,
    model_msg: Optional[str] = None,
    fixture_summary: Optional[Dict[str, Any]] = None,
    eval_metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Returns validation details for diff, fixture, and metric traceability."""
    fields: Dict[str, str] = declared_usage_traceability(usage)["usable_fields"]
    evidence_fields: Dict[str, str] = {
        key: value for key, value in fields.items() if key in _EVIDENCE_TRACEABILITY_KEYS
    }
    valid: List[str] = []
    invalid: List[str] = []
    unvalidated: List[str] = []

    diff_value: Optional[str] = evidence_fields.get("diff")
    if diff_value:
        diff_count: int = _search_replace_block_count(model_msg)
        diff_index: Optional[int] = _diff_reference_index(diff_value)
        if diff_count <= 0:
            unvalidated.append(f"diff={diff_value!r} cannot be validated without a model diff")
        elif diff_index is None:
            invalid.append(f"diff={diff_value!r} is not a SEARCH/REPLACE block reference")
        elif diff_index > diff_count:
            invalid.append(
                f"diff={diff_value!r} references SEARCH/REPLACE block {diff_index}, "
                f"but only {diff_count} block(s) were generated"
            )
        else:
            valid.append("diff")

    fixture_value: Optional[str] = evidence_fields.get("fixture")
    if fixture_value:
        fixture_values: Set[str] = _fixture_reference_values(fixture_summary)
        normalized_fixture: str = _normalized_evidence_value(fixture_value)
        if not fixture_values:
            unvalidated.append(
                f"fixture={fixture_value!r} cannot be validated without "
                "traceable train fixture names"
            )
        elif normalized_fixture not in fixture_values:
            invalid.append(f"fixture={fixture_value!r} is not present in fixture receipts")
        else:
            valid.append("fixture")

    metric_value: Optional[str] = evidence_fields.get("metric")
    if metric_value:
        metric_values: Set[str] = _metric_reference_values(eval_metrics)
        normalized_metric: str = _normalized_evidence_value(metric_value)
        if eval_metrics is None:
            unvalidated.append(
                f"metric={metric_value!r} cannot be validated before evaluator metrics exist"
            )
        elif normalized_metric not in metric_values:
            invalid.append(f"metric={metric_value!r} is not present in evaluator metrics")
        else:
            valid.append("metric")

    return {
        "evidence_fields": evidence_fields,
        "evidence_present": 1 if evidence_fields else 0,
        "validated_evidence_fields": valid,
        "validated_evidence_present": 1 if valid else 0,
        "invalid_evidence": invalid,
        "unvalidated_evidence": unvalidated,
    }


def declared_usage_traceability_rejection(
    usage: str,
    *,
    code: Optional[str] = None,
    model_msg: Optional[str] = None,
    fixture_summary: Optional[Dict[str, Any]] = None,
    eval_metrics: Optional[Dict[str, Any]] = None,
    require_evidence_traceability: bool = False,
) -> Optional[str]:
    """Returns a rejection reason for weak declared OKF usage, if any."""
    traceability: Dict[str, Any] = declared_usage_traceability(usage)
    fields: Dict[str, str] = traceability["usable_fields"]
    missing: List[str] = traceability["missing"]
    placeholder_fields: List[str] = traceability["placeholder_fields"]
    rejection_parts: List[str] = []
    if missing:
        rejection_parts.append("missing " + ", ".join(missing))
    evidence_validation: Dict[str, Any] = declared_usage_evidence_validation(
        usage,
        model_msg=model_msg,
        fixture_summary=fixture_summary,
        eval_metrics=eval_metrics,
    )
    if require_evidence_traceability and not evidence_validation["evidence_present"]:
        rejection_parts.append("missing evidence_traceability_field")
    elif require_evidence_traceability and not evidence_validation["validated_evidence_present"]:
        rejection_parts.append("missing validated_evidence_traceability_field")
        rejection_parts.extend(evidence_validation["unvalidated_evidence"])

    rejection_parts.extend(evidence_validation["invalid_evidence"])

    if code is not None:
        lowered_code: str = code.lower()
        for key in _CODE_TRACEABILITY_KEYS:
            value: Optional[str] = fields.get(key)
            if not value:
                continue
            token_pattern: str = (
                r"(?<![A-Za-z0-9_])" + re.escape(value.lower()) + r"(?![A-Za-z0-9_])"
            )
            if re.search(token_pattern, lowered_code) is None:
                rejection_parts.append(f"{key}={value!r} is not present in candidate code")

    blocking_placeholders: List[str] = []
    if "reason" in missing and "reason" in placeholder_fields:
        blocking_placeholders.append("reason")
    if "traceability_field" in missing:
        blocking_placeholders.extend(key for key in placeholder_fields if key in _TRACEABILITY_KEYS)
    if require_evidence_traceability:
        blocking_placeholders.extend(
            key for key in placeholder_fields if key in _EVIDENCE_TRACEABILITY_KEYS
        )
    if blocking_placeholders:
        rejection_parts.append("placeholder " + ", ".join(dict.fromkeys(blocking_placeholders)))
    return "; ".join(rejection_parts) if rejection_parts else None


def declared_okf_concept_use(
    *,
    model_msg: Optional[str],
    context_available: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], bool, bool]:
    """Returns model-declared OKF concept usage records.

    Returns:
        Tuple of (declared usage records, declaration present, explicit none).
    """
    use_lines: Optional[List[str]] = extract_knowledge_use_lines(model_msg)
    if use_lines is None:
        return [], False, False
    joined_lines: str = "\n".join(use_lines).strip()
    if joined_lines.lower() in {"none", "- none", "(none)", "no relevant context"}:
        return [], True, True

    declared: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for line in use_lines:
        normalized_line: str = _strip_usage_bullet(line)
        for context in context_available:
            concept_id: str = str(context["concept_id"])
            if concept_id in seen:
                continue
            if not line_declares_concept_id(normalized_line, concept_id):
                continue
            declared.append(
                {
                    "concept_id": concept_id,
                    "usage": normalized_line,
                    "source": "model_msg_knowledge_use_section",
                }
            )
            seen.add(concept_id)
    return declared, True, False
