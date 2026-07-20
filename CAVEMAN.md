# Caveman for Codex

This repository vendors the Caveman skill suite for Codex from
[`JuliusBrussee/caveman`](https://github.com/JuliusBrussee/caveman).

## Installed version

- Release: `v1.9.1`
- Upstream commit: `033f918602bd5319931256a537c4bd9ea7a48c25`
- Project skills: `.agents/skills/`
- Reproducibility lock: `skills-lock.json`
- File integrity manifest: `caveman-manifest.json`

The files are copied instead of symlinked so they work reliably on Windows and
can be committed to Git. `skills-lock.json` records the upstream tag, source
path, and content hash for every installed skill.

## Portability

Codex automatically scans `.agents/skills` from the current directory up to
the Git repository root. After cloning this repository, these skills therefore
work without downloading or installing anything. Start a new Codex task from
any directory inside the repository.

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
network request and does not execute upstream scripts. Existing differing
skills are left untouched unless `--force` (`-Force` in PowerShell) is supplied;
forced replacements are backed up first under `$HOME/.agents/skill-backups`,
outside Codex's active skill directory.

Verify an installation without changing it:

```powershell
.\scripts\install-caveman.ps1 -Verify
```

```bash
./scripts/install-caveman.sh --verify
```

If Codex does not immediately show a changed skill, restart Codex. The GitHub
Actions workflow verifies install, verification, and idempotent reinstallation
on Windows, macOS, and Linux.

## Usage

Open a new Codex task after installation, then invoke `$caveman` or say
`caveman mode`. Supported intensity levels are `lite`, `full`, and `ultra`.
Say `normal mode` to turn it off.

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
