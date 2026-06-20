# Literature Positioning and Current Limits

This note positions the current CodeEvolve KG/WRF development snapshot against
the AlphaEvolve-lineage evolutionary coding literature and records the claim
boundaries that should be preserved in docs, demos, and reviews.

## Summary

The project is a research-mature AlphaEvolve-lineage framework with two original
extensions:

- auditable, file-based KG grounding for scientific-code edits
- a scientific Fortran and WRF single-physics direction

Its current differentiator is provenance and policy auditability, not yet a
demonstrated scientific-discovery result. The WRF direction is designed and
scaffolded, but it still needs a runnable single-physics benchmark with baseline
numbers before it should be described as a validated WRF optimization capability.

## Strengths

- The core follows the AlphaEvolve family closely: marked EVOLVE blocks,
  SEARCH/REPLACE mutation, island populations, optional MAP-Elites archives,
  inspiration crossover, and prompt co-evolution.
- Fitness is evaluator-grounded rather than self-reported by the model. The
  Fortran stencil evaluator demonstrates the intended correctness-first pattern:
  debug build, finite-number checks, input-unchanged checks, release build, and
  speed-ratio fitness.
- The KG integration is auditable. `KNOWLEDGE_CONTEXT` injects selected
  file-based context with receipts, `KNOWLEDGE_GATE` records evidence and
  target contracts, and Graphify metadata keeps candidate-level knowledge-use
  declarations separate from verified knowledge use.
- The WRF framing targets a less-covered domain for evolutionary coding:
  scientific Fortran physics kernels rather than only math puzzles, heuristics,
  or accelerator kernels.
- The engineering surface is suitable for trusted research development:
  checkpoint/resume, provenance metadata, directory locking, mock model support,
  focused tests, and CI.

## Claim Boundaries

- The evaluator is resource containment, not a security sandbox. It uses
  subprocess execution, temporary work directories, timeout/resource monitoring,
  and process cleanup. Hostile-code operation still requires an external
  isolation layer.
- Correctness-first evaluation is a problem-level contract, not a universal core
  guarantee. A strong `evaluate.py` can enforce correctness and anti-cheat
  checks; a weak one can still reward wrong code.
- KG grounding is static file injection plus policy/traceability checking, not
  live retrieval. It does not prove semantic truth or that the model truly used
  a concept in the causal sense.
- Candidate `KNOWLEDGE USE` declarations are model self-report with structured
  traceability. Graphify may record them as declared use; verified knowledge use
  requires an additional verifier or semantic extraction result.
- The current WRF problem is a scaffold. The executable in-repo benchmark is the
  generic Fortran stencil; WRF single-physics still needs concrete fixtures,
  target source, baseline parity, and benchmark results.
- The current tree is source-clean, but old public Git history may still contain
  local development artifacts until history is rewritten or the repository is
  recreated.

## Frontier Gaps

- Diversity is the weakest search axis. Embeddings can be computed but are not
  used for novelty, parent selection, or migration. MAP-Elites uses configured
  evaluation metrics as descriptors and keeps only the highest-fitness elite per
  cell; poor descriptors can degenerate the archive into mostly fitness tracking.
  Migration is still rank/top-candidate oriented.
- Sample efficiency is limited. The main loop evaluates one generated candidate
  per epoch and does not yet include rejection sampling, reward-bandit routing,
  or sample allocation across model/prompt strategies.
- Reflection is not a first-class loop. The system has prompt co-evolution and
  evaluator feedback, but it does not yet implement a ReEvo-style verbal
  gradient/reflection step.
- The objective is single-scalar fitness. Pareto optimization and explicit
  multi-objective tradeoffs are not implemented in the core selection loop.
- SEARCH/REPLACE matching is exact. This is faithful and auditable, but it can
  waste calls when a generated search block nearly matches the parent code.
- The core trusts each problem evaluator for semantic correctness. It records
  metrics and return codes, but it does not yet attest that a problem implements
  the required correctness gates.

## Roadmap

### P0: Demonstrate the WRF Flagship

Ship one runnable `wrf_single_physics` problem that pins:

- exact WRF commit or source digest
- one selected physics family, scheme module, and entrypoint
- standalone train and holdout boundary fixtures
- reference parity against the original WRF scheme
- baseline correctness and speed numbers
- accepted-candidate host smoke procedure

This turns the WRF capability from sound-by-design into demonstrated behavior.

### P1: Add Diversity Pressure

Use existing embeddings and descriptors in the search loop:

- novelty-aware parent selection
- diversity-aware migration quotas
- embedding-distance or AST/metric descriptors for MAP-Elites
- archive reporting that distinguishes quality from descriptor coverage

### P2: Improve Sample Efficiency

Add low-cost rejection and routing before expensive evaluation:

- syntactic/static-policy rejection sampling for bad SEARCH/REPLACE outputs
- reward-bandit allocation across model ensemble members, prompts, or mutation
  strategies
- accounting that reports accepted/evaluated candidates per model call

### P3: Add Reflection and Core Evaluation Attestation

Introduce a reflection record that summarizes failures, accepted design
constraints, and next mutation hypotheses. Separately, make problem evaluators
declare the gates they implement, such as correctness, finite-number checks,
input immutability, train/holdout split, and semantic acceptance policy. The core
should record this declaration and surface missing gates in metadata.

## Recommended Wording

Use:

> A research-mature AlphaEvolve-lineage framework with auditable KG grounding and
> a scientific Fortran/WRF roadmap.

Avoid:

> A production sandbox for untrusted generated code.

Use:

> The WRF single-physics path is designed and scaffolded; the next milestone is
> a runnable benchmark with baseline numbers.

Avoid:

> WRF physics optimization is already demonstrated.
