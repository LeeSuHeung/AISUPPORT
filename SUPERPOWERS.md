# Superpowers for Codex

AISUPPORT vendors the complete Codex skill set from
[`obra/superpowers`](https://github.com/obra/superpowers) so the reviewed
version can be reproduced without running an upstream installer.

## Installed version

- Release: `v6.1.1`
- Upstream commit: `d884ae04edebef577e82ff7c4e143debd0bbec99`
- License: MIT
- Project skills: `.agents/skills/`
- Reproducibility lock: `skills-lock.json`
- File integrity manifest: `superpowers-manifest.json`
- Automatic root-task activation: `AGENTS.md`

All 14 upstream Codex skills are included: brainstorming, parallel-agent
dispatch, plan writing and execution, subagent-driven development, TDD,
systematic debugging, worktrees, code review, completion verification, branch
finishing, skill writing, and the `using-superpowers` entry workflow.
Upstream text sometimes names a skill as `superpowers:<name>`; the AISUPPORT
direct install resolves that to the standard Codex skill named `<name>`.

## Portability and activation

Codex automatically discovers the checked-in copy while working inside this
repository. For every repository on one computer, clone AISUPPORT and run the
offline bootstrap once:

```powershell
# Windows PowerShell
.\scripts\install-aisupport.ps1
```

```bash
# macOS or Linux
./scripts/install-aisupport.sh
```

The bootstrap requires Node.js 18 or newer. It copies the reviewed Caveman and
Superpowers skills to `$HOME/.agents/skills` and installs the marker-delimited
defaults from `AGENTS.md` into `$CODEX_HOME/AGENTS.md` (normally
`$HOME/.codex/AGENTS.md`). It makes no network request and executes no vendored
Superpowers helper script. Existing unrelated user instructions are preserved.

An older Caveman-only installation contains a previous managed block, so the
installer intentionally stops. Review the migration, then let it back up and
replace only AISUPPORT-managed content:

```powershell
.\scripts\install-aisupport.ps1 -DryRun -Force
.\scripts\install-aisupport.ps1 -Force
```

```bash
./scripts/install-aisupport.sh --dry-run --force
./scripts/install-aisupport.sh --force
```

Run verification without changing files:

```powershell
.\scripts\install-aisupport.ps1 -Verify
```

```bash
./scripts/install-aisupport.sh --verify
```

Start a new Codex task after installation; restart Codex if the new skills do
not appear. Parallel and subagent-driven workflows require Codex multi-agent
tools. If they are unavailable and local policy permits, enable them in
`$CODEX_HOME/config.toml` and start a new task:

```toml
[features]
multi_agent = true
```

Installations without subagent tools can still use planning, TDD, debugging,
and verification skills.

## Safety defaults

Superpowers adds workflows, not authority. Its merge, push, worktree cleanup,
and other external or destructive steps remain subject to the user's request
and Codex safety rules. AISUPPORT also prevents the TDD workflow from deleting
pre-existing or user-authored code merely because a test was written later,
and requires repository instructions plus manifest review before dependency or
package-lifecycle execution.

The optional visual brainstorming companion can run a local HTTP server and,
upstream by default, load a remote brand image. AISUPPORT keeps that companion
off until the user explicitly opts in and requires
`SUPERPOWERS_DISABLE_TELEMETRY=1` when it runs.

Several upstream helpers use POSIX shell tools: the visual companion launchers,
subagent review/brief helpers, debugging polluter search, and skill graph
renderer. They run directly on macOS/Linux; Windows needs Git Bash or WSL.
AISUPPORT's installer, skill discovery, planning, TDD, debugging method, and
verification workflows remain native Windows-compatible. The graph renderer
also needs Graphviz when explicitly used.

## Updating

Updates are intentional: select a reviewed upstream release, vendor all 14
skill directories, update `skills-lock.json` and
`superpowers-manifest.json`, run the portable installer tests, and review the
complete diff before committing. Do not replace the pinned source with a
remote `curl | sh`, `irm | iex`, or auto-update path.
