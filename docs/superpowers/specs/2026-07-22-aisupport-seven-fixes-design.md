# AISUPPORT 1~7 개선 설계

## 배경

AISUPPORT의 구파발게임 Skill, 전역 에이전트, 설치기, lifecycle Hook을 다른 Windows PC와 여러 프로젝트에서도 같은 방식으로 사용할 수 있어야 한다. 현재 감사에서 Windows 인코딩·경로 인용, `CODEX_HOME` 해석, 저장소별 합의 정책, 승인 무결성, 완료 에셋 검증의 일곱 결함이 확인됐다.

이번 작업은 실제 AISUPPORT 파일만 수정한다. 게임 기능, 엔진별 규칙, 아트 에셋, 목업은 만들지 않는다.

## 확정 설계

### 1. 통합 설치기의 Python UTF-8 모드

`scripts/install-aisupport.mjs`가 Python 버전을 찾을 때의 동작은 유지한다. Gupabal 설치기를 실행할 때에는 운영체제와 무관하게 선택된 Python prefix 뒤에 `-X utf8`을 추가한다. Windows `py` 호출은 `py -3 -X utf8 ...`이 된다.

`PYTHONUTF8=0`과 한글·공백·이모지가 포함된 임시 경로를 사용해 통합 dry-run, 설치, verify가 모두 성공하는지 검사한다.

### 2. 경로 정규화와 `CODEX_HOME`

최상위 통합 설치기가 `--target`과 `--agents-file`을 한 번 해석해 두 하위 설치기에 동일한 절대 경로를 전달한다.

우선순위는 다음과 같다.

1. 명시적 `--agents-file`
2. 비어 있지 않은 `CODEX_HOME`
3. `<사용자 홈>/.codex/AGENTS.md`

Skill 대상은 명시적 `--target`, 미지정 시 `<사용자 홈>/.agents/skills` 순서다. `~`, `~/`, `~\`만 사용자 홈으로 확장한다. `~other`는 오설치를 막기 위해 거부한다. 상대 경로는 설치 시작 작업 폴더 기준 절대 경로로 바꾸며, symlink/junction 안전 검사를 보존하도록 `realpath`로 미리 해석하지 않는다.

개별 Node 설치기도 직접 실행될 수 있으므로 같은 `~` 규칙을 적용한다. `gupabal-game`의 fallback agent 경로는 `$CODEX_HOME/agents/gupabal_*.toml`, 환경변수가 없으면 `~/.codex/agents`다. 과거 오설치된 문자 그대로의 `~` 폴더는 자동 삭제하지 않는다.

### 3. Windows Hook 명령 인용

공식 `openai/codex` Hook runner는 Windows 기본 실행기로 `cmd.exe /C`를 사용하고 handler 전체를 하나의 raw argument로 전달한다. 직접 큰따옴표로 감싼 경로는 바깥 `cmd.exe`의 delayed expansion 설정에 따라 `!NAME!`이 확장될 수 있으므로 경로를 handler 평문에 넣지 않는다.

이벤트별 PowerShell 명령문에서 Python 실행 파일, Hook script, 고정 이벤트 인수를 single-quoted literal로 만들고 작은따옴표는 두 번 써서 escape한다. 명령문을 UTF-16LE Base64로 바꿔 `powershell.exe -NoLogo -NoProfile -NonInteractive -EncodedCommand <base64>`로 실행하며 자식 Python의 `$LASTEXITCODE`를 그대로 반환한다. 따라서 공백, `&`, 괄호, `!`, `%`, 작은따옴표, 한글, 이모지가 command line parser에 노출되지 않는다. 실제 생성 명령을 바깥 `cmd.exe /D /S /V:OFF /C`와 `/V:ON /C` 양쪽에서 실행해 stdin, 이벤트 인수, 종료 코드, 정확히 한 번 실행을 검사한다.

### 4. Git root 정책과 조건부 fail-closed

Hook은 먼저 가장 가까운 `.git` 파일 또는 디렉터리를 찾아 현재 Git root를 확정한다. 정책은 정확히 `<git-root>/.codex/gupabal/decision.json` 하나만 읽고 하위 폴더 decision은 무시한다. Git 저장소가 아니거나 decision이 없거나 정상 schema v2의 exact boolean `enabled: false`이면 조용히 통과한다. 호환성을 위해 schema v1도 exact boolean false일 때만 과거 완료 기록으로 보고 조용히 통과한다. `enabled` 누락·비-boolean과 그 밖의 지원하지 않는 schema는 오류다.

root decision이 존재하지만 JSON 오류, 1 MiB 초과, symlink, 지원하지 않는 schema이면 구현 patch를 거부한다. 일반 decision 파일은 4 MiB 이하의 `Add File` 또는 `Update File`이 정확히 decision 하나만 대상으로 할 때만 복구를 허용한다. decision 자체가 symlink이면 정확한 `Delete File` 하나만 허용한다. Move와 구현 파일 혼합은 거부한다. malformed Hook event처럼 활성 정책을 확정할 수 없는 입력과 예상 밖 내부 예외는 구조화된 짧은 경고 후 fail-open을 유지한다.

### 5. 승인 경로의 정확히 한 owner

`agreement.status: approved`에서 모든 구현 경로는 ownership glob을 기준으로 고유 owner 집합 크기가 정확히 1이어야 한다. 0명 또는 서로 다른 2명 이상이면 전체 patch를 거부한다. 같은 owner의 여러 glob이 겹치는 것은 한 명으로 계산한다. `checks.*.roots`는 검사 범위이며 ownership으로 계산하지 않는다. decision-only 복구와 planning 단계의 `planning_allow`는 기존 예외를 유지한다.

### 6. decision schema v2와 승인 digest

v2 agreement는 `revision`, 비어 있지 않은 `summary`, 하나 이상의 비어 있지 않은 `invariants`, 선택적 `spec_refs`, `contract_digest`, 역할별 승인 객체, `unresolved`를 가진다. 승인 객체는 `status`, `revision`, `contract_digest`를 기록한다.

Digest payload에는 다음을 포함한다.

- `schema_version`
- `feature`
- `agreement.revision`
- `agreement.summary`
- `agreement.invariants`
- path로 정렬한 `agreement.spec_refs`
- `ownership`
- `checks`

`enabled`, agreement status, unresolved, contract digest, approvals는 제외한다. Python `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)` 결과를 UTF-8로 인코딩해 lowercase SHA-256을 계산한다.

각 spec ref는 저장소 상대 `path`, `owner`, 양의 정수 `schema_version`, lowercase SHA-256을 가진다. spec은 UTF-8 텍스트로 읽고 BOM을 제거한 뒤 CRLF와 CR을 LF로 정규화해 hash한다. 중복·대소문자 충돌·glob·절대경로·`.`·`..`·조상 symlink/junction·저장소 탈출을 거부하고, owner는 해당 파일의 유일한 ownership owner와 같아야 한다. spec 하나는 최대 1 MiB, 전체는 최대 16 MiB만 읽는다.

approved 조건은 네 역할 모두 `AGREE`, 현재 revision과 digest 일치, unresolved 빈 배열, spec hash 일치다. 계약·ownership·checks가 바뀌면 revision을 올리고 승인을 PENDING으로 되돌려야 한다.

v2 decision, agreement, approval, spec ref는 허용 필드 목록을 엄격히 적용한다. 중복 JSON key와 `NaN`·`Infinity`, 정수 자리에 들어온 boolean, 빈 문자열 계약, digest payload의 실수형 숫자는 거부한다. 승인된 `spec_refs.path`는 현재 revision에서 직접 Add·Update·Delete·Move할 수 없다. 먼저 decision-only patch로 planning 상태와 새 revision을 만들고, spec 수정·새 hash·새 digest 계산 뒤 네 역할이 다시 승인해야 한다.

완료할 때는 `enabled: false`, `agreement.status: completed`와 함께 `contract_digest`를 `null`로 만들고 네 역할의 active approval을 `PENDING`·digest `null`로 초기화한다. 재개하려면 revision을 올리고 새 digest에 대해 네 역할이 다시 승인해야 하므로 완료 시점의 승인을 상태 변경만으로 재사용할 수 없다.

활성 v1은 구현을 차단하고 decision-only v2 migration만 허용한다. 비활성 v1은 기존 완료 기록으로 보고 조용히 통과한다. v1 승인은 승계하지 않고 자동 migration도 하지 않는다.

### 7. 완료 시 전체 에셋 verifier

기존 Hook script에 읽기 전용 `--verify-project <repo>` CLI를 추가한다. `apply_patch` 입력과 관계없이 `checks.art.roots`에 일치하는 전체 일반 파일과 `checks.art.assets`의 모든 선언 경로를 검사한다.

지원하는 실제 공통 필드는 `roots`, `max_file_bytes`, `naming_glob`, `assets.path`, `width`, `height`, `max_bytes`, `checks.exclude`뿐이다. `logical_id`, fallback, 접근성, atlas, import preset, 메모리, draw call 같은 실제 계약이 없는 필드는 만들지 않는다. PNG, JPEG, GIF, WebP, SVG의 기존 공통 검사 로직을 재사용하고 SVG XML 모듈은 필요할 때만 불러온다. 완료 모드는 PNG chunk/IEND, JPEG SOF·SOS·EOI, GIF image block·trailer, WebP chunk 경계와 visual chunk, SVG XML 루트를 끝까지 확인해 헤더만 남은 잘린 파일을 성공 처리하지 않는다.

종료 코드는 `0=완전 검증 통과`, `1=유효한 정책에서 에셋 finding 발견`, `2=정책·입력·spec 오류 또는 완전 검증 불가`다. 결과는 안정적으로 정렬된 JSON 한 개를 stdout에 출력하며 어떤 파일도 수정하지 않는다. 이 검증은 실제 프로젝트 빌드·클라이언트·서버 테스트를 대체하지 않는다.

### 사용자 안내와 설치된 verifier 진입점

1~7의 구현과 사용자 안내가 어긋나지 않도록 `GUPABAL_GAME.md`, `README.md`, `gupabal-game` Skill을 함께 동기화한다. 정책 전체를 여러 문서에 복제하지 않고 초보자가 행동을 결정하는 데 필요한 핵심 흐름을 설명한 뒤 `decision-policy.md`를 상세 기준으로 연결한다.

`GUPABAL_GAME.md`는 다음 내용을 명시한다.

- `decision.json`은 프로젝트별 합의 파일이고 `contract_digest`는 계약 내용의 SHA-256 지문이며 runtime은 현재 Codex가 실제 사용하는 설치본이라는 뜻이다.
- Hook은 가장 가까운 정확한 Git root의 decision 하나만 사용한다. decision 없음·정상 비활성 v2·비활성 legacy v1은 조용히 통과하지만, 존재하는 decision의 손상·과대·symlink·지원하지 않는 schema·잘못된 `enabled`는 구현 patch를 fail-closed로 차단한다. decision-only 복구와 malformed Hook event·내부 예외의 구조화 경고 fail-open을 구분한다.
- `planning`에서 계약·ownership·checks를 정하고 같은 revision·digest에 네 역할이 승인한 뒤 `approved`가 된다. spec hash, 빈 unresolved, 구현 파일당 정확히 한 owner도 필요하다. 계약 변경은 revision 증가와 네 역할 재승인을 요구한다.
- 정상 완료는 실제 프로젝트 검증과 설치된 verifier exit `0` 뒤 `completed`, `enabled: false`, 빈 unresolved, digest `null`, 네 approval `PENDING`·현재 revision·digest `null`로 닫는다. 의도적인 취소는 새 status를 만들지 않고 `enabled: false`, status `planning`, 현재 revision 유지, digest `null`, 네 approval `PENDING`·현재 revision·digest `null`, unresolved에 짧은 취소 사유 1건으로 닫는다. 취소 뒤 재개할 때는 revision을 올리고 취소 사유를 해소한 새 digest에 네 역할이 재승인한다. 사용자는 JSON을 직접 고치지 않고 facilitator에게 취소 종료를 요청하도록 안내한다.
- verifier는 `checks.art.roots`와 선언 assets를 읽기 전용으로 검사한다. exit `1`과 `2`는 모두 완료를 막고, `checked: 0`은 검사 대상이 없다는 뜻이지 시각 검증 완료가 아니다. 구조 통과는 실제 빌드, 엔진 import, 렌더링, 애니메이션, 색상·폰트·접근성 검사를 대체하지 않는다.
- 소스 저장소 테스트나 `git pull`만으로 runtime은 갱신되지 않는다. canonical AISUPPORT checkout에서 최초 설치와 같은 `CODEX_HOME`, target, agents-file 인수로 설치기 verify를 실행한다. verify 전체 exit가 `0`이고 출력이 `OK .../gupabal_hooks_<sha16>.py`일 때 `OK ` 뒤의 전체 경로를 정확한 versioned script로 사용한다. `MISMATCH`가 있으면 완료하지 않고 설치본을 먼저 동기화한다. 새 Hook hash는 Codex CLI의 `/hooks`에서 검토·신뢰한 뒤 새 작업 또는 재시작으로 반영한다.

Skill의 완료 단계도 존재하지 않는 `<CODEX_HOME>/hooks/gupabal_hooks.py`를 직접 가리키지 않는다. canonical AISUPPORT 설치기의 verify 결과에서 현재 설치·설정된 versioned Hook 경로를 확인하고, verify를 성공시킨 Python 3.10+ 명령으로 그 파일에 `-X utf8 ... --verify-project <정확한 Git root>`를 실행하도록 안내한다. 사용자가 Windows `EncodedCommand`를 직접 해독하게 하지 않으며 새 stable launcher도 추가하지 않는다. `README.md`와 `GUPABAL_GAME.md`의 `/hooks` 표현은 공식 지원 범위인 Codex CLI로 한정한다.

소스 acceptance와 전역 runtime 배포를 별도 결과로 기록한다. 소스 acceptance는 manifest, 전체 테스트, 임시 설치·verify, wrapper dry-run, 문서·Skill 검사로 판단한다. 전역 runtime 배포는 사용자 승인을 받은 설치, 같은 인수의 실제 `-Verify` 또는 `--verify`, 설치된 versioned Hook의 프로젝트 verifier exit `0`이 필요하다. 전역 설정 변경 권한이 없거나 runtime이 `MISMATCH`인 동안에는 소스가 준비됐다고 보고할 수 있지만 decision은 `completed`로 닫지 않는다.

시스템 `quick_validate.py`는 먼저 실행한다. 현재 검증 환경처럼 import 단계에서 PyYAML이 없으면 Skill 실패가 아니라 validator environment `NOT RUN`으로 기록하고 사용자 전역 Python에 의존성을 자동 설치하지 않는다. 대신 같은 frontmatter 규칙의 표준 라이브러리 동등 검사, Node 설치기 검사, Hook·Skill 회귀 테스트를 통과시킨다. 이 대체 증거는 소스 acceptance에는 허용하지만 공식 validator 통과로 표현하지 않는다.

## 파일 소유권

- 구파발클라이언트: `scripts/install-aisupport.mjs`, `scripts/install-caveman.mjs`, `scripts/test-caveman-installer.mjs`, `scripts/merge_gupabal_hooks.py`, `tests/test_gupabal_windows.py`, `README.md`
- 구파발서버: Hook, Hook 테스트, `gupabal-game` Skill·template·policy, `gupabal-manifest.json`, `GUPABAL_GAME.md`, 본 설계와 실행 계획
- 구파발기획자·구파발아트디자이너: 읽기 전용 계약·결과 검토

## 완료 조건

각 번호에서 먼저 실패 테스트를 확인하고 최소 수정 뒤 관련 테스트를 통과시킨다. 1~7 전체가 끝난 뒤 사용자 안내와 Skill의 설치된 verifier 진입점을 실제 runtime 동작과 대조한다. Node, Python, Git Bash, 소스 설치 verify, 설치된 runtime verify, Skill validation, diff 검사와 네 역할의 결합 검토를 실행한다. 설치된 versioned Hook의 프로젝트 verifier exit `0`을 확인한 후에만 decision을 `completed`와 `enabled: false`로 닫는다.
