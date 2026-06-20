# KIM-meso KDM6 Microphysics Scaffold

This directory is a preparation scaffold, not an executable CodeEvolve problem
yet.

The target is the original Fortran KDM6 microphysics path in KIM-meso v1.0.
KDM6AD, LibTorch, C ABI, VJP/JVP, and AD wrapper paths are not part of this
problem.

## Valid Target

Use a local KIM-meso checkout through:

```bash
export KIM_MESO_SOURCE_ROOT=/path/to/KIM-meso_v1.0
```

The Fortran-only target contract is:

- scheme source: `phys/module_mp_kdm6.F`
- driver contract: `phys/module_microphysics_driver.F`
- Registry contract: `Registry/Registry.EM_COMMON`
- namelist selector: `mp_physics==37`
- package: `kdm6scheme`
- module: `module_mp_kdm6`
- entry point: `kdm6(...)`
- likely first inner edit surface: `kdm62D(...)`

Do not expose `phys/module_mp_kdm6ad.F`, `phys/kdm6_iso_c.F`, LibTorch paths, or
AD runtime files to CodeEvolve as candidate, reference, or validation targets.

## Files

```text
kim_kdm6_target.example.yaml       target contract example
input/kim_kdm6_evidence.example.yaml
                                   source/KG/fixture evidence scaffold
```

The detailed setup plan is in:

```text
../../docs/kim_kdm6_microphysics_problem_setup.md
```

## Next Milestone

The next milestone is a full KIM-meso Fortran KDM6 baseline:

```text
original KIM-meso source tree
source digest verification
KIM-meso compile
mp_physics=37 run
rsl success logs
wrfout.37* output digest
captured KDM6 boundary fixture
```

Only after that baseline exists should the scaffold move to a standalone
Fortran parity driver:

```text
original module_mp_kdm6.F
candidate module_mp_kdm6.F
fixed KDM6 driver
captured KIM-meso boundary fixture
debug parity build
release timing build
finite results.json
```

Only after the full-model baseline and standalone parity driver exist should
this directory gain `config.yaml`, `input/evaluate.py`, and candidate source
files. A fitness function based only on an uncoupled driver is not acceptable
until that driver has reproduced the full KIM-meso `mp_physics=37` baseline.

Use `scripts/verify_kim_kdm6_baseline.py` from the `science-codeevolve` root to
check copied baseline evidence and write a private receipt before defining
fitness.

## KG Context

Use CodeEvolve file-based KG context, not generic KG runtime dependencies. The
minimum context set for this scaffold is:

```yaml
KNOWLEDGE_CONTEXT:
  enabled: true
  title: "KIM KDM6 Fortran Context"
  required: true
  require_okf: true
  okf_bundle_root: wiki
  paths:
    - wiki/overview.md
    - wiki/decisions/target-kim-kdm6-fortran-path.md
    - wiki/concepts/kim-kdm6-microphysics-optimization.md
    - wiki/concepts/standalone-physics-boundary-fixture.md
    - wiki/procedures/prepare-kim-kdm6-codeevolve-problem.md
```

Candidate code, generated diffs, evaluator diagnostics, and candidate-declared
knowledge use remain untrusted generated artifacts. Graphify export should store
candidate code in a separate evolved-code corpus and link back to these KG pages
without publishing local source paths.
