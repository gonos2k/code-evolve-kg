# CodeEvolve KG Scientific-Code Research Snapshot

This directory is a development snapshot of CodeEvolve with CodeEvolve-specific
KG, Graphify, Fortran, WRF single-physics, and KIM-meso KDM6 microphysics work
layered on top.

It should be read as a research and engineering handoff, not as a production
service and not as a demonstrated NWP physics-optimization result. The current
validated executable Fortran example is the generic stencil problem. The WRF and
KIM-meso KDM6 paths are designed and scaffolded, but they still need runnable
targets, fixtures, parity checks, and baseline numbers.

For the repository-level wrapper skill, CI layout, and license boundary, start
with the parent [README](../README.md).

## What This Snapshot Contains

- AlphaEvolve-lineage evolutionary coding core:
  - marked EVOLVE blocks
  - SEARCH/REPLACE mutation
  - island populations and migration
  - prompt co-evolution
  - optional MAP-Elites archives
- File-based KG support:
  - `KNOWLEDGE_CONTEXT` prompt injection with source receipts
  - `KNOWLEDGE_GATE` preflight checks for evidence, targets, fixtures, and
    semantic-change policy
  - candidate-level `KNOWLEDGE USE:` parsing and traceability receipts
- Graphify export support:
  - evolved code stored outside `wiki/`
  - candidate cards, sidecar metadata, diffs, lineage, prompt IDs, receipt
    digests, and KG links
  - public metadata sanitization for local/private paths
- Fortran support:
  - `.f90` language registration
  - GNU Fortran debug/release toolchain helper
  - runnable `problems/fortran_stencil` example
- WRF single-physics design:
  - evidence manifest scaffold
  - WRF target contract examples
  - KG/OKF guardrails
  - standalone-fixture architecture documentation
- KIM-meso KDM6 microphysics setup:
  - Fortran-only target boundary for `phys/module_mp_kdm6.F`
  - explicit exclusion of KDM6AD, LibTorch, and AD runtime paths
  - full KIM-meso `mp_physics=37` compile/run baseline prerequisite
  - source digest and evidence-manifest scaffold

## Current Claim Boundary

Supported:

- This is a research-mature CodeEvolve development snapshot.
- KG integration improves provenance, auditability, and correctness discipline.
- The Fortran stencil path runs through compile, correctness, and benchmark
  gates.
- Graphify export records traceable links between candidate code, metadata,
  generated diffs, and selected KG pages.

Not yet supported:

- KG grounding has not been shown to improve evolutionary fitness or sample
  efficiency. That needs KG on/off ablations under the same seeds and budget.
- `KNOWLEDGE USE` is a structured model self-report, not verified causal proof
  that the model used a concept.
- WRF or KIM-meso KDM6 physics optimization is not yet demonstrated by an
  in-repo executable benchmark.
- The evaluator is not a security sandbox for hostile generated code.

See [docs/literature_positioning.md](docs/literature_positioning.md) for the
literature-facing positioning, corpus-derived claim taxonomy, limitations, and
roadmap.

## Directory Map

```text
science-codeevolve/
  src/codeevolve/
    cli.py                 CLI entry point
    evolution.py           evolutionary loop and component setup
    evaluator.py           resource-contained candidate execution
    database.py            Program model, selection, MAP-Elites
    prompt/
      knowledge.py         static file-based context injection
      knowledge_gate.py    evidence and policy preflight checks
    toolchains/
      fortran.py           GNU Fortran compile/run helper
    utils/
      graphify_export.py   evolved-code corpus export
      knowledge_use.py     candidate knowledge-use parsing
  problems/
    fortran_stencil/       runnable Fortran integration example
    wrf_single_physics/    WRF problem scaffold and examples
    kim_kdm6_microphysics/ KIM-meso KDM6 Fortran-only scaffold
  docs/
    kim_kdm6_microphysics_problem_setup.md
    literature_positioning.md
    okf_knowledge_usage_assessment.md
    wrf_single_physics_problem_setup.md
  wiki/                    OKF-style project KG/wiki bundle
  tests/                   unit and integration tests
  UPSTREAM.yml             upstream snapshot provenance
```

## Quick Start

Core requirements:

- Python `>=3.13.5`
- `uv`

Fortran requirements:

- GNU Fortran (`gfortran`) is needed only for the Fortran integration tests and
  Fortran examples. The core test command below excludes those tests.

Install development dependencies from the lockfile:

```bash
cd science-codeevolve
python -m pip install "uv==0.9.7"
uv sync --locked --extra dev
```

Run the core test suite:

```bash
uv run --no-sync pytest tests/ --ignore=tests/fortran -q
```

Run the Fortran integration tests:

```bash
uv run --no-sync pytest tests/fortran/ -q
```

Run format and scoped type checks:

```bash
uv run --no-sync isort --check-only src tests
uv run --no-sync black --check src tests
uv run --no-sync mypy \
  src/codeevolve/prompt/knowledge.py \
  src/codeevolve/prompt/knowledge_gate.py \
  src/codeevolve/utils/graphify_export.py \
  src/codeevolve/utils/knowledge_use.py \
  src/codeevolve/toolchains/fortran.py \
  src/codeevolve/evaluator.py \
  --ignore-missing-imports \
  --follow-imports=skip \
  --allow-untyped-defs \
  --allow-incomplete-defs
```

The repository-level CI runs these checks from the repository root with
`working-directory: science-codeevolve`.

## Running CodeEvolve

After `uv sync`, confirm that the `codeevolve` console script is available:

```bash
uv run --no-sync codeevolve --help
```

Each run is configured by YAML. Existing examples live under `configs/` and
`problems/*/config.yaml`. A problem usually provides:

- initial source file and language
- EVOLVE block markers
- evaluator entry point such as `evaluate.py`
- resource limits
- fitness key
- model or mock-model configuration

For development without model calls, use a config with `model_name: MOCK`.

## KG and OKF Workflow

`KNOWLEDGE_CONTEXT` is static selected context. It loads configured files,
records path/digest receipts, and injects the text into prompts. It is not a
live KG query and does not depend on generic KG tools at runtime.

`KNOWLEDGE_GATE` is a preflight acceptance-policy gate. In WRF-style strict
runs, it can require:

- exact WRF target metadata
- raw source and fixture digests
- official documentation and literature/source evidence
- OKF-compatible context pages
- required decision concepts
- train/holdout fixture separation
- candidate `KNOWLEDGE USE:` declarations before the first SEARCH/REPLACE block

The gate checks provenance and policy compliance. It does not prove that a
scientific claim is true and does not prove that a model causally used a concept.

For KG outcome experiments, `scripts/make_kg_ablation_plan.py` can generate
same-seed `kg_on`, `context_only`, and `kg_off` config variants plus a JSON run
manifest. It is a planning scaffold only; run results and aggregation are still
required before claiming that KG improves evolutionary fitness.

More detail:

- [docs/okf_knowledge_usage_assessment.md](docs/okf_knowledge_usage_assessment.md)
- [problems/wrf_single_physics/README.md](problems/wrf_single_physics/README.md)

## Graphify Export

`GRAPHIFY_EXPORT` writes evaluated candidates into a separate evolved-code
corpus instead of storing generated code inside the wiki. The export includes:

- source code
- generated diff
- candidate Markdown card
- metadata JSON
- manifest JSONL
- knowledge bridge file

Configured KG links must be complete public wiki links, bundle-relative Markdown
links, or `http(s)` URLs with public hosts. Local paths, traversal, unsupported
URI schemes, loopback/private IPs, embedded URL credentials, and mixed trailing
text are rejected. Configured knowledge context paths must be bundle-relative.
Public metadata stores numeric metrics, diagnostic digests, receipt digests, and
sanitized summaries; raw stderr/stdout-style diagnostics and full private
receipts can contain local paths and should not be published without review.

Candidate code, generated diffs, evaluator diagnostics, and candidate-declared
knowledge use are untrusted artifacts. Semantic Graphify extraction should treat
them as quoted evidence, not executable instructions.

Semantic Graphify extraction should be rerun when candidate cards, metadata, or
KG bridge files change. A structural code-only refresh is not enough for
knowledge-code linking.

## Fortran Path

The Fortran work is intentionally problem-local. CodeEvolve writes candidate
Fortran files and calls the existing `evaluate.py candidate_path results_path`
contract. The problem evaluator then uses `codeevolve.toolchains.fortran` to
compile fixed driver/reference sources plus the generated candidate.

The runnable reference example is:

```text
problems/fortran_stencil/
```

It demonstrates:

- candidate `.f90` handling
- debug build with runtime checks
- release build for timing
- correctness gates before performance scoring
- finite numeric metrics in `results.json`

## WRF Single-Physics Status

The WRF path is a scaffold for optimizing one selected physics process while
keeping WRF host contracts fixed. It is designed around:

- one pinned WRF source commit or digest
- one physics family and scheme entry point
- immutable public interfaces and species mappings
- standalone boundary fixtures for train/holdout evaluation
- full WRF smoke tests only for accepted candidates or checkpoints
- KG decisions for physical semantic changes

The next milestone is a runnable `wrf_single_physics` problem with baseline
correctness and speed numbers. Until then, describe this as a roadmap and
problem setup, not a validated WRF optimization benchmark.

See [docs/wrf_single_physics_problem_setup.md](docs/wrf_single_physics_problem_setup.md).

## KIM-meso KDM6 Status

The KIM-meso KDM6 path is a scaffold for improving the original Fortran KDM6
microphysics implementation in a user-supplied KIM-meso v1.0 source tree.

The valid target is:

```text
phys/module_mp_kdm6.F
```

The fixed host contracts are:

```text
phys/module_microphysics_driver.F
Registry/Registry.EM_COMMON
mp_physics=37
```

KDM6AD, LibTorch, C ABI, VJP/JVP, and AD runtime files are explicitly excluded
from the candidate, reference, and validation surface. The fitness function is
not valid until the original KIM-meso tree compiles and runs a Fortran KDM6
`mp_physics=37` baseline. Standalone Fortran fixtures are an inner-loop
acceleration only after they reproduce that full-model baseline.

Use `scripts/verify_kim_kdm6_baseline.py` to validate copied baseline evidence
and write a private receipt before defining KDM6 fitness.

See
[docs/kim_kdm6_microphysics_problem_setup.md](docs/kim_kdm6_microphysics_problem_setup.md)
and [problems/kim_kdm6_microphysics/README.md](problems/kim_kdm6_microphysics/README.md).

## Security Boundary

Candidate programs run in temporary working directories with subprocess
execution, timeout/resource monitoring, and process cleanup. That is resource
containment, not a security sandbox.

Do not run untrusted generated code on a sensitive host with this snapshot
alone. Production or multi-tenant use requires an external isolation layer such
as a rootless container, network-denied jail, read-only filesystem, environment
allowlist, non-privileged UID/GID, cgroup limits, and syscall filtering.

## Known Gaps

- No ablation yet shows that KG grounding improves evolutionary outcomes.
- No component-analysis suite yet separates the value of KG, diversity,
  reflection, prompt strategy, or evaluator policy.
- WRF single-physics is not yet runnable end-to-end.
- KIM-meso KDM6 is not yet runnable inside CodeEvolve; it first needs a recorded
  full-model `mp_physics=37` compile/run baseline and extracted fixtures.
- Diversity pressure is weak: embeddings are optional and not used for novelty,
  selection, migration, or MAP-Elites descriptors.
- Sample efficiency is limited: no rejection sampling or reward-bandit routing.
- Reflection is not a first-class ReEvo-style loop.
- Multi-objective/Pareto reporting is not implemented in the core selection
  loop.
- Core correctness still depends on the problem's `evaluate.py`.
- Full mypy coverage is not enabled for all core modules.
- Public Git history may still contain old development artifacts.

## License and Upstream

The `science-codeevolve/` tree is derived from the upstream CodeEvolve project
and keeps its Apache-2.0 license in [LICENSE](LICENSE). The current upstream
baseline is recorded in [UPSTREAM.yml](UPSTREAM.yml): upstream tag `v0.3.1`,
commit `70a656dee67640c26b414369c641fa5916e559b2`. The repository-level Codex
skill wrapper is documented separately in the parent directory.

## Citation

If you use upstream CodeEvolve research artifacts, cite the upstream project and
paper as appropriate. This KG/scientific-code snapshot additionally changes the
provenance, KG, Graphify, Fortran, WRF, and KIM-meso KDM6 problem-setup surface;
do not cite it as evidence of NWP physics performance improvement until runnable
benchmarks and ablations exist.
Use [docs/literature_positioning.md](docs/literature_positioning.md) as the
local claim-boundary and literature-anchor note, not as a substitute for a full
systematic literature review.
