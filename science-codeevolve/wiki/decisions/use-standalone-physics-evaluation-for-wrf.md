---
title: Use Standalone Physics Evaluation for WRF
type: Decision
instance_of: Decision
page_kind: decision-page
date: 2026-06-20
date_created: 2026-06-20
date_modified: 2026-06-20
relations:
  - predicate: decided_for
    target: "[[wrf-single-physics-optimization]]"
    rationale: "The decision defines the evaluation architecture for WRF physics optimization."
  - predicate: derived_from
    target: "[[wrf-single-physics-problem-setup]]"
    rationale: "The rationale is taken from the local WRF setup note."
---
# Use Standalone Physics Evaluation for WRF

## Context

CodeEvolve needs many candidate evaluations. Full WRF runs are expensive, tightly coupled, and difficult to attribute to one physics change.

## Decision

Use an extracted standalone WRF-physics evaluator for every candidate. Run full WRF only for accepted candidates or scheduled checkpoint smoke tests.

## Rationale

The standalone evaluator keeps the search scoped to one physics process, enforces the scheme boundary with compile and numeric checks, and provides fast speed-ratio fitness against the fixed reference implementation. A separate host-smoke step catches integration regressions without making every evolutionary iteration pay full-model cost.

## Alternatives Considered

- Run full WRF for every candidate: rejected because it is too slow and noisy for an evolutionary inner loop.
- Optimize the whole WRF physics tree: rejected because it would expose unrelated dispatch, Registry, namelist, and coupling code.
- Start with radiation, PBL, LSM, or cumulus: deferred because these families are more tightly coupled to cadence, surface state, vertical diffusion, or domain configuration.

## Consequences

The project must build reliable boundary fixtures and a standalone parity driver before real optimization starts. Full-model validation remains necessary, but it moves to a slower outer validation loop.
