---
title: Hot Cache
type: meta
date_modified: 2026-06-20
---
# Hot Cache

## Current Focus
Prepare a CodeEvolve problem that improves KIM-meso KDM6 microphysics on the
original Fortran path without exposing unrelated host-model code.

## Recent Activity
- [2026-06-20] recorded [[target-kim-kdm6-fortran-path]]; KDM6AD/LibTorch is excluded and full `mp_physics=37` compile/run is a fitness prerequisite
- [2026-06-20] recorded [[require-kg-interaction-for-wrf-physics-changes]] as a required gate for WRF physics optimization
- [2026-06-20] separated code graph from wiki content; Graphify owns code structure, wiki keeps domain decisions and procedures
- [2026-06-20] ingested [[wrf-single-physics-problem-setup]] into source, concept, procedure, and decision pages
- [2026-06-20] wiki bootstrapped to schema v1

## Key Tensions / Open Questions
- Need a clean KIM-meso `mp_physics=37` run receipt separate from any
  `mp_physics=137` or KDM6AD logs.
- Need boundary fixtures that prove standalone parity with the original Fortran
  KDM6 scheme.
- Need KG source coverage for KDM6 physical assumptions before accepting any
  physics-changing optimization.
