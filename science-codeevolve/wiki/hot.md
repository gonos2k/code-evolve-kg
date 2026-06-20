---
title: Hot Cache
type: meta
date_modified: 2026-06-20
---
# Hot Cache

## Current Focus
Prepare a CodeEvolve problem that improves one selected WRF physics process without exposing unrelated WRF code.

## Recent Activity
- [2026-06-20] recorded [[require-kg-interaction-for-wrf-physics-changes]] as a required gate for WRF physics optimization
- [2026-06-20] separated code graph from wiki content; Graphify owns code structure, wiki keeps domain decisions and procedures
- [2026-06-20] ingested [[wrf-single-physics-problem-setup]] into source, concept, procedure, and decision pages
- [2026-06-20] wiki bootstrapped to schema v1

## Key Tensions / Open Questions
- Need KG source coverage for the selected scheme before accepting any physics-changing optimization.
- Need exact WRF source commit or local tree before building the executable problem.
- Need target physics option, first likely `mp_physics` microphysics.
- Need boundary fixtures that prove standalone parity with the original WRF scheme.
