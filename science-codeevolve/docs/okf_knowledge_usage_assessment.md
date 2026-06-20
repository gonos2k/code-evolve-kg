# OKF Knowledge-Usage Assessment for CodeEvolve

This note evaluates whether Open Knowledge Format (OKF) is suitable for
judging how much CodeEvolve used project knowledge when modifying code.

## Conclusion

OKF is suitable as the knowledge-corpus format, but it is not sufficient by
itself as the usage-judgement format.

Use OKF for stable, portable knowledge units:

- each KG/wiki page is a Markdown concept document
- each document has YAML frontmatter with at least `type`
- the path is the concept ID
- frontmatter carries queryable metadata such as `title`, `resource`, `tags`,
  `timestamp`, and producer-specific fields
- Markdown links encode the concept graph

Then add a CodeEvolve-specific knowledge-use receipt for each generated
candidate. Graphify metadata writes this receipt under `knowledge_use`. The
receipt records which OKF concepts were available, which concepts the model
explicitly declared it used, and which gates validated or rejected the usage.

## Why OKF Alone Is Not Enough

OKF can prove that knowledge existed and was loaded. It cannot prove that a
model actually used that knowledge in a code edit.

For example, a candidate may receive five OKF documents in prompt context but
ignore all of them. Conversely, it may use a concept implicitly without naming
the concept ID. A usage judgement therefore needs evidence beyond the OKF bundle:
prompt receipts, a model-declared `KNOWLEDGE USE:` section, generated diffs,
candidate metadata, evaluator metrics, and Graphify links.

## Required Artifacts

```text
wiki/                         OKF-compatible KG bundle
  index.md                    bundle index, may declare okf_version
  concepts/*.md               domain concepts
  decisions/*.md              accepted decisions
  sources/*.md                source summaries
  procedures/*.md             workflows

<out_dir>/knowledge_gate/
  receipt.json                run-level evidence and context receipt

<out_dir>/graphify-evolve-corpus/
  code/*.F90                  generated code
  diffs/*.md                  model-generated edits
  candidates/*.md             candidate bridge cards
  metadata/*.json             candidate metadata and knowledge-use receipt
```

## Candidate Knowledge-Use Receipt

Graphify candidate metadata emits this shape under `knowledge_use`:

```json
{
  "knowledge_use_schema_version": 2,
  "okf_bundle": {
    "root": "wiki",
    "okf_version": "0.1",
    "bundle_sha256": "finite-content-digest"
  },
  "context_available": [
    {
      "concept_id": "decisions/require-kg-interaction-for-wrf-physics-changes",
      "type": "Decision",
      "title": "Require KG Interaction for WRF Physics Changes",
      "sha256": "..."
    }
  ],
  "context_declared_used": [
    {
      "concept_id": "decisions/require-kg-interaction-for-wrf-physics-changes",
      "usage": "symbol=kernel; diff=SEARCH_REPLACE_1; reason=preserved WRF semantic-change decision",
      "source": "model_msg_knowledge_use_section"
    }
  ],
  "context_declared_traceability": [
    {
      "concept_id": "decisions/require-kg-interaction-for-wrf-physics-changes",
      "traceability_present": 1,
      "fields": {
        "symbol": "kernel",
        "diff": "SEARCH_REPLACE_1",
        "reason": "preserved WRF semantic-change decision"
      },
      "usable_fields": {
        "symbol": "kernel",
        "diff": "SEARCH_REPLACE_1",
        "reason": "preserved WRF semantic-change decision"
      },
      "evidence_validation": {
        "evidence_fields": {
          "diff": "SEARCH_REPLACE_1"
        },
        "evidence_present": 1,
        "validated_evidence_fields": [
          "diff"
        ],
        "validated_evidence_present": 1,
        "invalid_evidence": [],
        "unvalidated_evidence": []
      },
      "placeholder_fields": [],
      "missing": [],
      "rejection": null
    }
  ],
  "declaration_present": 1,
  "declared_traceability_passed": 1,
  "policy_evidence": {
    "required_decision_ids": [
      "require-kg-interaction-for-wrf-physics-changes"
    ],
    "acceptance_policy_passed": 1,
    "semantic_gate_reported": 1,
    "semantic_gate_passed": 1,
    "static_policy_rejections": 0
  },
  "evaluation_evidence": {
    "correct": 1,
    "fitness": 1.08,
    "max_abs_error": 0.0,
    "max_rel_error": 0.0
  },
  "assessment": {
    "usage_assessment_kind": "declared_self_report",
    "assessment_status": "declared_usage",
    "knowledge_exposure_score": 1.0,
    "declared_usage_score": 1.0,
    "declared_traceability_score": 1.0,
    "declared_traceability_passed": 1,
    "verified_usage_available": 0,
    "verified_usage_score": 0,
    "gate_alignment_score": 1.0,
    "overall_declared_use_score": 1.0,
    "overall_knowledge_use_score": null,
    "overall_knowledge_use_score_kind": "deprecated_alias_removed_use_overall_declared_use_score"
  }
}
```

All numeric values must remain finite JSON numbers.

`context_declared_used` is populated only from structured lines in the model's
explicit `KNOWLEDGE USE:` section before the first SEARCH/REPLACE block. Each
declaration line must start with an exposed OKF concept ID. Concept IDs mentioned
only inside replacement code or arbitrary prose are not counted as declared
knowledge use. A candidate acceptance policy can additionally require the
declaration to include `reason=` and at least one traceability field such as
`symbol=`, `diff=`, `fixture=`, or `metric=`.
The structured fields must have non-empty values. When `symbol=`, `module=`, or
`subroutine=` is used by the acceptance policy, the named token must also be
present in the candidate code; otherwise the declaration is rejected as
untraceable. Placeholder values such as `todo`, `n/a`, `none`, or `unknown` do
not count as usable `reason=` or traceability values. For WRF single-physics
strict runs, `symbol=`, `module=`, or `subroutine=` alone is not enough; the
declaration must also include at least one usable evidence trace field:
`diff=`, `fixture=`, or `metric=`. `diff=` must reference a generated
SEARCH/REPLACE block such as `SEARCH_REPLACE_1`; `fixture=` must match a name
listed in `fixture_summary.traceable_train_fixture_names`, not a filename, path,
digest, holdout case, private holdout case, or unexposed train case. `metric=`
is checked against evaluator metric keys when metrics are available. Metric-only
declarations do not satisfy the pre-evaluation WRF acceptance gate because no
evaluator metrics exist yet.

`acceptance_policy_passed` means CodeEvolve's configured static and KG-decision
acceptance policy did not reject the candidate before evaluation. It is not a
semantic validator. `semantic_gate_passed` is counted only when the evaluator
explicitly reports that metric.

When OKF is required, inline context is not enough. At least one selected
Markdown path must produce an `okf_concept_id`; inline entries may supplement
that context but cannot establish concept identity by themselves.
For WRF single-physics gates, each `kg.required_decisions` entry must match an
exposed OKF `type: Decision` concept ID in `knowledge_context_receipts`, and the
matching context receipt must come from manifest `kg.context_paths`. A Graphify
`knowledge_links` entry that merely contains the decision string is not
sufficient. If multiple required decisions are configured, candidate
`KNOWLEDGE USE:` declarations must include at least one matching OKF concept ID
for every required decision. The WRF gate prompt receipt includes both exposed
`okf_concept_ids` and `required_decision_concept_ids` so the model can declare
exact concept IDs even if the longer `KNOWLEDGE_CONTEXT` body is truncated.
Graphify metadata records `required_decision_declarations` separately from
general declared usage so a non-required concept declaration is not mistaken for
required-decision compliance. Graphify recomputes those required-decision
concepts from `knowledge_context_receipts`, requires OKF `type: Decision`, and
intersects the result with `required_decision_concepts_by_id`; stale receipts
without that scoped map are treated as unavailable rather than accepted.

## Scoring Guidance

Do not score knowledge usage by lexical overlap alone. The current export
contract only counts exact OKF concept IDs listed in `KNOWLEDGE USE:`. Lexical
overlap elsewhere is retained in the diff/card for later review, but it is not
scored as declared usage.

Prefer these signals:

- Exposure: required OKF concepts were loaded into `KNOWLEDGE_CONTEXT`.
- Declaration: model output includes `KNOWLEDGE USE:` and names concrete OKF
  concept IDs from the exposed context with `reason=` plus symbol, diff,
  fixture, or metric traceability.
- Specificity: declared usage references a decision, contract, fixture, source,
  or tolerance rather than a generic page.
- Gate alignment: candidate passed an evaluator-reported semantic gate. Static
  and KG-decision acceptance policy is recorded separately as
  `acceptance_policy_passed`.
- Contradiction: candidate does not violate immutable contracts or KG decisions.
- Traceability: Graphify candidate metadata links code, diff, prompt lineage,
  OKF concepts, and evaluator metrics.

`declared_usage_score` is intentionally a self-report score. It should not be
reported as verified knowledge usage. A future verifier or Graphify semantic
extraction pass can add a separate `verified_usage_score`.
Use `overall_declared_use_score` for this self-report aggregate. The legacy
`overall_knowledge_use_score` field is retained only as a compatibility marker
with a null value and carries `overall_knowledge_use_score_kind` to make that
explicit.

Assessment status values:

- `no_okf_context`: no OKF concept receipts were available.
- `no_declared_usage`: OKF concepts were available, but no `KNOWLEDGE USE:`
  section was present.
- `declared_no_relevant_usage`: the model explicitly wrote
  `KNOWLEDGE USE: none`.
- `declared_usage`: at least one exposed OKF concept ID was declared with
  structured non-empty traceability.
- `declared_usage_unstructured`: at least one exposed OKF concept ID was
  declared, but the declaration lacked non-empty `reason=` and traceability
  fields.
- `declared_usage_unmatched`: a declaration existed, but it did not match any
  exposed OKF concept ID.

## CodeEvolve Application

Adopt OKF as an optional strict profile:

```yaml
KNOWLEDGE_CONTEXT:
  enabled: true
  required: true
  require_okf: true
  okf_bundle_root: wiki
  paths:
    - wiki/overview.md
    - wiki/decisions/require-kg-interaction-for-wrf-physics-changes.md
```

`require_okf: true` should fail fast if selected Markdown files lack parseable
frontmatter or a non-empty `type` field. When OKF context is used, the prompt
instructs the model to prepend a section like:

```text
KNOWLEDGE USE:
- decisions/require-kg-interaction-for-wrf-physics-changes: symbol=kernel; diff=SEARCH_REPLACE_1; reason=preserves the semantic-change acceptance rule.
<<<<<<< SEARCH
...
```

For WRF physics optimization, use the OKF bundle as the source of selected
context and decisions, but keep raw WRF code, driver contracts, fixtures, and
evaluator results as the final authority.

WRF runs that disable knowledge context or OKF context must set both
`KNOWLEDGE_GATE.allow_non_okf_context: true` and
`KNOWLEDGE_GATE.non_okf_context_justification`; otherwise preflight fails. For
generated candidates, set semantic candidate enforcement to require both
configured decision IDs and declared OKF concept use:

```yaml
KNOWLEDGE_GATE:
  semantic_change_policy:
    default: reject_without_kg_decision
    candidate_enforcement:
      - require_configured_kg_decision_ids
      - require_declared_okf_concept_use
```

WRF runs that override the default semantic policy to
`allow_without_kg_decision` must also set
`KNOWLEDGE_GATE.allow_semantic_policy_override: true` and a non-placeholder
`KNOWLEDGE_GATE.semantic_policy_justification`. Both fields are recorded in the
knowledge-gate receipt so generic comparison runs cannot silently disable the
WRF KG-use gate.

## Adoption Decision

Adopt OKF for KG/wiki portability and concept identity. Add a separate
CodeEvolve knowledge-use receipt before claiming that the system can quantify
how much knowledge influenced a candidate edit.
