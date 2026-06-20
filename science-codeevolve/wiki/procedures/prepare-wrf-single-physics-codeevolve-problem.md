---
title: Prepare WRF Single-Physics CodeEvolve Problem
type: Procedure
instance_of: Procedure
page_kind: procedure-page
epistemic_status: inferred
date_created: 2026-06-20
date_modified: 2026-06-20
relations:
  - predicate: applies_to
    target: "[[wrf-single-physics-optimization]]"
    rationale: "This procedure turns the WRF single-physics framing into an executable CodeEvolve problem."
  - predicate: derived_from
    target: "[[wrf-single-physics-problem-setup]]"
    rationale: "The sequence is derived from the local WRF setup note."
  - predicate: derived_from
    target: "[[require-kg-interaction-for-wrf-physics-changes]]"
    rationale: "The procedure now includes KG gates for scientific-domain reasoning."
  - predicate: derived_from
    target: "[[use-graphify-evolved-code-corpus]]"
    rationale: "The procedure includes Graphify export for generated candidate code."
---
# Prepare WRF Single-Physics CodeEvolve Problem

## Purpose

Create an executable CodeEvolve benchmark that optimizes one selected WRF physics process while keeping the host WRF contract fixed.

## Preconditions

- A pinned WRF source tree or exact commit.
- A selected physics family, namelist option, namelist value, scheme module, driver module, and entrypoint.
- A short WRF run directory or permission to add boundary dump instrumentation.
- A compiler profile and tolerance policy.
- A clear EVOLVE block that does not expose WRF driver dispatch, Registry or namelist parsing, public interfaces, species constants, fixture I/O, scoring, or full WRF build scripts.
- A `wrf_evidence.yaml` manifest with official documentation, raw WRF code, literature, similar-code evidence, KG decisions, and train/holdout fixture roles. Raw WRF source files, KG context pages, and train/holdout fixture files must exist locally for strict WRF runs.

## Steps

1. Select the exact WRF target and record it in `wrf_target.yaml`.
2. Query the KG for prior knowledge about the selected physics family, scheme assumptions, coupling contract, fixture requirements, and open risks.
3. Ingest or update KG source summaries for any missing WRF documentation, scheme references, or local notes needed to justify the target and tolerance policy.
4. Create `input/wrf_evidence.yaml` and record the pinned WRF target, official docs, raw WRF source files, literature, similar code with sha256 evidence, KG decision IDs, and train/holdout fixtures.
5. Add `KNOWLEDGE_GATE` to the CodeEvolve config so the run fails before LLM setup when evidence, raw source files, KG context, Graphify export, fixture files, or train/holdout separation are incomplete.
6. Add `KNOWLEDGE_CONTEXT` to the CodeEvolve config so the LLM sees the selected OKF-compatible KG pages during code generation and meta-prompting. WRF single-physics preflight should reject selected context pages without frontmatter or a non-empty `type`, and inline-only context should not satisfy the OKF concept requirement.
7. Add `GRAPHIFY_EXPORT` so evaluated candidates are exported to `<out_dir>/graphify-evolve-corpus/` with candidate cards, generated-diff sidecars, evidence receipt metadata, and KG links.
8. Require model outputs to include `KNOWLEDGE USE:` before the first SEARCH/REPLACE block when OKF context is used; Graphify should count only exposed OKF concept IDs declared there as declared candidate knowledge use, not verified usage. Empty or placeholder `reason=` or traceability fields do not count as structured use, code-symbol traceability should be checked the same way in the acceptance gate and Graphify export, and WRF strict runs should require `diff=`, `fixture=`, or `metric=` evidence in addition to any symbol/module/subroutine reference.
9. Run semantic Graphify extraction (`/graphify <out_dir>/graphify-evolve-corpus --update`) whenever candidate cards, metadata, receipt links, or KG bridge files change; reserve `graphify update` for code-only structural refreshes.
10. Inventory every input, inout, output, constant, species index, unit, array layout, and copy-back path used by the selected scheme.
11. Capture train and holdout boundary fixtures from a short WRF run.
12. Build a standalone reference driver that reproduces the original WRF scheme output for each fixture within tolerance.
13. Use KG challenge or a decision page for proposed changes that alter physical semantics, empirical constants, conservation assumptions, or tolerance policy.
14. Wrap the candidate kernel or rate block in an EVOLVE block while preserving module and subroutine contracts.
15. Implement `evaluate.py` to run static policy checks, debug compile, train/holdout parity checks, finite-value checks, release compile, benchmark trials, and finite numeric JSON emission.
16. Run CodeEvolve smoke tests with the mock model before using a real LLM.
17. Run Graphify on the evolved-code corpus when structural comparison of generated candidates is needed.
18. For accepted candidates, patch WRF and run a short host-smoke test outside the per-candidate loop.
19. File failed assumptions, validation surprises, and accepted scientific tradeoffs back into the KG as experiences, heuristics, or decisions.

## Postconditions / Verification

- Standalone reference parity passes for the captured fixture.
- Candidate failures return `fitness=0` with numeric failure codes, while infrastructure failures exit nonzero.
- Positive fitness is assigned only after correctness gates pass.
- `KNOWLEDGE_GATE` writes `<out_dir>/knowledge_gate/receipt.json` and Graphify candidate metadata includes the receipt digest, evidence manifest digest, KG context digest, raw-source digests, WRF commit, KG decision IDs, fixture summary, and `knowledge_use` receipt.
- A short WRF host-smoke check is available for accepted candidates or checkpoints.
- KG contains the source-backed assumptions, open questions, and validation decisions used by the benchmark.
- Graphify has a separate evolved-code corpus whose candidate cards and metadata link back to KG pages.
