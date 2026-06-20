---
title: KIM KDM6 Microphysics Optimization
type: Concept
date_modified: 2026-06-20
---
# KIM KDM6 Microphysics Optimization

KIM KDM6 microphysics optimization is the CodeEvolve problem framing for
improving the original Fortran KDM6 microphysics scheme in KIM-meso while
holding the host model, driver dispatch, Registry mapping, and species contracts
fixed.

## Scope

- Target source: `phys/module_mp_kdm6.F`
- Host dispatch contract: `phys/module_microphysics_driver.F`
- Registry contract: `Registry/Registry.EM_COMMON`
- Selector: `mp_physics==37`
- Package: `kdm6scheme`
- Module: `module_mp_kdm6`
- Public entry point: `kdm6(...)`
- First likely inner edit surface: `kdm62D(...)`

## Non-Scope

KDM6AD, LibTorch, C ABI wrappers, VJP/JVP, and AD runtime files are not part of
this concept. They should not be used as candidate targets, references, or
fitness validation paths for the Fortran-only KDM6 problem.

## Required Evidence

The problem needs source digests, a full KIM-meso `mp_physics=37` compile/run
baseline, boundary fixtures captured from that baseline, field tolerance policy,
and KG decisions before any physical semantic change is accepted.

The standalone Fortran evaluator is valid only after it reproduces the
full-model Fortran KDM6 baseline. Logs or outputs from `mp_physics=137` do not
count for this concept.

## Related

- [[target-kim-kdm6-fortran-path]]
- [[prepare-kim-kdm6-codeevolve-problem]]
- [[standalone-physics-boundary-fixture]]
