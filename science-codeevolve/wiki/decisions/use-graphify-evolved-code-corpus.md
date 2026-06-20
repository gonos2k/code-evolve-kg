---
title: Use Graphify Evolved-Code Corpus
type: Decision
instance_of: Decision
page_kind: decision-page
date: 2026-06-20
date_created: 2026-06-20
date_modified: 2026-06-20
relations:
  - predicate: decided_for
    target: "[[wrf-single-physics-optimization]]"
    rationale: "The decision defines how generated candidate code is managed during WRF physics optimization."
  - predicate: derived_from
    target: "[[require-kg-interaction-for-wrf-physics-changes]]"
    rationale: "The evolved-code corpus bridges KG-backed domain reasoning with generated candidate code."
---
# Use Graphify Evolved-Code Corpus

## Context

CodeEvolve creates many candidate programs during an evolutionary run. Keeping those candidates only inside checkpoints makes structural comparison difficult, while putting generated code into the wiki would violate the separation between code graph and domain knowledge.

## Decision

Export evaluated candidate code into a separate Graphify-managed corpus, normally `<out_dir>/graphify-evolve-corpus/`. Each exported candidate gets a source file, a Markdown candidate card, an optional generated-diff document, and sidecar metadata containing program lineage, evaluation metrics, and KG links.

## Rationale

Graphify should own structural analysis of generated code. KG should own the physical assumptions, validation decisions, and source-backed reasoning used to judge that code. Candidate cards and sidecar metadata connect the two without duplicating generated code into wiki pages. Semantic Graphify extraction is required when those bridge artifacts change; code-only structural refresh is not enough.

## Alternatives Considered

- Store candidates only in CodeEvolve checkpoints: rejected because Graphify cannot incrementally analyze the generated code.
- Create wiki pages for each generated candidate: rejected because the wiki should not become a code artifact store.
- Export only the best candidate: deferred because failed and mediocre candidates are useful for understanding search patterns and repeated mistakes.

## Consequences

The run output contains a reproducible code corpus that can be indexed by Graphify independently of the main repository. KG pages can reference concepts and decisions, while candidate cards and metadata record which KG pages informed each generated program and where the generated diff is stored.
