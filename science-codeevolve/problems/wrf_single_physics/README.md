# WRF Single-Physics Scaffold

This directory is a preparation scaffold, not an executable CodeEvolve problem yet.

For CodeEvolve-specific KG/Graphify implementation work, use the local
`code-evolve-kg` skill. Use the generic `kg-*` skills only for direct KG/wiki
queries, updates, linting, or challenge operations.

Use it after selecting:

- exact WRF version or commit
- target physics family
- target namelist option and value
- scheme source file
- captured standalone boundary fixtures
- source-backed evidence manifest, including official docs, raw WRF code,
  literature, similar code, KG decisions, and train/holdout fixtures

The detailed setup plan is in:

```text
docs/wrf_single_physics_problem_setup.md
```

The first recommended executable target is a single microphysics scheme selected
by `mp_physics`, with a standalone driver that reproduces the original WRF
scheme output before any candidate optimization.

When this scaffold becomes an executable CodeEvolve problem, configure KG-backed
prompt context explicitly. Code structure should stay in Graphify, but WRF
physics assumptions and validation decisions should be injected from selected
wiki pages:

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
  semantic_change_policy:
    default: "reject_without_kg_decision"
    candidate_enforcement:
      - "require_configured_kg_decision_ids"
      - "require_declared_okf_concept_use"
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

OKF is used here as the portable KG/wiki document format, not as proof that a
candidate actually used the knowledge. Candidate-level usage judgement requires
the additional receipt described in
`docs/okf_knowledge_usage_assessment.md`. The model should declare used OKF
concept IDs in a `KNOWLEDGE USE:` section before the first SEARCH/REPLACE
block. Each declaration line must start with an exposed OKF concept ID and
include `reason=` plus symbol/diff/fixture/metric traceability; Graphify
metadata does not count incidental concept-id mentions inside prose or
replacement code as declared knowledge use. In WRF single-physics mode,
`KNOWLEDGE_GATE` requires OKF-compatible context by default and fails before the
LLM is called if selected context pages lack frontmatter or a non-empty `type`.
Inline context may supplement selected OKF pages, but it cannot satisfy the WRF
OKF requirement by itself. Disabling WRF knowledge context or OKF context
requires both `allow_non_okf_context: true` and `non_okf_context_justification`;
use that only for an explicitly non-OKF generic comparison run.
Likewise, changing the WRF semantic default to `allow_without_kg_decision`
requires `allow_semantic_policy_override: true` plus
`semantic_policy_justification`, and the receipt records that opt-out. Empty
or placeholder `KNOWLEDGE USE` fields do not count as structured traceability,
and Graphify uses the same code-aware symbol traceability check as the
acceptance gate. For WRF strict runs, `symbol=` alone is not enough; add
`diff=`, `fixture=`, or `metric=` to connect the OKF concept to the edit or
validation evidence. `diff=` must reference an actual generated SEARCH/REPLACE
block, and `fixture=` must match a name listed in
`fixture_summary.traceable_train_fixture_names`, not a filename, path, holdout
case, private holdout case, or unexposed train case.
Metric-only declarations are validated only after evaluator metrics exist and
cannot satisfy the pre-eval acceptance gate by themselves.

Each `kg.required_decisions` id must be exposed as an OKF `type: Decision`
concept in the manifest `kg.context_paths` that also appear in
`KNOWLEDGE_CONTEXT.paths`. A Graphify link containing the decision id is useful
for corpus linkage, but it does not satisfy the decision evidence gate by
itself. If multiple decisions are required, the candidate must declare each one
in `KNOWLEDGE USE:`. The WRF gate receipt shown to the model lists the exposed
OKF concept ids and the required decision concept ids. Graphify metadata uses
the same scoped required-decision map and rechecks OKF `type: Decision`; a stale
receipt with only flat concept ids is marked unavailable, not compliant.

Also export evaluated candidates into a separate Graphify corpus. This keeps
modified code out of the wiki while preserving links from each candidate back
to the KG pages that informed it:

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

`knowledge_links` are public Graphify bridge links. Use complete wiki links,
bundle-relative Markdown links, or `http(s)` URLs with public hosts. Do not put
local absolute paths, traversal, `file:` URIs, loopback/private IPs, embedded URL
credentials, mixed trailing text, or private fixture/source paths in this field.
If `GRAPHIFY_EXPORT.knowledge_context_paths` is set explicitly, those paths must
also be bundle-relative KG/wiki paths.

After or during a run, inspect the evolved-code corpus separately:

For queryable KG-code links from candidate cards, metadata, and the bridge file:

```text
/graphify /path/to/run/graphify-evolve-corpus --update
```

For a structural refresh after pure code changes:

```bash
graphify update /path/to/run/graphify-evolve-corpus
```

The full `knowledge_gate/receipt.json` under a run output is a private runtime
receipt. It can contain local source, fixture, manifest, and context paths for
auditability. Publish the Graphify corpus metadata and receipt SHA/reference, not
the full run output or private receipt, unless the paths have been reviewed.

Candidate code, generated diffs, evaluator diagnostics, and candidate-declared
knowledge use are untrusted generated artifacts. Public metadata stores numeric
metrics, digest summaries, lineage, and sanitized KG summaries rather than raw
stderr/stdout-style diagnostics.
