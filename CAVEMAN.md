# Caveman for Codex

This repository vendors the Caveman skill suite for Codex from
[`JuliusBrussee/caveman`](https://github.com/JuliusBrussee/caveman).

## Installed version

- Release: `v1.9.1`
- Upstream commit: `033f918602bd5319931256a537c4bd9ea7a48c25`
- Project skills: `.agents/skills/`
- Reproducibility lock: `skills-lock.json`
- File integrity manifest: `caveman-manifest.json`
- Default activation guidance: `AGENTS.md`

The files are copied instead of symlinked so they work reliably on Windows and
can be committed to Git. `skills-lock.json` records the upstream tag, source
path, and content hash for every installed skill.

## Portability

Codex automatically scans `.agents/skills` from the current directory up to
the Git repository root. After cloning this repository, these skills therefore
work without downloading or installing anything. Start a new Codex task from
any directory inside the repository. Caveman starts on every task and Ponytail
on every coding task; invoke all other skills explicitly when needed.

Choose one scope:

- Repository only: do not run the bootstrap. Codex uses the checked-in copy.
- Every repository for one user: run the bootstrap once on that computer.

When the user-level copy is installed, Codex may display both the repository
and user copies while working inside this repository. Codex does not merge
same-named skills; both copies are intentionally identical and verified.

To make the reviewed AISUPPORT skill suite (Caveman, Ponytail, and Superpowers)
available in every repository for the current user, run the included offline
bootstrap after cloning:

```powershell
# Windows PowerShell
.\scripts\install-aisupport.ps1
```

```bash
# macOS or Linux
./scripts/install-aisupport.sh
```

The cross-platform implementation is also directly callable:

```bash
node scripts/install-aisupport.mjs
```

Requirements: Git and Node.js 18 or newer. The installer copies only the
vendored, version-locked files into `$HOME/.agents/skills`; it performs no
network request and does not execute upstream scripts. It also inserts the
marker-delimited managed instruction block into `$CODEX_HOME/AGENTS.md` (normally
`$HOME/.codex/AGENTS.md`) while preserving unrelated user instructions.
Existing differing managed content is left untouched unless `--force`
(`-Force` in PowerShell) is supplied. Replaced skill folders and AGENTS files
are backed up first. Existing UTF-8 or BOM-marked UTF-16 encoding and newline
style are preserved. Ambiguous encodings, malformed markers, and non-regular
AGENTS targets such as symbolic links are rejected before managed files change.

Verify an installation without changing it:

```powershell
.\scripts\install-aisupport.ps1 -Verify
```

```bash
./scripts/install-aisupport.sh --verify
```

If Codex does not immediately show a changed skill, restart Codex. The GitHub
Actions workflow never starts automatically from a push or pull request. When
explicitly dispatched, it verifies install, verification, idempotency,
instruction and encoding preservation, backups, and conflict handling on
Windows, macOS, and Linux. The legacy `install-caveman.*` entry points remain
compatible aliases and now install the same complete AISUPPORT suite.

## AISUPPORT extension policy

AISUPPORT is the canonical Git source for Codex skills and lifecycle hooks made
for this user. New skills belong in `.agents/skills/<skill-name>/`. Project hook
configuration should normally use `.codex/hooks.json`, with supporting scripts
under `.codex/hooks/`. User-level copies are installation targets, not the only
source of truth.

When a new skill or hook needs user-wide activation, extend the checked-in
bootstrap and integrity metadata so another computer can reproduce the same
installation from this repository. Validate the change, then commit or push it
only when the user explicitly requests that exact publishing action.

## Usage

Caveman starts in full mode for every new task and applies to every response.
Ask for `caveman lite`, `caveman full`, or `caveman ultra` to change intensity.
Say `normal mode` or `stop caveman` to disable it for the current task.

Do not start subagents, background helpers, scheduled work, branches, commits,
pushes, pull requests, Hooks, or GitHub workflows merely because a skill makes
them available. Each action requires an explicit user request. A one-time test
needed to finish an explicitly requested change is allowed, but it is never
scheduled or repeated in the background.

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
