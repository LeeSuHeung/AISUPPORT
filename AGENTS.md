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
## Manual execution defaults

- Do not invoke AISUPPORT skills unless the user explicitly names the skill.
- Do not spawn subagents or delegate work unless the user explicitly requests
  delegation or explicitly invokes a workflow that requires it.
- Do not create or switch branches, create commits or pull requests, push,
  dispatch workflows, enable lifecycle hooks, start background helpers, or
  create scheduled or recurring automations unless the user explicitly
  requests that exact action.
- When the user does not request another branch, stay on `master`.
- Tests and verification needed to finish an explicitly requested change may
  run once in that task. Never schedule or repeat them in the background.
- After explicit invocation, follow that skill for the current task within the user's scope.

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
- After validation, commit or push completed skill or hook changes only when
  the user explicitly requests that exact publishing action; otherwise leave
  the validated changes ready and report their state.
<!-- END CAVEMAN PORTABLE ALWAYS-ON -->
