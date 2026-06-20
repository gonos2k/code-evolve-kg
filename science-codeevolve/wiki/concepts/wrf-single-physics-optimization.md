---
title: WRF Single-Physics Optimization
type: Concept
instance_of: Concept
page_kind: concept-page
epistemic_status: inferred
date_created: 2026-06-20
date_modified: 2026-06-20
provenance:
  sources:
    - docs/wrf_single_physics_problem_setup.md
relations:
  - predicate: derived_from
    target: "[[wrf-single-physics-problem-setup]]"
    rationale: "The concept is extracted from the local WRF problem setup note."
---
# WRF Single-Physics Optimization

## Definition

WRF single-physics optimization is a CodeEvolve problem framing where only one selected WRF physics process, such as one microphysics scheme, is exposed to the evolutionary search.

## Why It Matters

Full WRF is too slow and too coupled for a per-candidate evolutionary loop. Isolating one physics process keeps candidate compilation, correctness checks, and benchmarking fast enough to support iterative search while preserving the host model contract.

## Current Understanding

The recommended first target is microphysics. The candidate must preserve the selected scheme's public interface, module names, hydrometeor or scalar index mapping, units, array layout, and copy-back contract. Full WRF should be used as a scheduled host-smoke validation for accepted candidates, not as the default evaluator.

The first executable milestone is one microphysics scheme, one captured boundary fixture, standalone reference parity, and a CodeEvolve smoke run with the mock model.
