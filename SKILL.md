---
name: code-evolve-kg
description: >-
  CodeEvolve-specific KG/wiki and Graphify workflow for WRF or scientific-code
  optimization changes. Use when Codex is modifying or reviewing CodeEvolve
  support for KNOWLEDGE_CONTEXT, GRAPHIFY_EXPORT, evolved-code corpora,
  OKF-compatible KG/wiki bundles, WRF single-physics problem setup, Fortran
  evaluator/toolchain integration, or KG-backed prompt/evaluation gates. Do not
  use for generic /kg, /kg-query, /kg-update, or non-CodeEvolve knowledge-graph
  operations; use the existing kg skills for those.
---

# CodeEvolve KG

## Overview

Use this skill to keep CodeEvolve's KG integration scoped to CodeEvolve runs while avoiding overlap with the generic `kg` skill family. Treat KG/wiki pages as selected context and decision records, and treat Graphify as the owner of evolved-code corpora and code-structure indexing.

## Workflow

1. Read repository-local `AGENTS.md` before editing CodeEvolve files.
2. Identify whether the request is CodeEvolve-specific. If it is a generic KG command or generic wiki maintenance task, stop using this skill and use the existing `kg-*` skill.
3. Keep this skill and the CodeEvolve core decoupled from generic `kg-*` skill internals, KG MCP servers, or wiki implementation code. Prefer file-based `KNOWLEDGE_CONTEXT`, explicit config, and run metadata over direct runtime dependencies on KG tools.
4. Preserve the authority chain: fixed evaluator/driver contracts and raw sources override KG wiki summaries; KG wiki summaries override Graphify-derived code links; Graphify is for code corpus structure and semantic linking, not domain truth.
5. Make KG usage auditable. When injecting context, include source labels and a receipt such as path, resolved path, and content digest. If required context is missing, fail before the run starts.
6. Make Graphify export auditable. Export candidate code outside `wiki/`, with sidecar metadata, candidate cards, generated diffs, finite JSON, lineage IDs, prompt IDs, and configured KG links.
7. Re-run semantic Graphify extraction when bridge artifacts change. A code-only structural refresh is insufficient after candidate cards, metadata, or KG links change.
8. Add focused tests for every gate or export contract changed.

## OKF Profile

- Treat CodeEvolve KG/wiki content as an OKF-compatible file bundle when possible: Markdown files with YAML frontmatter and a non-empty `type` field.
- Do not add OKF services, SDKs, or network dependencies to CodeEvolve runtime code. OKF is a file format boundary for portability, not a platform dependency.
- Prefer bundle-relative Markdown links for KG pages and keep Graphify evolved-code exports as a separate corpus linked back from candidate cards and metadata.
- When `KNOWLEDGE_CONTEXT` claims OKF compatibility, fail fast if selected Markdown context files lack parseable frontmatter or `type`.
- For WRF single-physics runs, require OKF-compatible context by default; do not allow a successful WRF KG gate to produce no OKF concept IDs unless explicitly designing a non-OKF generic run with an auditable override. Inline context may supplement OKF pages, but inline-only context must not satisfy WRF OKF requirements.
- Preserve producer-specific fields such as `instance_of`, `page_kind`, `relations`, and `provenance`; OKF consumers should tolerate extensions.
- Do not treat OKF alone as proof that a candidate used knowledge. For usage judgement, require candidate-level knowledge-use receipts that connect OKF concept IDs, model rationale, generated diffs, Graphify metadata, gate results, and evaluator metrics.
- Require model-visible OKF usage to be declared in a `KNOWLEDGE USE:` section before the first SEARCH/REPLACE block. Prefer structured declarations with non-empty `reason=` and symbol/diff/fixture/metric traceability; empty fields such as `reason=; symbol=;` and placeholder values such as `todo`, `n/a`, `none`, or `unknown` must not count. For WRF single-physics strict runs, `symbol=`, `module=`, or `subroutine=` alone is insufficient; require at least one of `diff=`, `fixture=`, or `metric=`. Graphify metadata should count only exposed OKF concept IDs declared in that section as `context_declared_used`; do not infer usage from incidental lexical overlap in generated code or declarations after the first diff block.
- Treat `context_declared_used` and `declared_usage_score` as model self-report, not verified knowledge usage. Do not report verified usage without an additional verifier or Graphify semantic extraction result.
- Prefer `overall_declared_use_score` for aggregate self-report scoring. If `overall_knowledge_use_score` is kept for compatibility, set it to null or mark it as a removed/deprecated alias so downstream consumers do not mistake it for verified usage.

## CodeEvolve Contracts

- `KNOWLEDGE_CONTEXT` is static, selected prompt context unless a dedicated dynamic retriever is explicitly implemented. Do not claim live KG interaction from static file injection alone.
- Required KG context must fail fast on missing or empty paths.
- Prompt context must be fence-safe and prompt-injection resistant enough for Markdown source pages; use indented source blocks rather than wrapping arbitrary wiki text in fences.
- Initial candidate evaluation must fail fast on infrastructure errors, nonzero evaluator return codes, or missing fitness keys.
- Candidate failures expected during evolution should still return exit code `0` plus finite numeric metrics so the evolutionary loop continues.
- `eval_metrics` and Graphify metadata must serialize with `allow_nan=False`; convert non-finite numeric values to a finite penalty.
- Do not auto-fill `semantic_gate_passed`. It should mean the evaluator explicitly ran and passed a semantic validation gate. Use a separate `acceptance_policy_passed` metric for CodeEvolve static/KG-decision policy acceptance.
- Keep static-policy rejection counts separate from KG/semantic-decision rejection counts in candidate metrics and Graphify metadata.
- Keep candidate-level OKF traceability validation shared between acceptance policy and Graphify export. If `symbol=`, `module=`, or `subroutine=` is checked against candidate code in the gate, Graphify metadata should use the same code-aware result.
- For `domain: wrf_single_physics`, do not allow `semantic_change_policy.default: allow_without_kg_decision` unless the configuration also records an explicit semantic-policy override flag and non-placeholder justification in the gate receipt.
- Checkpoint resume must preserve solution-to-prompt provenance when the original prompt is still available. If not available, record the fallback explicitly in metadata or logs.

## WRF Physics Guardrails

- Optimize one selected physics process at a time; do not expose full WRF, registry, namelist parsing, or driver dispatch to LLM edits.
- Use standalone boundary fixtures for per-candidate parity and benchmark loops. Use full WRF only for accepted-candidate smoke checks or scheduled checkpoints.
- Require immutable interface contracts: module names, public subroutine signatures, array layouts, units, species mappings, and copy-back semantics.
- Treat physical correctness as a hard gate before performance fitness.
- Separate train and holdout fixtures when possible. Do not rely on one fixed visible fixture for acceptance.

## Review Checklist

- Does the implementation avoid importing or invoking generic KG skill internals from CodeEvolve runtime code?
- Does the prompt path include enough KG context for the model and enough receipt metadata for later audit?
- If OKF is claimed, do selected KG files have parseable frontmatter with `type`, and is candidate-level knowledge use recorded separately from mere context exposure?
- Does Graphify export write evolved code outside the wiki and link back to KG pages without making wiki pages the code store?
- Are bridge files updated when configured KG links or context paths change?
- Are WRF or Fortran evaluator failures split into candidate failure vs infrastructure failure?
- Are tests covering the negative path, not only the successful path?
