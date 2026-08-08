# AISUPPORT

Codex에서 여러 PC에 동일한 작업 방식과 에이전트를 설치하기 위한 비공개 구성 저장소입니다. 직접 관리하는 Short, Glif 연결, 검토해 고정한 Superpowers Skill, 구파발게임 팀을 한 번에 설치합니다.

## 포함된 구성

- **Short**: 짧고 명확한 답변, 가장 작은 올바른 구현, RTK식 도구 출력 축소를 합친 상시 Skill
- **Glif**: Codex에서 이미지·영상·오디오를 생성하고 개인 Glif Skill을 사용하는 MCP 연결
- **Superpowers**: 기획, 테스트 주도 개발, 디버깅, 검토 같은 작업 절차
- **구파발게임**: 기획자·아트디자이너·클라이언트·서버 역할의 합의형 게임 개발팀
- **구파발 Hook**: 명시적으로 활성화한 경우 합의 상태, 파일 담당 범위, 변경 파일의 확실한 오류를 자동 확인하는 안전장치
- **텔레그램 완료 알림**: 통합 설치 파일 실행 시 Codex 작업 완료를 개인 텔레그램으로 알리는 기능

자세한 내용은 [SHORT.md](SHORT.md), [GLIF.md](GLIF.md), [SUPERPOWERS.md](SUPERPOWERS.md), [GUPABAL_GAME.md](GUPABAL_GAME.md)에서 확인할 수 있습니다.

## 수동 기본 정책

Short 외에는 별도 요청 없이 Skill, 역할 에이전트, 하위 에이전트, 브랜치·커밋·push·PR, GitHub 검사, lifecycle Hook, 백그라운드 도우미, 예약·반복 작업을 시작하지 않습니다. 브랜치 변경을 요청하지 않으면 현재 브랜치를 유지합니다. 명시적으로 호출한 워크플로는 필요한 집중 테스트를 실행할 수 있습니다. 구현 후 최종 검증은 한 번 실행하고, 변경 없는 전체 테스트를 반복하거나 백그라운드에 예약하지 않습니다.

이 PC의 Codex 사용자 설정은 자동 계속(`goals`), lifecycle Hook(`hooks`), 자동 하위 에이전트(`multi_agent`), 기억 기능(`memories`), 후속 작업 제안(`ambient-suggestions-enabled`)을 꺼 둡니다. 통합 설치 파일은 텔레그램 완료 알림을 `notify`에 연결하지만 아래 기능 값은 임의로 바꾸지 않습니다. 다른 PC에서도 같은 동작이 필요하면 `$CODEX_HOME/config.toml`에 아래 값을 직접 적용하고 Codex를 다시 시작합니다.

```toml
[features]
goals = false
hooks = false
multi_agent = false
memories = false

[desktop]
ambient-suggestions-enabled = false
```

통합 설치는 기존 `notify = [...]` 명령을 보존하면서 텔레그램 알림을 앞에 연결합니다. 상시 정책으로 지정한 Short 외의 플러그인·도구는 설치돼 있어도 사용자가 명시적으로 요청한 경우에만 호출합니다.

## 준비물

- Node.js 18 이상
- Python 3.10 이상
- 비공개 저장소에 접근 가능한 GitHub 계정

설치기는 외부 코드를 내려받아 실행하지 않습니다. 사용자가 설치 명령을 직접 실행하면 저장소에 고정된 파일의 SHA-256을 확인한 뒤 로컬 Codex 설정으로 복사하고, 같은 명령 안에서 설치 결과를 다시 검증합니다.

## 새 PC 설치

Windows:

```powershell
git clone https://github.com/LeeSuHeung/AISUPPORT.git
cd AISUPPORT
.\AISUPPORTinstall.cmd
```

복제한 폴더에서 `AISUPPORTinstall.cmd`를 더블클릭해도 됩니다. 실행 정책 명령을 따로 입력할 필요가 없습니다.

macOS 또는 Linux:

```sh
git clone https://github.com/LeeSuHeung/AISUPPORT.git
cd AISUPPORT
sh ./install.sh
```

통합 설치 파일 한 번으로 Short, Glif, Superpowers, 구파발게임, 텔레그램 완료 알림을 설치합니다. 새 PC에 텔레그램 인증 정보가 없으면 Bot Token 입력과 `/start` 전송을 안내합니다. 기존 인증 정보와 다른 완료 알림 명령은 보존합니다.

설치 전 변경 예정 항목만 확인하려면 `--dry-run` 또는 `-DryRun`, 설치 결과를 다시 검사하려면 `--verify` 또는 `-Verify`를 사용합니다. 두 모드에서는 텔레그램 인증을 요청하지 않습니다. 기존 관리 파일이 수정돼 있으면 기본적으로 중단하며, 내용을 확인한 뒤 `--force` 또는 `-Force`를 사용하면 백업 후 교체합니다.

기존 AISUPPORT 설치를 갱신하면 이전 Caveman·Ponytail Skill은 활성 Skill 폴더에서 제거되고 인접한 `skill-backups` 폴더에 보관됩니다. 기존 항상 실행 블록도 Short 블록으로 자동 이전됩니다.

`-WithHooks` 또는 `--with-hooks`를 직접 선택한 경우에만 Codex CLI의 `/hooks`에서 새 command Hook을 검토하고 신뢰합니다. 새 Skill이나 전역 지침이 보이지 않으면 Codex를 다시 시작합니다.

일반 설치는 `glif` Skill과 Glif MCP 주소를 함께 설치합니다. Codex를 다시 시작한 뒤 **Settings > MCP servers**에서 Glif 계정을 PC마다 한 번 인증해야 합니다. 인증정보는 저장소에 저장되지 않습니다.

## 사용

### 텔레그램 완료 알림

통합 설치에 포함됩니다. 기존 Codex 완료 알림을 보존하며, 대화 내용은 보내지 않고 완료 문구와 프로젝트 이름만 보냅니다. Bot Token을 바꿀 때만 다음 명령으로 다시 설정합니다.

```powershell
py -3 -X utf8 .\.codex\hooks\telegram_notify.py --configure
```

macOS 또는 Linux에서는 `python3 -X utf8 ./.codex/hooks/telegram_notify.py --configure`를 사용합니다. 설정 명령은 토큰을 화면에 표시하지 않으며 `$CODEX_HOME/telegram-notify.json`에 저장합니다. 연결 성공 메시지를 확인한 뒤 Codex를 다시 시작합니다.

### 구파발 Hook 활성화

구파발 command Hook은 기본으로 비활성화됩니다. 일반 설치는 기존 사용자 Hook을 보존하면서 이전에 설치된 구파발 관리 Hook만 제거합니다. Hook을 사용하려면 설치 옵션과 Codex 기능을 모두 명시적으로 켜야 합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\AISUPPORTinstall.ps1 -WithHooks
```

```sh
sh ./install.sh --with-hooks
```

또한 `$CODEX_HOME/config.toml`의 `[features]` 아래에서 `hooks = true`로 바꾼 뒤 Codex를 다시 시작해야 합니다. 사용을 마치면 `hooks = false`로 되돌리고 일반 설치를 다시 실행합니다.

활성화한 Hook은 `SubagentStop`, `PreToolUse`, `PostToolUse` 이벤트마다 자동으로 실행됩니다. `/hooks`에서 경로와 내용을 검토하고 신뢰한 경우에만 활성화하세요.

`short` Skill은 모든 응답과 코딩 작업에 자동으로 적용됩니다. 상시 적용되는 AISUPPORT Skill은 Short뿐입니다. RTK식 출력 축소 규칙도 Short 안에 포함되며 별도 RTK 프로그램이나 Hook은 설치하지 않습니다. 다른 AISUPPORT Skill은 필요한 이름을 직접 말해야 시작됩니다.

```text
short lite로 답변해줘.
normal mode로 전환해줘.
$glif로 이 캐릭터의 게임 아이콘을 한 장 만들어줘.
$using-superpowers를 사용해서 이 작업 절차를 진행해줘.
$verification-before-completion으로 최종 결과만 검증해줘.
```

게임의 여러 분야가 함께 결정해야 할 때는 다음처럼 호출합니다.

```text
구파발게임으로 현재 프로젝트의 이 기능을 검토하고 구현해줘.
```

한 역할만 필요하면 `구파발기획자`, `구파발아트디자이너`, `구파발클라이언트`, 또는 `구파발서버`를 정확히 말해 호출합니다.

Hook은 별도로 호출하지 않습니다. 프로젝트에 구파발 합의 파일이 활성화된 동안 관련 파일 변경 시 자동 실행됩니다.

## 갱신과 검증

GitHub 검사는 자동으로 시작하지 않습니다. `push`나 PR(Pull Request, 변경을 `master`에 합치기 전에 검토하는 요청)만으로는 실행되지 않으며, 필요할 때 다음 명령으로 직접 시작합니다.

```powershell
gh workflow run verify-aisupport.yml --ref master
```

```powershell
git pull
powershell -ExecutionPolicy Bypass -File .\AISUPPORTinstall.ps1 -DryRun
powershell -ExecutionPolicy Bypass -File .\AISUPPORTinstall.ps1
powershell -ExecutionPolicy Bypass -File .\AISUPPORTinstall.ps1 -Verify
```

`git pull`은 이 저장소의 소스 파일만 갱신하며 Codex가 실제 사용하는 설치본(runtime)은 바꾸지 않습니다. 설치 스크립트를 다시 실행한 뒤 `-Verify`(Windows) 또는 `--verify`(macOS/Linux)로 설치 결과를 확인하세요. 검증 모드는 설치 파일이나 Hook 설정을 수정하지 않는 읽기 전용 작업입니다.

소스 Skill은 `.agents/skills`, 역할과 Hook은 `.codex`, 설치기는 `scripts`에서 관리합니다. Short는 `short-manifest.json`, 제3자 Skill은 기존 manifest와 `skills-lock.json`, Glif Skill은 `glif-manifest.json`, 구파발 자체 파일은 `gupabal-manifest.json`으로 무결성을 확인합니다.
