---
title: Standalone Physics Boundary Fixture
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
  - predicate: part_of
    target: "[[wrf-single-physics-optimization]]"
    rationale: "Boundary fixtures are the data contract used by the standalone evaluator."
  - predicate: derived_from
    target: "[[wrf-single-physics-problem-setup]]"
    rationale: "The fixture requirements are listed in the local WRF setup note."
---
# Standalone Physics Boundary Fixture

## Definition

A standalone physics boundary fixture is a captured WRF physics-driver boundary snapshot containing the dimensions, state arrays, mutable outputs, timestep constants, namelist constants, and species mappings needed to reproduce one physics scheme call outside full WRF.

## Why It Matters

It lets the evaluator compare a candidate against the original WRF scheme without running a full forecast for every candidate. The fixture is only valid if the standalone reference reproduces the original WRF boundary output within the declared tolerance.

## Current Understanding

The fixture should capture loop bounds such as `ids/ide`, `jds/jde`, `kds/kde`, memory bounds, tile bounds, state arrays used by the scheme, tendencies, mutable outputs, `dt`, timestep counters, scheme constants, and moist or scalar index mappings. For the first version, fixtures should come from a short WRF run or explicit boundary dump instrumentation.
