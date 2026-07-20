# Beginner Collaboration Guide

- 사용자는 개발과 Codex 사용 모두 초보자라고 가정한다.
- 전문 용어가 필요하면 처음 등장할 때 쉬운 말로 설명한다.
- 작업을 시작할 때 현재 폴더의 구조와 관련 파일을 먼저 확인한다.
- 사용자가 현황 파악이나 추천을 요청한 경우에는 파일을 변경하지 않고 다음 내용을 먼저 설명한다.
  1. 현재 상태
  2. 가장 작고 안전하게 개선할 수 있는 작업
  3. 작업 목적
  4. 변경할 파일
  5. 실행할 명령
  6. 예상되는 위험
  7. 완료 여부를 확인하는 방법
- 사용자가 구현이나 변경을 명시적으로 요청하면 기존 변경을 보존하면서 작업한다.
- 삭제, 대량 덮어쓰기, 중요한 설정 변경처럼 복구하기 어려운 작업은 대상과 영향을 먼저 설명하고 확인을 받는다.
- 구현 후에는 관련 테스트나 검증을 실행한다.
- 마지막에는 변경한 내용, 검증 결과, 남은 위험이나 확인하지 못한 부분을 쉬운 말로 정리한다.

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
- Repository or user instructions requiring beginner-friendly explanations
  take priority over compression. In those contexts, use complete sentences
  and switch to Caveman `lite` whenever `full` would reduce clarity.
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
- Tests and fixtures may model existing behavior or agreed contracts, but must
  not invent product requirements, production code, or art assets.
- Before a workflow installs dependencies or runs package lifecycle scripts,
  verify that the repository's own instructions require them and inspect the
  relevant manifest or lockfile.
- For Codex skill creation, follow the system `skill-creator` skill first and
  use Superpowers `writing-skills` only as supplemental guidance.
- Superpowers workflows do not grant extra authority. Keep merge, push,
  deployment, worktree removal, and other destructive or external actions
  within the user's request and the active safety policy.
- Superpowers skill selection happens before repository inspection; it does
  not waive repository rules that require status-first, no-write analysis, or
  preservation of existing changes.
- When `gupabal-game` applies, its named-role selection, cross-review,
  agreement gate, and exclusive file ownership override generic Superpowers
  parallel-agent and subagent-driven-development workflows. Superpowers may
  support the agreed workflow but must not bypass it.

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
- After validation, commit and push completed skill or hook changes only when
  publishing is within the user's current request; otherwise leave the
  validated changes ready and report their state.
<!-- END CAVEMAN PORTABLE ALWAYS-ON -->
