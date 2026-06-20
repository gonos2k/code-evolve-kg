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
  - predicate: part_of
    target: "[[kim-kdm6-microphysics-optimization]]"
    rationale: "KDM6 standalone fixtures must be captured from a full KIM-meso mp_physics=37 baseline run."
  - predicate: derived_from
    target: "[[wrf-single-physics-problem-setup]]"
    rationale: "The fixture requirements are listed in the local WRF setup note."
---
# Standalone Physics Boundary Fixture

## Definition

A standalone physics boundary fixture is a captured host-model physics-driver
boundary snapshot containing the dimensions, state arrays, mutable outputs,
timestep constants, namelist constants, and species mappings needed to reproduce
one physics scheme call outside the full host model.

## Why It Matters

It lets the evaluator compare a candidate against the original scheme without
running a full forecast for every candidate. The fixture is only valid if the
standalone reference reproduces the original full-model boundary output within
the declared tolerance.

## Current Understanding

The fixture should capture loop bounds such as `ids/ide`, `jds/jde`, `kds/kde`,
memory bounds, tile bounds, state arrays used by the scheme, tendencies, mutable
outputs, `dt`, timestep counters, scheme constants, and moist or scalar index
mappings. For KIM-meso KDM6, fixtures must come from a successful
`mp_physics=37` full-model run or explicit boundary dump instrumentation in
that Fortran path.
