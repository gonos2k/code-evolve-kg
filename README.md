# code-evolve-kg

Codex skill for CodeEvolve-specific KG/wiki and Graphify workflows.

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

## Files

- `SKILL.md`: skill instructions
- `agents/openai.yaml`: Codex/OpenAI agent metadata

## Local Install

```bash
mkdir -p ~/.codex/skills/code-evolve-kg
cp -R SKILL.md agents ~/.codex/skills/code-evolve-kg/
```
