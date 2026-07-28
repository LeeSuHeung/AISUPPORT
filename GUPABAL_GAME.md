# 구파발게임 Codex 팀

기획자, 아트디자이너, 클라이언트 개발자, 서버 개발자 역할과 안전한 작업 Hook을 여러 PC의 Codex에서 공통으로 사용하기 위한 설정 저장소입니다. 게임 기능이나 프로젝트 코드는 포함하지 않습니다.

## 포함된 역할

- `구파발기획자`: 시스템, 성장, 경제, 수치 밸런스
- `구파발아트디자이너`: 아트 방향, UI 시각 체계, 캐릭터·환경·에셋 규격
- `구파발클라이언트`: 화면, 입력, 렌더링, 플랫폼, 네트워크 연동
- `구파발서버`: 권위 상태, API, DB, 동시성, 보안, 운영
- `구파발게임`: 둘 이상의 역할이 제안과 교차 검토를 거쳐 합의하도록 조정하는 이름
- `$gupabal-game`: Codex Skill 규칙에 맞춘 실제 직접 호출명

## 수동 호출

구파발 Skill과 역할 에이전트는 자동으로 시작하지 않습니다. 새 작업에서도 `구파발게임`,
`$gupabal-game`, 또는 필요한 정확한 역할 이름을 직접 말해야 합니다. 예: `구파발기획자에게
현재 프로젝트의 성장 시스템을 검토하게 해줘.`

## 새 PC에 설치

비공개 AISUPPORT 저장소를 새 PC에서 복제합니다.

통합 설치 프로그램을 실행하려면 Node.js 18 이상과 Python 3.10 이상이 필요합니다. 설치 프로그램은 기존 Codex Hook을 지우지 않고 구파발게임 항목만 병합합니다.

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

설치 후 Codex CLI의 `/hooks`를 열어 새 command Hook의 경로와 내용을 검토한 뒤 신뢰합니다. Codex는 보안을 위해 command Hook의 정확한 버전이 신뢰되기 전에는 실행하지 않습니다. 그다음 새 Codex 작업을 시작합니다. 바로 표시되지 않으면 Codex를 다시 시작합니다.

## 적용된 Hook

구파발 command Hook은 기본으로 비활성화됩니다. 일반 설치는 사용자 Hook을 보존하고 기존 구파발 관리 handler만 제거합니다. Hook을 명시적으로 활성화하려면 Windows에서는 `-WithHooks`, macOS/Linux에서는 `--with-hooks`를 설치 명령에 추가합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -WithHooks
```

```sh
sh ./install.sh --with-hooks
```

활성화한 Hook은 아래 이벤트마다 자동 실행됩니다. `/hooks`에서 command와 버전 경로를 검토하고 신뢰한 뒤에만 사용합니다.

- `SubagentStop`: 네 역할의 결과에 작업 범위, 위험, 검증 방법이 빠졌을 때 한 번만 보완을 요청합니다.
- `PreToolUse`: 활성 합의가 승인됐는지와 수정 파일에 정확히 한 owner(담당 역할)가 있는지 `apply_patch` 전에 확인합니다.
- `PostToolUse`: 합의된 경로의 이번 수정 파일만 대상으로 JSON 문법, 병합 충돌 표식, 선언된 이미지 규격 같은 빠르고 확실한 문제를 알려줍니다.

Hook은 현재 작업 위치에서 위로 올라가 처음 만나는, 즉 가장 가까운 Git 저장소를 정확한 Git 루트로 선택합니다. 그 루트의 `.codex/gupabal/decision.json` 하나만 읽습니다. Git 루트나 합의 파일이 없거나, 아래 완료·취소 규칙을 모두 만족하는 비활성 합의라면 조용히 종료합니다.

decision이 잘못된 JSON이거나 1 MiB를 넘거나, symlink이거나, 지원하지 않는 버전이거나, `enabled` 또는 `schema_version`의 형식이 잘못되면 `PreToolUse`는 fail-closed로 구현 변경을 막습니다. 잘린 비활성 schema v2, 잘못된 완료·취소 상태, 초기화되지 않은 approval도 같은 방식으로 막습니다. 복구할 때만 4 MiB 이하의 작은 `decision-only` 패치 하나를 허용합니다. 일반 파일은 Add 또는 Update만, symlink decision은 Delete만 허용합니다. decision과 구현 파일을 섞거나 Move하거나 4 MiB를 넘기면 막습니다.

이 fail-closed 규칙은 저장소의 decision을 안전하게 해석하지 못한 경우에 적용됩니다. 반대로 Codex가 Hook에 보낸 event 자체가 잘못된 JSON이거나 Hook 내부 예외가 발생하면, Hook은 구조화된 경고를 남기고 fail-open으로 종료합니다. `PreToolUse` event가 8 MiB를 넘어 Git 루트와 정책을 확인할 수 없는 경우도 `systemMessage`와 `hookSpecificOutput.additionalContext`에 경고만 남기고 변경을 차단하지 않습니다. 이 경우 정책 검사가 끝났다고 가정하지 말고 경고 원인을 확인해야 합니다. 정상 event를 해석한 뒤 활성 정책에서 4 MiB를 넘는 patch를 막는 제한은 그대로 적용됩니다.

`PostToolUse` 경고가 나올 때는 변경이 이미 적용된 뒤이므로 다음 작업 전에 내용을 고쳐야 합니다. 엔진별 빌드나 클라이언트·서버 전체 테스트는 파일을 고칠 때마다 돌리지 않고, 기능 구현이 끝난 뒤 프로젝트의 실제 명령으로 검증합니다. Hook은 실수를 일찍 발견하는 보조 안전장치이며 보안 경계는 아닙니다.

## 합의와 파일 담당자

다역할 구현은 `schema v2` decision을 `enabled: true`, `agreement.status: planning`으로 엽니다. 실제 계약의 요약, 불변 규칙, `spec_refs`, 파일 담당자, 검사 규칙을 기록하고 그 내용의 SHA-256 지문인 `contract_digest`를 계산합니다. 각 `spec_refs`에는 실제 계약 문서 경로와 정규화된 문서 hash가 들어갑니다.

네 역할은 같은 revision과 `contract_digest`를 승인해야 합니다. `agreement.unresolved`가 비어 있고 모든 구현 경로에 정확히 한 owner가 있을 때만 `approved`가 됩니다. 계약, 문서, 담당자, 검사 규칙이 바뀌면 revision을 올리고 새 digest로 네 역할의 승인을 다시 받습니다. 자세한 규칙은 [decision-policy.md](.agents/skills/gupabal-game/references/decision-policy.md)에 있습니다.

## source와 runtime 검증

Git에서 받은 AISUPPORT source가 올바르다는 검사와 이 PC의 Codex runtime에 설치된 결과가 올바르다는 검사는 다릅니다. `git pull`만으로 runtime은 갱신되지 않습니다. 설치 후 canonical AISUPPORT 폴더에서, 설치 때 사용한 것과 같은 custom `CODEX_HOME`, `--target`, `--agents-file` 값으로 통합 installer verify를 먼저 실행합니다.

Windows에서는 설치 때와 같은 `CODEX_HOME` 환경을 유지하고 다음 명령을 실행합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Verify -Target '<same-target>' -AgentsFile '<same-agents-file>'
```

macOS 또는 Linux에서는 다음 명령을 실행합니다.

```sh
CODEX_HOME='<same-codex-home>' sh ./install.sh --verify --target '<same-target>' --agents-file '<same-agents-file>'
```

이 통합 명령 전체가 exit `0`이고 출력 어디에도 `MISMATCH`가 없어야 합니다. 그다음 명시적으로 선택한 Python 3.10+ 명령으로 같은 환경에서 다음 명령을 실행합니다.

```text
<python> -X utf8 scripts/install_gupabal.py --target <exact> --agents-file <exact> --verify
```

두 `<exact>`는 각각 최초 설치와 정확히 같은 target과 agents-file 값이며, shell에서 Unicode (공백·한글·이모지 포함) 경로 하나로 안전하게 quote합니다. `PYTHONUTF8=0`이어도 `-X utf8`을 제거하지 않습니다. 이 두 번째 명령도 exit `0`이고 `MISMATCH`가 없어야 하며, 정확히 하나의 `OK <전체경로>/gupabal_hooks_<sha16>.py` 줄이 있어야 합니다. Windows `EncodedCommand`를 수동으로 decode해 Python이나 Hook 경로를 추측하지 않습니다. 그 `OK ` 뒤의 전체 경로와 방금 성공한 같은 Python 명령으로 다음 검사를 실행합니다.

```text
<python> -X utf8 <verified-versioned-hook-path> --verify-project <정확한-Git-루트>
```

프로젝트 verifier의 exit `0`은 통과, exit `1`은 규칙 위반 발견, exit `2`는 정책·입력 오류 또는 완전 검증 불가입니다. 결과의 `checked: 0`은 선언된 아트 대상이 없었다는 뜻일 뿐, 시각 검수·빌드·import·render가 통과했다는 뜻은 아닙니다. 필요한 프로젝트 검증은 따로 실행합니다. source만 준비됐거나 runtime 설치와 검증이 끝나지 않았다면 decision을 완료 처리하지 않습니다.

## 정상 완료와 의도적인 취소

정상 완료는 runtime과 프로젝트 검증까지 통과한 뒤 다음 값으로 닫습니다.

- `enabled: false`
- `agreement.status: completed`
- `agreement.unresolved: []`
- `agreement.contract_digest: null`
- 모든 approval: `status: PENDING`, 현재 revision, `contract_digest: null`

구현하지 않고 끝내는 의도적인 취소는 새 status를 만들지 않고 다음 값으로 닫습니다.

- `enabled: false`
- `agreement.status: planning`
- `agreement.contract_digest: null`
- 모든 approval: `status: PENDING`, 현재 revision, `contract_digest: null`
- `agreement.unresolved`: 짧은 취소 이유 정확히 한 항목

사용자는 JSON을 직접 고치지 말고 `구파발게임 합의 파일을 정상 완료로 닫아줘` 또는 `이 작업을 취소하고 이유를 기록해줘`라고 요청합니다. 다시 열 때는 revision을 올리고, 취소 이유를 제거하거나 해결하고, 새 digest와 네 역할의 승인을 받아야 합니다. 설치된 새 Hook 버전은 Codex CLI의 `/hooks`에서 다시 확인하고 신뢰해야 합니다.

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
