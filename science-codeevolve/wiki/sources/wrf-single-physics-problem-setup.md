---
title: WRF Single-Physics Problem Setup
type: Source
instance_of: Source
page_kind: source-page
date_ingested: 2026-06-20
provenance:
  sources:
    - docs/wrf_single_physics_problem_setup.md
relations:
  - predicate: about
    target: "[[wrf-single-physics-optimization]]"
    rationale: "The source defines the CodeEvolve problem boundary for optimizing one WRF physics process."
---
# WRF Single-Physics Problem Setup

## Summary

This source defines a CodeEvolve problem setup for improving exactly one selected WRF physics process while keeping unrelated WRF code immutable.

Key takeaways:

- Per-candidate evaluation should not run full WRF. It should use an extracted standalone physics driver with captured boundary fixtures, then reserve full-WRF execution for accepted candidates or scheduled host-smoke checks.
- The recommended first target is microphysics via `mp_physics`, because WRF exposes it as a namelist-controlled physics family and the official source tree has a dedicated microphysics driver plus scheme modules.
- The target contract must pin the WRF version or commit, physics family, namelist option and value, scheme module, driver module, entrypoint, and allowed edit scope before evolution starts.
- Correctness is a hard gate: debug compile, standalone parity checks, finite output checks, release compile, and benchmark must all pass before positive fitness is assigned.
- The executable problem still needs a concrete WRF source tree or commit, selected scheme, short WRF run or boundary dump instrumentation, compiler choice, and tolerance policy.

Primary local source: `docs/wrf_single_physics_problem_setup.md`.
