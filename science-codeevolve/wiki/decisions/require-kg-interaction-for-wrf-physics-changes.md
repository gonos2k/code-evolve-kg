---
title: Require KG Interaction for WRF Physics Changes
type: Decision
instance_of: Decision
page_kind: decision-page
date: 2026-06-20
date_created: 2026-06-20
date_modified: 2026-06-20
relations:
  - predicate: decided_for
    target: "[[wrf-single-physics-optimization]]"
    rationale: "The decision defines the knowledge workflow required before and during WRF physics optimization."
---
# Require KG Interaction for WRF Physics Changes

## Context

WRF physics-process improvement is not a normal code-only optimization task. Candidate changes can alter physical assumptions, conservation behavior, numerical stability, units, scheme coupling, and validation tolerances.

## Decision

Every WRF physics-process improvement task must interact with the KG before and during implementation. Code structure remains under Graphify, but domain knowledge, assumptions, source summaries, validation policy, open questions, and decisions must be handled through the KG.

## Rationale

The KG provides the working memory needed for high-knowledge scientific code changes. It keeps source-backed domain constraints visible, makes assumptions explicit, and gives a place to challenge proposed modifications before they enter the evolutionary loop.

The verification chain remains: Graphify for code structure, KG wiki for synthesized domain context, raw WRF or literature sources for primary evidence. Wiki pages guide work but do not replace raw-source verification.

## Alternatives Considered

- Treat the physics scheme as a pure performance kernel: rejected because speed-only optimization can damage physical validity.
- Keep all reasoning in the chat transcript: rejected because WRF setup and validation decisions must persist across sessions.
- Put code structure pages into the wiki: rejected because Graphify owns code graph artifacts and the wiki should stay focused on domain knowledge and decisions.

## Consequences

Before changing a WRF physics candidate, the agent should query or update the KG for the target scheme, governing equations or assumptions, WRF coupling contract, fixture validity, tolerances, and known risks. If a proposed optimization changes physical semantics, the agent should use KG challenge or an explicit decision page before implementation.
