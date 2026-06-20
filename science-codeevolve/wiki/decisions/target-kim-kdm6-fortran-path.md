---
title: Target KIM KDM6 Fortran Path
type: Decision
status: accepted
date_modified: 2026-06-20
---
# Target KIM KDM6 Fortran Path

## Decision

For KDM6 microphysics improvement, CodeEvolve targets only the original Fortran
KDM6 path in `phys/module_mp_kdm6.F`.

KDM6AD, LibTorch, C ABI wrappers, VJP/JVP, and AD runtime files are excluded
from the candidate, reference, and validation surface.

## Rationale

The user selected a local KIM-meso v1.0 source tree as the original source and
clarified that only the Fortran path is valid. Repo configs and public metadata
should refer to that tree through `KIM_MESO_SOURCE_ROOT`, not a committed
absolute path. The host model selects the KDM6 scheme through
`mp_physics==37`, `kdm6scheme`, and the `CASE (KDM6SCHEME)` dispatch to
`kdm6(...)`. That is the contract the evaluator must preserve.

Keeping the target Fortran-only also avoids mixing a physics-optimization
objective with AD/LibTorch integration concerns.

## Consequences

- The fitness function requires a successful original KIM-meso compile and
  `mp_physics=37` run before any standalone evaluator can be trusted.
- The first standalone evaluator compares candidate Fortran KDM6 against the
  original Fortran KDM6 reference only after reproducing that full-model
  baseline.
- `module_microphysics_driver.F` and `Registry.EM_COMMON` are fixed evidence,
  not edit targets.
- Candidate prompts must preserve `module_mp_kdm6`, the `kdm6(...)` signature,
  and KDM6 species/output semantics.
- Any future AD or LibTorch work requires a separate problem and separate KG
  decision.

## Related

- [[kim-kdm6-microphysics-optimization]]
- [[prepare-kim-kdm6-codeevolve-problem]]
