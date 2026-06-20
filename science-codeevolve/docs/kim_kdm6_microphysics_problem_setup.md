# KIM-meso KDM6 Microphysics Problem Setup

This note defines the CodeEvolve problem setup for improving the KDM6
microphysics process in the KIM-meso v1.0 source tree supplied by the user.

The valid target path is the original Fortran KDM6 implementation only. The
KDM6AD/LibTorch path is explicitly out of scope for this problem.

## Source Boundary

Use the local source tree through an environment variable, not a hard-coded
absolute path in public run metadata:

```bash
export KIM_MESO_SOURCE_ROOT=/path/to/KIM-meso_v1.0
```

The source tree inspected for this setup had the following KDM6-relevant
Fortran files and digests:

| Role | Path | SHA-256 |
| --- | --- | --- |
| Candidate and reference scheme | `phys/module_mp_kdm6.F` | `948d64b3dd7722a8eca730afc08544115907ec1b4a1561d737dadcea80a88f2a` |
| Fixed host dispatch contract | `phys/module_microphysics_driver.F` | `6d4f09b4e0306131e585dbd3b7456850db878f459f2202b3dc67061026e5c056` |
| Fixed Registry contract | `Registry/Registry.EM_COMMON` | `19612afc3dd73931c11a6065cc87457da5cead98191052acc8a1e3d8c9af067e` |
| Direct scheme dependency | `phys/module_mp_radar.F` | `aa99da858be41efa579966680708d230123a7417560af0eb2e24f4c94e253688` |
| Direct scheme dependency | `share/module_model_constants.F` | `5b80377fecdc18a5f0ad38d3b6c15cfc86ad5d76701adbbbb08a08698d0f7062` |

Observed KDM6 entry points:

- `module module_mp_kdm6`
- `subroutine kdm6(...)`
- `subroutine kdm62D(...)`
- `subroutine kdm6init(...)`
- `subroutine slope_kdm6(...)`
- `subroutine refl10cm_kdm6(...)`
- `subroutine effectRad_kdm6(...)`

Observed host contract:

- Registry package: `kdm6scheme`
- Namelist selector: `mp_physics==37`
- Required species/state mapping:
  `moist:qv,qc,qr,qi,qs,qg;scalar:qnn,qnc,qni,qib,qnr;state:re_cloud,re_ice,re_snow,rhopo3d`
- Driver case: `CASE (KDM6SCHEME)` calls `kdm6(...)`

## Explicit Non-Targets

The following paths are not part of this problem's candidate, reference,
benchmark, or KG target surface:

- `phys/module_mp_kdm6ad.F`
- `phys/kdm6_iso_c.F`
- any LibTorch, C ABI, VJP/JVP, or AD runtime path

Those files can remain in the user's local model checkout, but CodeEvolve must
not treat them as the source of truth or as a validation reference for this
Fortran-only KDM6 problem.

## First Editable Surface

The first executable version should evolve only a single marked block inside
`phys/module_mp_kdm6.F`. The initial block should be narrow enough to preserve
host integration, but wide enough for the model to make physically meaningful
Fortran edits.

Recommended first target:

- Keep `module_mp_kdm6` unchanged.
- Keep the public `kdm6(...)` signature unchanged.
- Prefer a marked block in or below `kdm62D(...)`, where the column-local
  microphysical tendencies are computed.
- Do not expose `module_microphysics_driver.F`, `Registry.EM_COMMON`, namelist
  parsing, or package selection to LLM edits.
- Do not expose generated code to file I/O, environment access, C
  interoperability, OpenMP, or external libraries.

The candidate can change numerical formulations only inside the EVOLVE block.
It must not change array dimensions, units, species order, precipitation
accumulator semantics, effective-radius outputs, or radar reflectivity outputs.

## Fitness Prerequisite: Full KIM-meso Compile and Run

The fitness function is not valid until the original KIM-meso tree can compile
and run the Fortran KDM6 path. The first P0 milestone is therefore not the
standalone driver; it is a source-tree baseline run.

Required baseline evidence:

- `KIM_MESO_SOURCE_ROOT` resolves to the original source tree.
- The source digests in this document match the local tree.
- `main/wrf.exe` and, for idealized cases, `main/ideal.exe` are built from that
  source tree.
- The selected KIM-meso case runs with `mp_physics=37`, not `mp_physics=137`.
- `rsl.out.*` or equivalent runtime logs show successful completion for the
  `mp_physics=37` case.
- `wrfout.37*.nc` or an equivalent KDM6 output artifact is produced and its
  digest is recorded.
- Any boundary fixture used by CodeEvolve is captured from that successful
  Fortran KDM6 run.

The evidence can be checked with:

```bash
uv run --no-sync python scripts/verify_kim_kdm6_baseline.py \
  --manifest problems/kim_kdm6_microphysics/input/kim_kdm6_evidence.yaml \
  --bundle-root /path/to/private/kdm6-baseline-bundle \
  --source-root "$KIM_MESO_SOURCE_ROOT" \
  --output /path/to/private/kdm6-baseline-receipt.json
```

The baseline bundle should contain copied logs, namelist, executable digests,
`wrfout.37*` output, and fixture artifacts using bundle-relative paths. It
should not publish local absolute paths.

Current local evidence should be treated carefully: the tree contains built
`main/wrf.exe` and `main/ideal.exe`, and it contains `wrfout.37*.nc` artifacts,
but the active `run/namelist.input` inspected during setup used
`mp_physics=137`. Logs or outputs from `mp_physics=137` are invalid for this
Fortran-only KDM6 objective.

## Evaluation Architecture

The executable problem should be built in stages.

Stage 0: source-tree baseline

- Resolve `KIM_MESO_SOURCE_ROOT`.
- Verify the SHA-256 digests of all fixed source files listed above.
- Compile the original KIM-meso tree.
- Run the selected baseline case with `mp_physics=37`.
- Record the build log digest, run log digest, namelist digest, `wrfout.37*`
  digest, executable digest, compiler identity, and runtime environment needed
  to repeat the run.
- Only after this passes, copy the original `module_mp_kdm6.F` into the
  evaluation input as the immutable reference source.
- Copy candidate `module_mp_kdm6.F` files into separate build directories.

Stage 1: standalone Fortran parity fixture

- Build a fixed Fortran driver that calls the same `kdm6(...)` contract as the
  KIM-meso microphysics driver.
- Feed column or small-patch boundary fixtures captured from the successful
  `mp_physics=37` KIM-meso baseline into both original and candidate KDM6.
- Compare all prognostic and diagnostic outputs touched by KDM6:
  `TH`, `Q`, `QC`, `QR`, `QI`, `QS`, `QG`, `NN`, `NC`, `NI`, `NR`, `BG`,
  precipitation increments, `SR`, `REFL_10CM`, and effective radii when enabled.
- Enforce finite values and input immutability before measuring performance.

Stage 2: release benchmark

- Only candidates that pass debug parity compile a release executable.
- Fitness should be a speed ratio against the original Fortran KDM6 reference
  under the same executable and fixture mix:

```text
fitness = reference_time_s / candidate_time_s
```

- Use median timing over multiple fixture sizes and seeds.
- Keep all JSON metrics finite. Candidate failures return `fitness=0` with a
  structured failure code; infrastructure failures return a nonzero evaluator
  exit.

Stage 3: KIM-meso host smoke

- Periodically copy accepted candidates back into a disposable KIM-meso build
  tree.
- Compile or relink the disposable tree and run a short `mp_physics=37` smoke
  case.
- Treat host smoke as checkpoint validation, not as the per-candidate inner
  loop.

## KG Gate Requirements

KDM6 microphysics changes require KG-backed reasoning because the target is a
scientific physics parameterization, not a generic loop kernel.

The KDM6 KG context should expose:

- the Fortran-only source boundary and non-target list
- the `mp_physics==37` package contract
- species and diagnostic output mappings
- fixture provenance and train/holdout separation
- physical tolerance policy
- allowed semantic-change decisions

This follows the code-evolution wiki's claim boundary: static KG injection and
knowledge-use receipts improve provenance and auditability, but they do not by
themselves prove better evolutionary outcomes. Any claim that KG improves KDM6
fitness requires same-seed, same-budget KG-on/KG-off ablations.

## Acceptance Gates

A KDM6 candidate should be accepted only if all of these pass:

- Original KIM-meso Fortran KDM6 baseline compile/run evidence exists.
- Fortran debug build succeeds with runtime checks.
- Public interface and host contract are unchanged.
- No banned API is introduced in the EVOLVE block.
- All compared fields are finite.
- Mass and number concentration floors remain physically admissible.
- Reference parity passes on visible train fixtures.
- Holdout fixtures pass after selection.
- Release benchmark reports finite speed-ratio metrics.
- Candidate `KNOWLEDGE USE:` declarations cite the KDM6 Fortran-path decision
  and connect the edit to a real diff plus a traceable fixture or metric.

## Current Status

This is a preparation scaffold. It does not yet include:

- recorded `mp_physics=37` full KIM-meso baseline receipt
- extracted KDM6 boundary fixtures
- a standalone KDM6 driver
- an executable `evaluate.py`
- baseline timing numbers
- KG ablation results
- host KIM-meso smoke outputs

Until those exist, describe KDM6 support as a problem setup and source-boundary
decision, not as a demonstrated KDM6 optimization benchmark.
