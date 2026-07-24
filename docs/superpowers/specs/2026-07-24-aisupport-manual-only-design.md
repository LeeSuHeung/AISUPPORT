# AISUPPORT 수동 전용화 설계

## 목적

AISUPPORT가 설치하는 Skill, 구파발 역할 에이전트, command Hook이 사용자의 명시적 요청 없이 실행되지 않게 한다. 기능 원본은 Git에 유지하여 사용자가 이름이나 설치 옵션을 직접 지정했을 때만 사용할 수 있게 한다.

## 현재 상태

- `caveman`은 전역 `AGENTS.md` 규칙 때문에 모든 답변에 자동 적용된다.
- `using-superpowers`는 전역 규칙과 Skill 설명 때문에 모든 새 작업에서 자동 적용된다.
- 다른 Superpowers Skill은 작업 내용이 설명과 일치하면 자동 선택될 수 있다.
- 구파발 역할 에이전트와 `gupabal-game` Skill은 게임 작업의 분야에 따라 자동 선택될 수 있다.
- 사용자 `hooks.json`에는 `apply_patch` 전후와 구파발 에이전트 종료 시 실행되는 command Hook이 등록되어 있다.

## 범위

### 포함

- AISUPPORT가 관리하는 18개 Skill을 명시적 호출 전용으로 변경한다.
- Caveman과 Superpowers의 전역 자동 실행 규칙을 제거한다.
- 구파발 역할 에이전트는 `구파발게임` 또는 역할 이름을 사용자가 명시한 경우에만 사용한다.
- 구파발 command Hook은 기본 설치 및 기본 검증 대상에서 비활성 상태가 되게 한다.
- 기존 사용자 Hook 설정에서 AISUPPORT가 관리하는 handler만 제거하고 다른 Hook은 보존한다.
- lock, 무결성 manifest, 설치기, 테스트, 사용자 문서를 새 동작에 맞춘다.
- 사용자 설치본을 백업 가능한 설치 절차로 갱신한다.

### 제외

- Codex 자체 시스템 Skill과 외부 플러그인의 자동 선택 동작은 변경하지 않는다.
- Skill 본문, 구파발 에이전트 정의, Hook 구현 원본은 삭제하지 않는다.
- Hook과 관계없는 사용자 설정은 변경하지 않는다.
- 현재 열려 있는 Codex 작업에 이미 로드된 지침을 강제로 제거하지 않는다.

## 동작 설계

### Skill 호출

각 `.agents/skills/<skill-name>/SKILL.md`의 `description`은 해당 Skill 이름을 사용자가 명시한 경우에만 사용하는 조건으로 바꾼다. 예를 들어 `using-superpowers`는 `$using-superpowers` 또는 정확한 Skill 이름을 사용자가 요청했을 때만 로드된다. Skill이 한 번 명시적으로 호출된 뒤 따르는 내부 절차는 유지한다.

### 전역 지침

`AGENTS.md`의 managed block은 다음만 유지한다.

- Skill과 Hook의 Git 원본 및 설치 위치 정책
- 안전, 기존 변경 보존, 검증 규칙
- 명시적으로 호출된 Skill을 따르는 방법

모든 답변에 Caveman을 적용하거나 모든 작업에서 Superpowers 절차를 시작하는 규칙은 제거한다.

`.codex/gupabal/AGENTS.md`는 구파발 팀이나 개별 역할을 사용자가 직접 지정했을 때만 역할 선택과 합의 절차를 적용하도록 바꾼다.

### Hook 등록

통합 설치기와 구파발 설치기는 기본적으로 AISUPPORT 관리 Hook handler가 없는 상태를 설치·검증한다. 명시적인 `--with-hooks` 또는 PowerShell의 `-WithHooks` 옵션을 제공한 경우에만 Hook을 등록한다.

기본 설치가 기존 설정을 갱신할 때는 다음 순서를 지킨다.

1. 사용자 `hooks.json`을 읽는다.
2. 경로와 파일 형식이 안전한지 확인한다.
3. AISUPPORT 관리 handler만 제거한다.
4. 다른 handler와 설정을 그대로 보존한다.
5. 변경 전 파일을 백업한다.
6. 임시 파일을 사용해 원자적으로 교체한다.

기존 버전별 Hook 스크립트 파일은 등록이 없으면 실행되지 않으므로 자동 삭제하지 않는다. 이는 불필요한 데이터 삭제 위험을 피한다.

### 사용자 설치본 동기화

저장소 검증이 끝난 뒤 통합 설치기를 `-Force`로 실행한다. 설치기는 기존 AISUPPORT 관리 Skill과 전역 지침을 백업한 뒤 수동 전용 버전으로 교체하고, 관리 Hook handler를 제거한다. 새 동작은 새 Codex 작업에서 확인하며 필요하면 Codex를 재시작한다.

## 변경 대상

- `.agents/skills/*/SKILL.md`: 18개 Skill의 호출 조건
- `AGENTS.md`: Caveman·Superpowers 자동 실행 규칙
- `.codex/gupabal/AGENTS.md`: 구파발 역할 자동 선택 규칙
- `scripts/install-caveman.mjs`: 수동 전용 Skill 검증과 설치
- `scripts/install_gupabal.py`: Hook 기본 비활성 및 명시적 활성 옵션
- `scripts/merge_gupabal_hooks.py`: 관리 Hook 제거·검증 기능
- `scripts/install-aisupport.mjs`와 셸별 wrapper: `with-hooks` 옵션 전달
- `skills-lock.json`, `caveman-manifest.json`, `superpowers-manifest.json`, `gupabal-manifest.json`: 변경 파일의 무결성 값
- 관련 installer·Hook·Windows 테스트
- `README.md`, `CAVEMAN.md`, `SUPERPOWERS.md`, `GUPABAL_GAME.md`: 수동 호출과 Hook 활성 방법

## 오류 처리와 안전

- 형식이 잘못된 `hooks.json`, 일반 파일이 아닌 대상, 관리 여부를 판별할 수 없는 handler는 변경하지 않고 오류로 중단한다.
- `--force` 없이 다른 내용의 관리 파일을 덮어쓰지 않는다.
- 사용자 설정을 바꾸기 전 백업을 만든다.
- AISUPPORT 관리 경로와 command 패턴이 확인된 Hook만 제거한다.
- Git의 기존 사용자 변경은 보존하고 이번 작업 파일만 커밋한다.

## 테스트

- 모든 AISUPPORT Skill 설명이 명시적 호출 조건인지 정적 검사한다.
- managed `AGENTS.md` 블록에 자동 시작 규칙이 없는지 검사한다.
- Hook 기본 설치가 관리 handler를 제거하고 다른 handler를 보존하는지 검사한다.
- `--with-hooks`가 기존 Hook 설치 동작을 복원하는지 검사한다.
- dry-run, install, verify가 같은 상태를 판단하는지 검사한다.
- Caveman/Superpowers installer, 구파발 installer, Hook 단위 테스트, Windows 회귀 테스트를 실행한다.
- 사용자 설치본 검증에서 Skill·전역 지침은 일치하고 관리 Hook handler는 없는지 확인한다.

## 완료 기준

- 새 Codex 작업에서 사용자가 Skill 이름을 말하지 않으면 AISUPPORT Skill이 자동 호출되지 않는다.
- 게임 작업만으로 구파발 역할 에이전트가 자동 생성되지 않는다.
- `apply_patch`와 에이전트 종료만으로 구파발 command Hook이 실행되지 않는다.
- `$using-superpowers`, `$caveman`, `구파발게임`처럼 사용자가 명시하면 해당 기능을 사용할 수 있다.
- 명시적 Hook 설치 옵션을 사용하면 Hook을 다시 활성화할 수 있다.
- 관련 테스트와 설치 검증이 모두 통과한다.
