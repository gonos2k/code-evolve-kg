---
title: Wiki Overview
type: meta
date_modified: 2026-06-20
---
# Wiki Overview

## Current Project Thread

The active thread is preparing CodeEvolve to optimize Fortran kernels and then one selected WRF physics process.

Code structure is not represented as wiki content. Graphify owns code graph artifacts under `graphify-out/`; the wiki keeps domain framing, decisions, procedures, and source summaries.

WRF physics improvement is KG-gated because it requires high-domain scientific judgment. The workflow must use KG query, ingest, challenge, and decision records for physical assumptions, coupling contracts, tolerances, and validation risks before candidate changes are trusted.

During evolution, generated candidate code should be exported to a separate Graphify corpus such as `<out_dir>/graphify-evolve-corpus/`. Candidate cards, generated-diff sidecars, and metadata record KG links and evaluation metrics, creating a knowledge+code bridge without moving generated code into the wiki.

## WRF Problem Setup

- [[wrf-single-physics-optimization]] is the main concept.
- [[use-standalone-physics-evaluation-for-wrf]] is the current architecture decision.
- [[require-kg-interaction-for-wrf-physics-changes]] is the knowledge workflow decision.
- [[use-graphify-evolved-code-corpus]] is the code-graph bridge decision.
- [[prepare-wrf-single-physics-codeevolve-problem]] is the next execution path.
- [[standalone-physics-boundary-fixture]] is the critical missing data contract.

## Immediate Missing Inputs

- Exact WRF source path or commit/tag.
- Target physics family and namelist value, for example `mp_physics=8`.
- Short WRF run output or boundary dump permission.
- Compiler profile.
- Field tolerance policy.
