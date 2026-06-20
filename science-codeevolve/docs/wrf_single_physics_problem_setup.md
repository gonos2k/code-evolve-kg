# WRF Single-Physics Problem Setup

This note defines how to set up a CodeEvolve problem that improves one selected
WRF physics process without letting the search modify unrelated WRF code.

## Sources Checked

- WRF User's Guide, physics overview:
  https://www2.mmm.ucar.edu/wrf/users/wrf_users_guide/build/html/physics.html
- WRF User's Guide, namelist physics variables:
  https://www2.mmm.ucar.edu/wrf/users/wrf_users_guide/build/html/namelist_variables.html
- WRF official repository, `phys/` tree:
  https://github.com/wrf-model/WRF/tree/master/phys
- WRF official repository, microphysics driver:
  https://github.com/wrf-model/WRF/blob/master/phys/module_microphysics_driver.F

## Conclusion

Do not run full WRF for every CodeEvolve candidate. The problem should evolve
only one extracted physics scheme and should use full WRF only as a periodic
host smoke test.

Recommended first target: one microphysics scheme.

Reasons:

- WRF documents microphysics as producing heat, moisture, and resolved-scale
  precipitation tendencies.
- WRF exposes microphysics selection through `mp_physics`; the User's Guide says
  this option is set consistently across domains.
- The official WRF source has a dedicated `phys/module_microphysics_driver.F`
  and many `phys/module_mp_*.F` scheme files, making the boundary easier to
  isolate than a whole-model objective.

PBL, surface layer, LSM, cumulus, and radiation can follow the same pattern, but
they should be second-stage targets because they are more tightly coupled to
surface state, radiation cadence, vertical diffusion, or grid/domain choices.

## Target Contract

Each WRF single-physics problem must define these facts before any evolution:

```yaml
WRF_TARGET:
  wrf_version: "v4.x.y or exact commit"
  physics_family: "microphysics"
  namelist_option: "mp_physics"
  namelist_value: 8
  scheme_module: "phys/module_mp_thompson.F"
  driver_module: "phys/module_microphysics_driver.F"
  entrypoint: "scheme subroutine name"
  allowed_edit_scope: "single EVOLVE block inside scheme wrapper"
```

The public subroutine signature, module name, hydrometeor/scalar slot mapping,
units, array layout, and tendency copy-back contract are immutable. If a
candidate changes any of these, the driver compile or numeric contract must fail
with `fitness=0`.

## Evaluation Architecture

```text
Program.code
  -> Evaluator writes temporary .F/.F90 candidate
  -> evaluate.py runs in copied input directory
  -> FortranToolchain debug build
  -> standalone WRF-physics parity cases
  -> FortranToolchain release build
  -> benchmark cases
  -> finite numeric results.json
  -> CodeEvolve reads fitness
```

## KG-Backed Prompt Context

WRF physics-process improvement must use KG interaction before and during code
generation. Code structure and call relationships belong to Graphify, but
domain assumptions, source-backed constraints, validation policy, and open
risks belong to KG wiki pages.

Use the local `code-evolve-kg` skill for CodeEvolve-specific implementation and
review work. Keep the generic `kg-*` skills for direct KG/wiki operations such as
querying, updating, linting, or challenging wiki knowledge.

Use `KNOWLEDGE_GATE` as the executable preflight. It validates the evidence
manifest before any LLM prompt sampling or candidate evaluation starts:

```yaml
KNOWLEDGE_GATE:
  enabled: true
  required: true
  domain: "wrf_single_physics"
  manifest: "input/wrf_evidence.yaml"
  receipt_output: "knowledge_gate/receipt.json"
  require_exact_target: true
  require_knowledge_context: true
  require_graphify_export: true
  require_train_holdout: true
  require_source_files: true
  require_source_digests: true
  require_fixture_files: true
  require_kg_decisions: true
  min_sources:
    official_docs: 1
    raw_wrf_code: 2
    literature: 1
    similar_code: 1
  static_policy:
    enabled: true
    scan_scope: "evolve_block"
    strip_fortran_comments: true
```

The evidence manifest must pin the WRF commit and target scheme, cite official
WRF docs, cite raw WRF source files, include at least one scheme literature
source, include at least one similar implementation, list required KG decisions,
and separate train from holdout fixtures. With the strict WRF defaults, raw WRF
source entries must exist under `wrf_source_root` and match the target commit,
raw WRF source entries must include the configured `scheme_module` and
`driver_module`, similar-code entries must include an exact commit plus a local
snapshot artifact with verified sha256 evidence, context pages must exist and be
non-empty, required KG decision IDs must be referenced, and train/holdout
fixture paths must be existing disjoint files. A passing run writes:

```text
<out_dir>/knowledge_gate/receipt.json
```

The receipt digest is prepended to the static prompt context and copied into
Graphify candidate metadata. This is deliberately file-based preflight, not a
live KG query inside CodeEvolve core.

Use CodeEvolve's `KNOWLEDGE_CONTEXT` setting to inject selected KG pages into
every LLM code-generation prompt:

```yaml
KNOWLEDGE_CONTEXT:
  enabled: true
  title: "WRF KG Context"
  required: true
  require_okf: true
  okf_bundle_root: wiki
  max_chars: 16000
  paths:
    - wiki/overview.md
    - wiki/decisions/require-kg-interaction-for-wrf-physics-changes.md
    - wiki/concepts/wrf-single-physics-optimization.md
    - wiki/concepts/standalone-physics-boundary-fixture.md
    - wiki/procedures/prepare-wrf-single-physics-codeevolve-problem.md
```

The selected KG pages should be OKF-compatible Markdown documents. In this
project, that means parseable YAML frontmatter with at least a non-empty `type`
field. OKF gives every knowledge page a portable concept identity, but it does
not by itself prove that a candidate used that knowledge. Use the candidate
knowledge-use receipt design in `docs/okf_knowledge_usage_assessment.md` to
judge knowledge influence.

For `domain: wrf_single_physics`, `KNOWLEDGE_GATE` requires OKF-compatible
context by default. A selected context page without frontmatter or a non-empty
`type` fails preflight before the LLM is called. Inline context can supplement
selected pages, but it cannot satisfy the WRF OKF requirement by itself because
it has no bundle-relative concept identity. Turning off knowledge context or
OKF context requires both `KNOWLEDGE_GATE.allow_non_okf_context: true` and a
non-placeholder `KNOWLEDGE_GATE.non_okf_context_justification`, which are
recorded in the gate receipt.

When OKF context is injected, the prompt asks the model to add a
`KNOWLEDGE USE:` section before the first SEARCH/REPLACE block. Graphify
metadata records only structured lines in that section that start with an
exposed OKF concept ID as `knowledge_use.context_declared_used`; incidental
concept-id mentions inside prose or replacement code are retained for review but
are not scored as declared use.
The declaration is still a self-report, not proof of verified knowledge usage.
For generated WRF candidates, configure semantic candidate enforcement to
require both configured KG decision IDs and declared OKF concept use so a
candidate cannot pass acceptance using only a run-level KG receipt. The declared
use should include `reason=` and at least one traceability field such as
`symbol=`, `diff=`, `fixture=`, or `metric=`. Empty field values do not count;
placeholder values such as `todo`, `n/a`, `none`, or `unknown` do not count
either. `symbol=`, `module=`, and `subroutine=` declarations are checked
against the candidate code by both the acceptance policy and Graphify
knowledge-use receipt. For WRF single-physics strict runs, symbol traceability
alone is insufficient; include at least one of `diff=`, `fixture=`, or
`metric=` so the declaration links the KG concept to a concrete edit, case, or
reported validation signal. `diff=` must point at an actual generated
SEARCH/REPLACE block such as `SEARCH_REPLACE_1`, and `fixture=` must match a
name listed in `fixture_summary.traceable_train_fixture_names`, not a filename,
path, holdout case, private holdout case, or unexposed train case. Metric
traceability is checked against evaluator metric keys when metrics exist, so
metric-only declarations cannot satisfy the pre-eval WRF acceptance gate.

`kg.required_decisions` must resolve to exposed OKF `type: Decision` concept IDs
in `knowledge_context_receipts`, and those receipts must come from manifest
`kg.context_paths`. A `GRAPHIFY_EXPORT.knowledge_links` string that contains the
decision id is not enough to satisfy the gate. When more than one decision is
required, each decision needs a matching declaration in `KNOWLEDGE USE:`. The
WRF gate prompt receipt lists both `okf_concept_ids` and
`required_decision_concept_ids`, so the model has exact identifiers available
even when the longer knowledge-context body is truncated. Candidate acceptance
and Graphify metadata both derive valid required-decision concepts from the
scoped receipt map and the actual `knowledge_context_receipts`, requiring OKF
`type: Decision`; stale flat concept-id lists do not count.

If a WRF run intentionally changes `semantic_change_policy.default` to
`allow_without_kg_decision`, also set
`KNOWLEDGE_GATE.allow_semantic_policy_override: true` and provide
`KNOWLEDGE_GATE.semantic_policy_justification`. The receipt records this audit
trail; otherwise the preflight gate fails.

Before starting a real WRF run, update these KG pages with the selected scheme's
physical assumptions, coupling contract, fixture validity criteria, tolerance
policy, and known risks. If a proposed optimization changes physical semantics,
record a KG challenge or decision before accepting it into the evolutionary
loop.

Use `GRAPHIFY_EXPORT` to export every evaluated candidate into a separate
Graphify-managed corpus:

```yaml
GRAPHIFY_EXPORT:
  enabled: true
  root: "graphify-evolve-corpus"
  mode: "all"
  include_initial: true
  required: true
  knowledge_links:
    - "[[wrf-single-physics-optimization]]"
    - "[[require-kg-interaction-for-wrf-physics-changes]]"
    - "[[standalone-physics-boundary-fixture]]"
```

The export writes:

```text
<out_dir>/graphify-evolve-corpus/
  README.md
  knowledge_bridge.md
  island_0/
    candidates/epoch_000001__candidate__program_<id>.md
    code/epoch_000001__candidate__program_<id>.F90
    diffs/epoch_000001__candidate__program_<id>.md
    metadata/epoch_000001__candidate__program_<id>.json
    manifest.jsonl
```

Graphify owns this evolved-code corpus. KG owns the domain pages referenced in
`knowledge_bridge.md`, each candidate Markdown card, and each metadata sidecar.
This creates a knowledge+code link without turning generated code into wiki
content.

When KG links, candidate cards, or metadata change, run semantic Graphify
extraction on the evolved-code corpus:

```text
/graphify <out_dir>/graphify-evolve-corpus --update
```

Use `graphify update <out_dir>/graphify-evolve-corpus` only for structural
code refreshes where code files changed but the semantic bridge did not.

Full WRF execution is deliberately outside the per-candidate loop. Use it only
for accepted candidates or scheduled checkpoints:

```text
candidate accepted
  -> rebuild WRF or patched physics library
  -> 1-3 timestep idealized or small real-data smoke
  -> compare selected wrfout/wrfrst fields and logs
```

## Required Input Bundle

The evaluator input directory should contain:

```text
input/
  evaluate.py
  wrf_evidence.yaml
  wrf_physics_profile.yaml
  wrf_target.yaml
  driver/
    standalone_driver.F90
    reference_driver.F90
  fixtures/
    case_0001.npz or NetCDF-derived arrays
    case_0002.npz or NetCDF-derived arrays
  source/
    reference_scheme.F
  src/
    init_program.F
```

`src/init_program.F` is the evolved candidate. `source/reference_scheme.F`,
drivers, fixture data, namelist constants, and metadata are immutable.

## Fixture Capture

For the first version, collect fixtures from a short WRF run rather than a full
forecast objective.

Capture at the physics-driver boundary:

- Dimensions and loop bounds: `ids/ide`, `jds/jde`, `kds/kde`, `ims/ime`,
  `jms/jme`, `kms/kme`, `its/ite`, `jts/jte`, `kts/kte`.
- State arrays used by the target scheme: temperature/potential temperature,
  pressure/exner, density, water vapor, hydrometeors/scalars, vertical metrics,
  land/sea or surface fields as needed.
- Tendencies and mutable outputs.
- `dt`, timestep counters, and scheme-specific namelist constants.
- Any species index mapping from WRF moist/scalar arrays to scheme-local names.

A fixture is valid only if the standalone reference reproduces the original WRF
scheme output for that boundary snapshot within the declared tolerance.

## Fitness

Use a hard correctness gate:

```json
{
  "fitness": 1.08,
  "correct": 1,
  "failure_code": 0,
  "max_abs_error": 0.0,
  "max_rel_error": 0.0,
  "candidate_time_s": 0.018,
  "reference_time_s": 0.0195,
  "compile_time_s": 0.47,
  "eval_time": 0.71
}
```

Recommended failure codes:

```text
10 debug compile failure
11 debug run failure
12 standalone numeric mismatch
13 release compile failure
14 benchmark failure
15 output parse failure
16 static policy rejection
17 missing or invalid evidence manifest
18 missing KG decision for semantic change
19 required Graphify export failed
20 WRF boundary fixture invalid
21 host-smoke regression
22 holdout fixture mismatch
23 target WRF source digest mismatch
```

The JSON must contain only finite numeric values. Compiler versions, full build
commands, and WRF logs belong in stderr, run logs, or metadata files, not in
`eval_metrics`.

## Candidate Scope

The first WRF problem should not expose the whole WRF scheme file to CodeEvolve.
Wrap the target kernel or rate block:

```fortran
! EVOLVE-BLOCK-START
  ! local rate computation / loop body only
! EVOLVE-BLOCK-END
```

If new local variables are likely, place the EVOLVE block around the smallest
subroutine body that can legally contain declarations and executable statements.
Do not let the model edit:

- WRF driver dispatch code.
- Registry or namelist parsing.
- Module public interfaces.
- Hydrometeor/scalar index constants.
- Fixture I/O or result scoring.
- Full WRF build scripts.

## Recommended Implementation Phases

1. **W0 target selection**: choose exact WRF commit, physics family, namelist
   option, scheme module, and entrypoint.
2. **W1 boundary inventory**: enumerate every input, inout, output, constant,
   species index, unit, and copy-back path used by the selected scheme.
3. **W2 standalone reference**: build a driver that reproduces original scheme
   outputs for captured fixtures.
4. **W3 CodeEvolve candidate loop**: use `FortranToolchain` debug/release
   builds and speed-ratio fitness.
5. **W4 accepted-candidate host smoke**: patch WRF, run 1-3 timesteps, compare
   selected `wrfout` or restart fields.
6. **W5 long-run validation**: only after W0-W4 are stable, run a longer case.

## First Target Recommendation

Start with microphysics, not radiation or full PBL.

Candidate shortlist:

- WSM6 or WDM6: good for single-scheme boundary extraction.
- Thompson: scientifically relevant but has more internal state and branches.
- NSSL: useful later if intercept/density parameters are part of the search,
  but it has more species and options.

The first milestone should be:

```text
one WRF microphysics scheme
one captured boundary fixture
standalone reference parity
CodeEvolve smoke with MOCK model
no full WRF run inside per-candidate evaluation
```

## Open Inputs Needed

Before creating the executable WRF problem directory, provide:

- WRF source tree path or exact Git commit/tag.
- Target physics family and namelist value, for example `mp_physics=8`.
- One short WRF run directory with `namelist.input`, `wrfinput`, and relevant
  `wrfout`/restart output, or permission to add boundary dump instrumentation.
- Preferred compiler and build mode.
- Tolerance policy: bitwise, ULP-bounded, or absolute/relative field tolerance.
