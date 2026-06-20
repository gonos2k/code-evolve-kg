---
title: Prepare KIM KDM6 CodeEvolve Problem
type: Procedure
date_modified: 2026-06-20
---
# Prepare KIM KDM6 CodeEvolve Problem

## Steps

1. Set `KIM_MESO_SOURCE_ROOT` to the local KIM-meso v1.0 checkout.
2. Verify source digests for `phys/module_mp_kdm6.F`,
   `phys/module_microphysics_driver.F`, `Registry/Registry.EM_COMMON`,
   `phys/module_mp_radar.F`, and `share/module_model_constants.F`.
3. Compile the original KIM-meso tree and record build log, executable, and
   compiler receipts.
4. Run the selected case with `mp_physics=37`, record the namelist digest, run
   log digest, success marker, and `wrfout.37*` digest.
5. Reject any baseline evidence from `mp_physics=137`; that is not the
   Fortran-only KDM6 path.
6. Capture train, holdout, and private-holdout KDM6 boundary fixtures from the
   successful `mp_physics=37` run.
7. Extract a fixed standalone Fortran driver that calls `kdm6(...)` with the
   same species, dimensions, and constants as the KIM-meso microphysics driver.
8. Build the original Fortran KDM6 source as the immutable reference.
9. Build candidate `module_mp_kdm6.F` files with a single EVOLVE block.
10. Run debug parity before release timing.
11. Score only candidates with finite fields and matching physical contracts.
12. Export candidates to a separate Graphify evolved-code corpus with links back
   to the KDM6 KG decision and concept pages.
13. Use full KIM-meso smoke tests only for selected candidates or checkpoints.

## Hard Constraints

- Do not use KDM6AD, LibTorch, C ABI, VJP/JVP, or AD runtime paths.
- Do not edit `module_microphysics_driver.F` or `Registry.EM_COMMON`.
- Do not change the `kdm6(...)` public signature.
- Do not accept a physical semantic change without a KG decision and traceable
  fixture evidence.

## Output

The procedure is complete when `problems/kim_kdm6_microphysics` contains a
full KIM-meso `mp_physics=37` baseline receipt, a runnable `config.yaml`,
`input/evaluate.py`, fixed Fortran driver/reference sources, captured fixtures,
and baseline correctness/speed metrics.
