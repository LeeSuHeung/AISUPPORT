<!-- BEGIN CAVEMAN PORTABLE ALWAYS-ON -->
## Caveman always-on

- Apply the available `caveman` skill to every response by default, using
  `full` intensity.
- Keep Caveman active across the entire task. Do not announce the mode or add a
  second normal-prose recap.
- Preserve all technical substance, code, commands, API names, paths, and exact
  error text.
- Follow the skill's Auto-Clarity exceptions for security warnings,
  irreversible actions, and instructions where compression could be ambiguous.
- If the user says `normal mode` or `stop caveman`, disable it for the rest of
  the current task unless the user explicitly enables it again.
- Start each new task with Caveman `full` active.

## AISUPPORT skill and hook policy

- Treat `https://github.com/LeeSuHeung/AISUPPORT.git` as the canonical source
  for every Codex skill or lifecycle hook created or updated for this user.
- Use an existing AISUPPORT worktree when available. If none exists, clone it
  to `$HOME/AISUPPORT`; never leave the only source copy in a user-profile
  runtime directory.
- Store skill sources under `.agents/skills/<skill-name>/`.
- Prefer `.codex/hooks.json` for project hook configuration and
  `.codex/hooks/` for its scripts. Keep user-wide hook sources here too, then
  update the bootstrap so it installs them into `$CODEX_HOME`.
- When a skill or hook must run outside AISUPPORT, update the checked-in
  bootstrap and integrity metadata so the runtime copy is reproducible from
  this repository.
- After validation, commit and push completed skill or hook changes to
  AISUPPORT `origin` unless the user explicitly requests a local-only change
  or push is blocked.
<!-- END CAVEMAN PORTABLE ALWAYS-ON -->
