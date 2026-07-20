# Caveman for Codex

This repository vendors the Caveman skill suite for Codex from
[`JuliusBrussee/caveman`](https://github.com/JuliusBrussee/caveman).

## Installed version

- Release: `v1.9.1`
- Upstream commit: `033f918602bd5319931256a537c4bd9ea7a48c25`
- Project skills: `.agents/skills/`
- Reproducibility lock: `skills-lock.json`
- File integrity manifest: `caveman-manifest.json`
- Repository always-on rule: `AGENTS.md`

The files are copied instead of symlinked so they work reliably on Windows and
can be committed to Git. `skills-lock.json` records the upstream tag, source
path, and content hash for every installed skill.

## Portability

Codex automatically scans `.agents/skills` from the current directory up to
the Git repository root. After cloning this repository, these skills therefore
work without downloading or installing anything. Start a new Codex task from
any directory inside the repository. Root `AGENTS.md` activates Caveman `full`
for every new task and response automatically.

Choose one scope:

- Repository only: do not run the bootstrap. Codex uses the checked-in copy.
- Every repository for one user: run the bootstrap once on that computer.

When the user-level copy is installed, Codex may display both the repository
and user copies while working inside this repository. Codex does not merge
same-named skills; both copies are intentionally identical and verified.

To make the same reviewed skills available in every repository for the current
user, run the included offline bootstrap after cloning:

```powershell
# Windows PowerShell
.\scripts\install-caveman.ps1
```

```bash
# macOS or Linux
./scripts/install-caveman.sh
```

The cross-platform implementation is also directly callable:

```bash
node scripts/install-caveman.mjs
```

Requirements: Git and Node.js 18 or newer. The installer copies only the
vendored, version-locked files into `$HOME/.agents/skills`; it performs no
network request and does not execute upstream scripts. It also inserts the
marker-delimited always-on block into `$CODEX_HOME/AGENTS.md` (normally
`$HOME/.codex/AGENTS.md`) while preserving unrelated user instructions.
Existing differing managed content is left untouched unless `--force`
(`-Force` in PowerShell) is supplied. Replaced skill folders and AGENTS files
are backed up first. Existing UTF-8 or BOM-marked UTF-16 encoding and newline
style are preserved. Ambiguous encodings, malformed markers, and non-regular
AGENTS targets such as symbolic links are rejected before managed files change.

Verify an installation without changing it:

```powershell
.\scripts\install-caveman.ps1 -Verify
```

```bash
./scripts/install-caveman.sh --verify
```

If Codex does not immediately show a changed skill, restart Codex. The GitHub
Actions workflow verifies install, verification, idempotency, instruction and
encoding preservation, backups, and conflict handling on Windows, macOS, and
Linux.

## Usage

Caveman `full` starts automatically in every new Codex task. No invocation is
required. Ask for `caveman lite`, `caveman full`, or `caveman ultra` to change
intensity. Say `normal mode` or `stop caveman` to disable it for the current
task; the next new task starts in `full` again.

Additional project skills:

- `$caveman-commit`: concise Conventional Commit message generation
- `$caveman-review`: concise code-review comments

The upstream `caveman-help`, `caveman-compress`, `caveman-stats`, and
`cavecrew` skills are not vendored here. The upstream help card references
features not included in this repository, `caveman-compress` can send named
file contents to Anthropic and replace the local file, `caveman-stats` depends
on Claude Code hooks, and `cavecrew` changes subagent behavior. They are outside
this repository's minimal Caveman integration.

## Update

Update intentionally by replacing `v1.9.1` with the desired reviewed release:

```powershell
npx -y skills@latest add https://github.com/JuliusBrussee/caveman/tree/v1.9.1 --agent codex --skill caveman caveman-commit caveman-review --yes --copy --full-depth
```

Review the resulting skill and lock-file diff before committing.
