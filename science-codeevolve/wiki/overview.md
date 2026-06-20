---
title: Wiki Overview
type: meta
date_modified: 2026-06-20
---
# Wiki Overview

## Current Project Thread

The active thread is preparing CodeEvolve to optimize Fortran kernels and then
one selected NWP physics process. The current concrete target is KIM-meso KDM6
microphysics on the original Fortran path.

Code structure is not represented as wiki content. Graphify owns code graph artifacts under `graphify-out/`; the wiki keeps domain framing, decisions, procedures, and source summaries.

WRF/KIM physics improvement is KG-gated because it requires high-domain
scientific judgment. The workflow must use KG query, ingest, challenge, and
decision records for physical assumptions, coupling contracts, tolerances, and
validation risks before candidate changes are trusted.

During evolution, generated candidate code should be exported to a separate Graphify corpus such as `<out_dir>/graphify-evolve-corpus/`. Candidate cards, generated-diff sidecars, and metadata record KG links and evaluation metrics, creating a knowledge+code bridge without moving generated code into the wiki.

## WRF Problem Setup

- [[wrf-single-physics-optimization]] is the main concept.
- [[use-standalone-physics-evaluation-for-wrf]] is the current architecture decision.
- [[require-kg-interaction-for-wrf-physics-changes]] is the knowledge workflow decision.
- [[use-graphify-evolved-code-corpus]] is the code-graph bridge decision.
- [[prepare-wrf-single-physics-codeevolve-problem]] is the next execution path.
- [[standalone-physics-boundary-fixture]] is the critical missing data contract.

## KIM-meso KDM6 Problem Setup

- [[kim-kdm6-microphysics-optimization]] is the current concrete target concept.
- [[target-kim-kdm6-fortran-path]] records the Fortran-only decision.
- [[prepare-kim-kdm6-codeevolve-problem]] is the setup procedure.
- Full KIM-meso `mp_physics=37` compile/run evidence is required before a
  fitness function is valid.
- KDM6AD, LibTorch, C ABI, VJP/JVP, and AD runtime paths are excluded.

## Immediate Missing Inputs

- Recorded KIM-meso `mp_physics=37` build/run receipt.
- KDM6 boundary dump or fixture capture from that run.
- Compiler profile.
- Field tolerance policy.
