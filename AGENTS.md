<!-- BEGIN CAVEMAN PORTABLE ALWAYS-ON -->
## AISUPPORT skill defaults

### Caveman always-on

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

### Superpowers always-on

- Caveman controls response compression; Superpowers controls workflow and
  evidence. Keep required Superpowers skill announcements terse.
- Apply the available `using-superpowers` skill at the start of every new root
  task, before any response or action. Respect its `SUBAGENT-STOP` rule for
  subagents dispatched with a concrete task.
- Invoke each relevant Superpowers process skill before implementation. Direct
  user instructions and higher-priority system or developer instructions still
  take precedence.
- This repository installs Superpowers as standard Codex skills. Resolve an
  upstream reference such as `superpowers:writing-plans` to the installed
  `writing-plans` skill with the same suffix.
- Keep the optional visual brainstorming companion off unless the user
  explicitly opts in. When it is used, set `SUPERPOWERS_DISABLE_TELEMETRY=1`
  so its remote brand image is not requested.
- Apply TDD prospectively. Never delete or revert pre-existing or user-authored
  code solely because a Superpowers TDD workflow says implementation preceded
  its test.
- Before a workflow installs dependencies or runs package lifecycle scripts,
  verify that the repository's own instructions require them and inspect the
  relevant manifest or lockfile.
- For Codex skill creation, follow the system `skill-creator` skill first and
  use Superpowers `writing-skills` only as supplemental guidance.
- Superpowers workflows do not grant extra authority. Keep merge, push,
  deployment, worktree removal, and other destructive or external actions
  within the user's request and the active safety policy.

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
