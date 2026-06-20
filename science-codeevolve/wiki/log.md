---
title: Wiki Log
type: meta
date_modified: 2026-06-20
---
# Wiki Log

- [2026-06-20] decision | [[target-kim-kdm6-fortran-path]] recorded; KIM-meso KDM6 optimization targets only `phys/module_mp_kdm6.F`, excludes KDM6AD/LibTorch, and requires a full `mp_physics=37` compile/run baseline before fitness is valid
- [2026-06-20] concept | [[kim-kdm6-microphysics-optimization]] added for the KIM-meso Fortran-only KDM6 problem framing
- [2026-06-20] procedure | [[prepare-kim-kdm6-codeevolve-problem]] added for source digest, full-model baseline, fixture capture, and standalone driver setup
- [2026-06-20] decision | [[use-graphify-evolved-code-corpus]] recorded; evolved candidate code belongs in a separate Graphify corpus with KG-linked metadata
- [2026-06-20] implementation | `GRAPHIFY_EXPORT` scheme added so evaluated candidates can be exported to a separate evolved-code corpus linked back to KG pages
- [2026-06-20] implementation | Graphify export now writes candidate cards, generated-diff sidecars, and checkpoint-best resume seeds for queryable KG-code linkage
- [2026-06-20] implementation | CodeEvolve `KNOWLEDGE_CONTEXT` added so selected KG pages can be injected into LLM code-generation prompts
- [2026-06-20] kg-lint | wiki frontmatter and wikilinks passed locally; graph report drift remains until semantic Graphify update is rerun
- [2026-06-20] decision | [[require-kg-interaction-for-wrf-physics-changes]] recorded; WRF physics optimization must use KG for domain assumptions and validation decisions
- [2026-06-20] policy | separated code graph from wiki content; Graphify owns code structure under `graphify-out/`
- [2026-06-20] kg-update | graphify update . -> 1644 nodes / 2733 edges / 153 communities in `graphify-out/`
- [2026-06-20] ingest | docs/wrf_single_physics_problem_setup.md -> [[wrf-single-physics-problem-setup]]
- [2026-06-20] init | bootstrapped to v1
