# AISUPPORT 1~7 개선 구현 계획

> 실행 방식: 현재 세션에서 구파발게임의 역할 합의·단독 파일 소유권을 우선 적용한다. 각 작업은 RED → GREEN → 관련 회귀 검증 순서로 끝낸 뒤 다음 번호로 이동한다.

**목표:** 감사에서 확인한 일곱 결함을 순차 수정하고, 다른 Windows PC와 프로젝트에서도 재현 가능한 설치·합의·검증 흐름을 만든다.

**구조:** Node 통합 설치기가 공통 경로와 UTF-8 실행을 책임진다. Python Hook merger는 공식 Windows `cmd.exe /C` 계약에 맞춘 명령을 만든다. Gupabal Hook은 exact Git-root 정책, schema v2 승인 digest, 전체 에셋 verifier를 한 기준 구현으로 제공한다.

**기술:** Node.js 18+, Python 3.10+, 표준 라이브러리, Windows `cmd.exe`, `unittest`, Git Bash.

---

## Task 1: 통합 Python UTF-8

**파일:**

- 수정: `scripts/test-caveman-installer.mjs`
- 수정: `scripts/install-aisupport.mjs`

1. `PYTHONUTF8=0`, 공백·한글·이모지 임시 경로에서 통합 dry-run/install/verify를 실행하는 회귀 테스트를 추가한다.
2. `node scripts/test-caveman-installer.mjs`를 실행해 기존 코드의 encode 실패를 확인한다.
3. Gupabal Python 자식 인수에 `-X utf8`을 추가한다.
4. 같은 테스트를 다시 실행해 통과를 확인한다.

## Task 2: `CODEX_HOME`과 `~` 통일

**파일:**

- 수정: `scripts/test-caveman-installer.mjs`
- 수정: `scripts/install-aisupport.mjs`
- 수정: `scripts/install-caveman.mjs`
- 수정: `.agents/skills/gupabal-game/SKILL.md`
- 수정: `gupabal-manifest.json`

1. `CODEX_HOME=~/<고유 경로>`와 명시적 `--agents-file` 우선순위 테스트를 추가한다.
2. Node 설치기에서 문자 그대로의 `~` 경로가 나오는 RED를 확인한다.
3. 최상위 경로 정규화와 개별 Node `~` 확장을 구현한다.
4. Skill fallback을 `$CODEX_HOME/agents`, 미설정 `~/.codex/agents`로 수정한다.
5. Skill source hash를 manifest에 갱신하고 Node·Python 설치 검증을 실행한다.

## Task 3: Windows `commandWindows`

**파일:**

- 추가: `tests/test_gupabal_windows.py`
- 수정: `scripts/merge_gupabal_hooks.py`
- 수정: `gupabal-manifest.json`

1. 공백·`&`·괄호·`!`·`%`·작은따옴표·한글·이모지 임시 Hook 경로에서 생성된 명령을 실제 `cmd.exe /D /S /V:OFF /C`와 `/V:ON /C`로 실행하는 Windows 테스트를 추가한다.
2. `!NAME!` 경로에서 직접 인용한 명령이 delayed expansion으로 변형되는 RED를 확인한다.
3. 이벤트별 PowerShell 명령문을 single-quoted literal로 만들고 UTF-16LE `EncodedCommand`로 전달해 경로 문자를 바깥 `cmd.exe`에서 숨긴다.
4. stdin·이벤트 인수·자식 exit code·정확히 한 번 실행, merger 회귀 테스트, manifest 검증을 통과시킨다.

## Task 4: exact Git root와 조건부 fail-closed

**파일:**

- 수정: `tests/test_gupabal_hooks.py`
- 수정: `.codex/hooks/gupabal_hooks.py`
- 수정: `gupabal-manifest.json`

1. nested decision shadowing, `.git` file worktree, malformed/oversize/unsupported policy, exact boolean `enabled`, exact integer schema, decision-only Add/Update 복구, 혼합·Move·Delete 거부 테스트를 추가한다.
2. 기존 nearest-decision과 fail-open 동작의 RED를 확인한다.
3. exact root lookup과 policy load 상태를 구현한다.
4. 활성 policy를 확정한 오류만 fail-closed로 처리하고 내부 예외는 구조화된 경고로 남긴다.
5. Hook 전체 테스트와 설치 manifest 검증을 실행한다.

## Task 5: exact-one-owner

**파일:**

- 수정: `tests/test_gupabal_hooks.py`
- 수정: `.codex/hooks/gupabal_hooks.py`
- 수정: `gupabal-manifest.json`

1. 기존 warn-only 테스트를 0 owner·다중 owner deny 테스트로 바꾸고 동일 owner 중복 glob 허용 테스트를 추가한다.
2. 기존 advisory 동작의 RED를 확인한다.
3. approved 구현 경로마다 owner 고유 집합 크기 1을 강제한다.
4. planning_allow와 decision-only 회귀 테스트를 함께 통과시킨다.

## Task 6: schema v2와 계약 digest

**파일:**

- 수정: `tests/test_gupabal_hooks.py`
- 수정: `.codex/hooks/gupabal_hooks.py`
- 수정: `.agents/skills/gupabal-game/references/decision-template.json`
- 수정: `.agents/skills/gupabal-game/references/decision-policy.md`
- 수정: `.agents/skills/gupabal-game/SKILL.md`
- 수정: `.codex/gupabal/decision.json`
- 수정: `gupabal-manifest.json`

1. canonical digest 고정값, key 순서, 한글, LF/CRLF spec hash, stale approval, spec 탈출·symlink·owner 불일치, active/disabled v1 테스트를 추가한다.
2. schema v1 구현의 RED를 확인한다.
3. v2 schema·digest·spec ref·approval binding 검증을 구현한다.
4. template, policy, Skill을 v2 workflow에 맞춘다.
5. 현재 decision을 실제 합의 내용의 v2로 decision-only migration하고 네 승인에 동일 revision/digest를 기록한다.
6. Skill validation, Hook 테스트, manifest 검증을 통과시킨다.

## Task 7: 완료 전체 에셋 verifier

**파일:**

- 수정: `tests/test_gupabal_hooks.py`
- 수정: `.codex/hooks/gupabal_hooks.py`
- 수정: `.agents/skills/gupabal-game/SKILL.md`
- 수정: `.agents/skills/gupabal-game/references/decision-policy.md`
- 수정: `gupabal-manifest.json`

1. apply_patch와 무관한 미선언 변경, 선언 누락, 이름·용량·크기·헤더 오류, exclude, 성공, exit 0/1/2, no-write snapshot 테스트를 추가한다.
2. CLI가 없어 실패하는 RED를 확인한다.
3. `--verify-project`와 안정적으로 정렬된 JSON 결과를 구현한다.
4. 기존 `checks.art` 필드만 검증하고 PNG chunk/IEND, JPEG SOF·SOS·EOI, GIF image·trailer, WebP chunk·visual chunk, SVG 전체 XML 루트 구조를 끝까지 확인한다. SVG XML import는 lazy 처리한다.
5. Skill 완료 단계가 verifier 성공 후 decision을 닫도록 문서화한다.

## Task 8: 사용자 안내와 설치된 verifier 동기화

**파일:**

- 수정: `GUPABAL_GAME.md`
- 수정: `README.md`
- 수정: `.agents/skills/gupabal-game/SKILL.md`
- 수정: `.agents/skills/gupabal-game/references/decision-policy.md`
- 수정: `tests/test_gupabal_hooks.py`
- 수정: `gupabal-manifest.json`
- 수정: `.codex/gupabal/decision.json`
- 수정: 본 설계와 실행 계획

1. 존재하지 않는 unversioned Hook 경로, 손상 decision의 잘못된 fail-open 설명, 불완전한 완료 상태를 검출하는 문서·Skill 회귀 검사를 추가해 RED를 확인한다.
2. `GUPABAL_GAME.md`에 정확한 Git root, fail-closed와 decision-only 복구, schema v2 revision/digest/spec/고유 owner, 완료 verifier 0/1/2·`checked: 0`, 구조 검사 한계, source/runtime 차이를 초보자용으로 설명한다.
3. Skill은 최초 설치와 같은 인수의 installer verify 전체 exit `0`과 `OK ...gupabal_hooks_<sha16>.py`를 확인하고, verify를 성공시킨 Python 3.10+로 그 정확한 경로의 `--verify-project <Git root>`를 실행하게 한다. `MISMATCH`면 완료를 중단한다.
4. 정상 완료는 `completed`와 빈 unresolved로, 의도적인 취소는 새 enum 없이 비활성 `planning`·취소 사유·초기화된 digest/approvals로 구분한다. 둘 다 old approval 재사용을 막고 재개 시 revision 증가·재승인을 요구한다.
5. `README.md`와 상세 안내의 `/hooks`를 Codex CLI 범위로 명확히 하고, 문서 drift를 줄이기 위해 상세 schema는 canonical policy 문서에 연결한다.
6. 새 spec hash와 contract digest를 계산하고 네 역할이 revision 5의 같은 digest에 재승인한 뒤 문서·Skill 구현을 시작한다.

## Task 9: 전체 검증과 마무리

**파일:**

- 수정: `.codex/gupabal/decision.json`
- 필요 시 수정: `gupabal-manifest.json`

1. `node scripts/test-caveman-installer.mjs` 실행.
2. `py -3 -X utf8 -B -m unittest discover -s tests -v` 실행.
3. Git Bash에서 `tests/test_install_sh.sh` 실행.
4. source manifest, 임시 설치·verify, 실제 wrapper dry-run을 실행해 소스 acceptance를 확인한다.
5. system `skill-creator` validator를 먼저 실행한다. PyYAML 부재로 import 전에 끝나면 `NOT RUN`으로 기록하고, 의존성을 자동 설치하지 않은 채 같은 frontmatter 규칙의 동등 검사와 Node·Hook·Skill 회귀 검사를 실행한다. 공식 validator 통과로 표현하지 않는다.
6. `git diff --check`, Python/Node/Shell 문법, JSON parse를 실행한다.
7. 구파발 4개 역할의 결합 결과 검토와 독립 코드 리뷰를 실행한다.
8. 사용자 승인을 받은 뒤 canonical AISUPPORT 설치기를 전역 runtime에 적용한다. 최초 설치와 같은 target·agents-file·`CODEX_HOME`으로 실제 `-Verify` 또는 `--verify`를 실행하고 `MISMATCH`가 없는지 확인한다.
9. verify 출력의 정확한 versioned Hook을 성공한 Python 3.10+로 실행해 `--verify-project <정확한 Git root>` exit `0`을 확인한다. 에셋 범위가 비어 `checked: 0`이면 시각 품질 통과로 표현하지 않는다.
10. 전역 runtime 검증까지 끝난 뒤에만 decision을 `enabled: false`, `agreement.status: completed`, 빈 unresolved, null digest와 초기화된 approvals로 별도 patch한다. 전역 변경 승인이 없으면 소스 준비 완료와 배포 대기를 분리 보고하고 decision은 닫지 않는다.

## Task 10: Revision 6 독립 리뷰 보강

**파일:**

- 수정: `tests/test_gupabal_hooks.py`
- 수정: `.codex/hooks/gupabal_hooks.py`
- 수정: `tests/test_gupabal_windows.py`
- 수정: `scripts/install_gupabal.py`
- 수정: `GUPABAL_GAME.md`
- 수정: `gupabal-manifest.json`
- 수정: `.codex/gupabal/decision.json`
- 수정: 본 설계와 실행 계획

1. 잘린 비활성 v2, 잘못된 완료·취소 상태, stale approval을 거부하고 정상 완료·취소만 조용히 통과하는 RED 테스트를 추가한다.
2. 비활성 v2의 전체 구조와 종료 규칙을 검사하고, 오류는 decision-only 복구 외 구현 patch를 fail-closed로 막는다.
3. 8 MiB 초과 `PreToolUse` 입력이 전역 deny되는 RED를 확인하고, 지원되는 경고 출력만 남기는 fail-open으로 바꾼다. 파싱된 활성 정책의 4 MiB patch 제한은 유지한다.
4. 실제 Windows junction을 skill target으로 전달했을 때 설치기가 쓰기를 시작하는 RED를 확인한다.
5. Python 3.10·3.11에서도 reparse-point attribute를 검사해 symlink·junction container를 모두 거부한다.
6. `GUPABAL_GAME.md`의 oversize event 안내를 fail-open 계약과 동기화하고 manifest hash를 갱신한다.
7. 관련 테스트를 각각 RED→GREEN으로 확인한 뒤 전체 Node·Python·Git Bash·Skill·runtime 검증과 독립 재리뷰를 실행한다.
