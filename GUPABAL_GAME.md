# 구파발게임 Codex 팀

기획자, 아트디자이너, 클라이언트 개발자, 서버 개발자 역할과 안전한 작업 Hook을 여러 PC의 Codex에서 공통으로 사용하기 위한 설정 저장소입니다. 게임 기능이나 프로젝트 코드는 포함하지 않습니다.

## 포함된 역할

- `구파발기획자`: 시스템, 성장, 경제, 수치 밸런스
- `구파발아트디자이너`: 아트 방향, UI 시각 체계, 캐릭터·환경·에셋 규격
- `구파발클라이언트`: 화면, 입력, 렌더링, 플랫폼, 네트워크 연동
- `구파발서버`: 권위 상태, API, DB, 동시성, 보안, 운영
- `구파발게임`: 둘 이상의 역할이 제안과 교차 검토를 거쳐 합의하도록 조정하는 이름
- `$gupabal-game`: Codex Skill 규칙에 맞춘 실제 직접 호출명

## 새 PC에 설치

비공개 AISUPPORT 저장소를 새 PC에서 복제합니다.

Hook 검사 프로그램을 실행하려면 Python 3.10 이상이 필요합니다. 설치 프로그램은 기존 Codex Hook을 지우지 않고 구파발게임 항목만 병합합니다.

Windows PowerShell:

```powershell
git clone https://github.com/LeeSuHeung/AISUPPORT.git
cd AISUPPORT
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

macOS 또는 Linux:

```sh
git clone https://github.com/LeeSuHeung/AISUPPORT.git
cd AISUPPORT
sh ./install.sh
```

설치 프로그램은 기존 관리 파일의 내용이 다르면 안전을 위해 중단합니다. 내용을 확인한 뒤 `-Force` 또는 `--force`를 사용하면 `.backup-날짜` 백업을 만들고 교체합니다. 전역 `AGENTS.md`의 다른 지침과 사용자 Hook은 보존하고, 이 팀의 관리 구역만 추가하거나 갱신합니다.

설치 후 Codex에서 `/hooks`를 열어 새 command Hook의 경로와 내용을 검토한 뒤 신뢰합니다. Codex는 보안을 위해 command Hook의 정확한 버전이 신뢰되기 전에는 실행하지 않습니다. 그다음 새 Codex 작업을 시작합니다. 바로 표시되지 않으면 Codex를 다시 시작합니다.

## 적용된 Hook

- `SubagentStop`: 네 역할의 결과에 작업 범위, 위험, 검증 방법이 빠졌을 때 한 번만 보완을 요청합니다.
- `PreToolUse`: 실제 게임 프로젝트에 `.codex/gupabal/decision.json`이 있고 네 역할의 승인 또는 미결정 정리가 끝나지 않았을 때만 구현용 `apply_patch`를 중단합니다. 합의 파일이 손상됐으면 작업을 강제로 막지는 않지만 먼저 고치도록 경고합니다.
- `PostToolUse`: 합의된 경로의 이번 수정 파일만 대상으로 JSON 문법, 병합 충돌 표식, 선언된 이미지 규격 같은 빠르고 확실한 문제를 알려줍니다.

합의 파일이 없는 프로젝트에서는 `PreToolUse`와 `PostToolUse`가 아무 출력 없이 종료됩니다. 엔진별 빌드나 클라이언트·서버 전체 테스트는 파일을 고칠 때마다 돌리지 않고, 기능 구현이 끝난 뒤 프로젝트의 실제 명령으로 한 번 검증합니다.

다역할 구현을 시작하면 Skill이 합의 파일을 `planning` 상태로 열어 구현을 잠시 잠급니다. 네 역할의 승인이 모두 `AGREE`이고 `agreement.unresolved`가 빈 배열일 때만 `approved`로 바꾸고, 구현과 검증이 끝나면 `enabled: false`로 닫습니다. 작업이 중단돼 잠금이 남았다면 `구파발게임 합의 파일을 확인하고 안전하면 비활성화해줘`라고 요청할 수 있습니다.

Hook은 실수를 일찍 발견하는 보조 안전장치이며 보안 경계는 아닙니다. `PostToolUse` 경고가 나올 때는 변경이 이미 적용된 뒤이므로 다음 작업 전에 내용을 고쳐야 합니다. 설치 갱신은 사용자 Hook을 handler 단위로 보존하고, 검사 프로그램 내용이 바뀌면 새 해시 이름을 사용해 `/hooks`에서 새 버전을 다시 확인할 수 있게 합니다.

## 사용 예시

한 역할만 사용할 때:

```text
구파발기획자에게 현재 프로젝트의 성장 시스템을 검토하게 해줘.
```

네 역할이 함께 대화하게 할 때:

```text
구파발게임으로 현재 프로젝트의 이 기능을 검토해줘.
아직 구현하지 말고 네 역할의 합의안만 보여줘.
```

Skill을 문법적으로 직접 지정하려면 다음처럼 입력합니다.

```text
$gupabal-game을 사용해서 현재 프로젝트의 이 기능을 검토해줘.
```

## 설정 갱신

원본은 `.agents/skills/gupabal-game`, `.codex/agents`, `.codex/hooks`에서 관리합니다. 한 PC에서 수정해 Git에 올린 뒤, 다른 PC에서 `git pull`하고 통합 설치 스크립트를 다시 실행하면 갱신됩니다.
