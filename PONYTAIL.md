# Ponytail for Codex

AISUPPORT vendors the reviewed Ponytail `v4.8.4` skills from
[`DietrichGebert/ponytail`](https://github.com/DietrichGebert/ponytail), pinned
to commit `bc9ee949d5f439e8b9f3bb92c6d6d3d1e6ebd324`.

## Default behavior

- `ponytail` applies automatically to every coding task in full mode.
- It checks existing code, the standard library, native platform features, and
  installed dependencies before adding new code or packages.
- It never removes requested validation, data-loss protection, security, or
  accessibility.
- `caveman` and `ponytail` are the only automatically invoked AISUPPORT skills.

Say `stop ponytail` to disable Ponytail for the current task. Say
`ponytail lite`, `ponytail full`, or `ponytail ultra` to change intensity.

## Optional skills

These remain manual and run only when named:

- `$ponytail-review`: review the current diff for removable complexity
- `$ponytail-audit`: scan the repository for over-engineering
- `$ponytail-debt`: list deliberate `ponytail:` shortcuts
- `$ponytail-gain`: show the published benchmark card
- `$ponytail-help`: show the command reference

## Installation

The normal AISUPPORT installer copies the pinned skills into
`$HOME/.agents/skills` and verifies their hashes. Ponytail lifecycle hooks are
not required for this setup and remain disabled. Automatic use comes from the
managed `AGENTS.md` rule and the vendored `ponytail` skill.
