# code-evolve-kg

CodeEvolve KG/WRF/Graphify development bundle.

This repository contains both the Codex skill and a full local development
snapshot of the CodeEvolve KG integration work. The snapshot is source-focused:
virtual environments, test caches, bytecode, and generated Graphify output are
not part of the current tree.

Use this skill when modifying or reviewing CodeEvolve support for:

- `KNOWLEDGE_CONTEXT`
- `GRAPHIFY_EXPORT`
- evolved-code corpora
- OKF-compatible KG/wiki bundles
- WRF single-physics problem setup
- Fortran evaluator/toolchain integration
- KG-backed prompt and evaluation gates

This skill is intentionally separate from the generic `kg-*` skill family. It
keeps CodeEvolve runtime integration file-based and auditable, without adding
runtime dependencies on KG MCP servers, wiki internals, or OKF services.

## Layout

- `SKILL.md`: Codex skill instructions
- `agents/openai.yaml`: Codex/OpenAI agent metadata
- `science-codeevolve/`: CodeEvolve working tree snapshot for development,
  including source, tests, docs, problems, and wiki pages
- `.github/workflows/ci.yml`: repository-level CI that runs inside
  `science-codeevolve/`

## Local Install

```bash
mkdir -p ~/.codex/skills/code-evolve-kg
cp -R SKILL.md agents ~/.codex/skills/code-evolve-kg/
```

## Development Snapshot

The `science-codeevolve/` directory is intentionally broad because this
repository is used as a development handoff bundle. It keeps the current source
state together so KG, Graphify, WRF single-physics problem setup, Fortran
toolchain support, tests, and documentation can be reviewed as one unit.

## Security Boundary

The current evaluator uses subprocess execution, temporary working directories,
timeouts, memory monitoring, and process cleanup. That is resource containment,
not a security sandbox. Do not run untrusted LLM-generated code from this
snapshot on a sensitive host. Production or multi-tenant use requires a separate
isolation layer such as a rootless container, network-denied jail, read-only
filesystem, environment allowlist, non-privileged UID, cgroup limits, and syscall
filtering.

## License Boundary

The wrapper skill files at the repository root are distributed under this
repository's MIT license. The `science-codeevolve/` snapshot is derived from the
CodeEvolve project and keeps its Apache-2.0 license in
`science-codeevolve/LICENSE`.
