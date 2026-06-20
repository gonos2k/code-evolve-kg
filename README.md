# code-evolve-kg

CodeEvolve KG/WRF/Graphify development bundle.

This repository contains both the Codex skill and a full local development
snapshot of the CodeEvolve KG integration work.

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
- `science-codeevolve/`: full CodeEvolve working tree snapshot for development,
  including source, tests, docs, problems, wiki pages, Graphify output, and local
  development environment files

## Local Install

```bash
mkdir -p ~/.codex/skills/code-evolve-kg
cp -R SKILL.md agents ~/.codex/skills/code-evolve-kg/
```

## Development Snapshot

The `science-codeevolve/` directory is intentionally broad because this
repository is used as a development handoff bundle. It keeps the current local
state together so KG, Graphify, WRF single-physics problem setup, Fortran
toolchain support, tests, and generated inspection artifacts can be reviewed as
one unit.
