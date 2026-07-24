# AISUPPORT

Codex에서 여러 PC에 동일한 작업 방식과 에이전트를 설치하기 위한 비공개 구성 저장소입니다. 외부에서 검토해 고정한 Caveman·Superpowers Skill과 직접 관리하는 구파발게임 팀을 한 번에 설치합니다.

## 포함된 구성

- **Caveman**: 답변을 짧고 명확하게 정리하는 표현 방식
- **Superpowers**: 기획, 테스트 주도 개발, 디버깅, 검토 같은 작업 절차
- **구파발게임**: 기획자·아트디자이너·클라이언트·서버 역할의 합의형 게임 개발팀
- **구파발 Hook**: 합의 상태, 파일 담당 범위, 변경 파일의 확실한 오류를 자동 확인하는 안전장치

자세한 내용은 [CAVEMAN.md](CAVEMAN.md), [SUPERPOWERS.md](SUPERPOWERS.md), [GUPABAL_GAME.md](GUPABAL_GAME.md)에서 확인할 수 있습니다.

## 준비물

- Node.js 18 이상
- Python 3.10 이상
- 비공개 저장소에 접근 가능한 GitHub 계정

설치기는 외부 코드를 내려받아 실행하지 않습니다. 저장소에 고정된 파일의 SHA-256을 확인한 뒤 로컬 Codex 설정으로 복사하고, 설치 결과를 자동으로 다시 검증합니다.

## 새 PC 설치

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

설치 전 변경 예정 항목만 확인하려면 `--dry-run` 또는 `-DryRun`, 설치 결과를 다시 검사하려면 `--verify` 또는 `-Verify`를 사용합니다. 기존 관리 파일이 수정돼 있으면 기본적으로 중단하며, 내용을 확인한 뒤 `--force` 또는 `-Force`를 사용하면 백업 후 교체합니다.

설치 후 Codex CLI의 `/hooks`에서 새 command Hook을 검토하고 신뢰한 뒤 새 작업을 시작합니다. 새 Skill이나 전역 지침이 보이지 않으면 Codex를 다시 시작합니다.

## 사용

AISUPPORT Skill은 자동으로 시작하지 않습니다. 새 작업에서도 필요한 Skill 이름을 직접 말해야 합니다.

```text
$caveman을 사용해서 답변을 짧게 정리해줘.
$using-superpowers를 사용해서 이 작업 절차를 진행해줘.
```

게임의 여러 분야가 함께 결정해야 할 때는 다음처럼 호출합니다.

```text
구파발게임으로 현재 프로젝트의 이 기능을 검토하고 구현해줘.
```

한 역할만 필요하면 `구파발기획자`, `구파발아트디자이너`, `구파발클라이언트`, 또는 `구파발서버`를 정확히 말해 호출합니다.

Hook은 별도로 호출하지 않습니다. 프로젝트에 구파발 합의 파일이 활성화된 동안 관련 파일 변경 시 자동 실행됩니다.

## 갱신과 검증

```powershell
git pull
powershell -ExecutionPolicy Bypass -File .\install.ps1 -DryRun
powershell -ExecutionPolicy Bypass -File .\install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Verify
```

`git pull`은 이 저장소의 소스 파일만 갱신하며 Codex가 실제 사용하는 설치본(runtime)은 바꾸지 않습니다. 설치 스크립트를 다시 실행한 뒤 `-Verify`(Windows) 또는 `--verify`(macOS/Linux)로 설치 결과를 확인하세요.

소스 Skill은 `.agents/skills`, 역할과 Hook은 `.codex`, 설치기는 `scripts`에서 관리합니다. 제3자 Skill은 기존 manifest와 `skills-lock.json`, 구파발 자체 파일은 `gupabal-manifest.json`으로 무결성을 확인합니다.
