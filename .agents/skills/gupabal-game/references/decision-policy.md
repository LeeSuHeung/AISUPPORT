# 구파발게임 합의 파일

`<repo>/.codex/gupabal/decision.json`은 현재 다역할 기능의 합의 상태와 파일 담당자를 기록한다. 실제 프로젝트에서 확인한 값만 사용한다.

## 생명주기

1. 구현 요청을 받으면 `enabled: true`, `agreement.status: planning`, 양의 정수 `revision`으로 연다.
2. 실제 계약을 `summary`, `invariants`, `spec_refs`, `ownership`, `checks`에 기록하고 `contract_digest`를 계산한다.
3. 네 역할이 같은 revision과 digest를 직접 확인한 뒤 각 approval 객체를 `AGREE`로 바꾸고 status를 `approved`로 바꾼다.
4. 구현과 전체 검증을 마치면 아래의 정상 완료 규칙으로 닫는다. 구현하지 않고 끝내기로 했다면 의도적인 취소 규칙으로 닫는다.

`planning` 중에는 decision 파일과 `planning_allow`에 명시한 기획 문서만 수정할 수 있다. 사용자는 JSON을 직접 편집하지 않고 메인 조정자에게 완료 또는 취소 처리를 요청한다.

## 필드

- `feature`: 사용자가 요청한 실제 기능 이름.
- `planning_allow`: 합의 전에 작성하도록 사용자가 요청한 문서 경로 패턴. 없으면 빈 배열.
- `agreement.revision`: 계약이 바뀔 때마다 올리는 양의 정수. boolean은 정수로 인정하지 않는다.
- `agreement.summary`: 비어 있지 않은 계약 요약.
- `agreement.invariants`: 반드시 지켜야 하는 비어 있지 않은 문자열 목록. 최소 한 항목이 필요하다.
- `agreement.spec_refs`: 상세 계약 문서를 digest에 묶는 선택 목록. 없으면 빈 배열.
- `agreement.contract_digest`: 아래 규칙으로 계산한 lowercase SHA-256.
- `agreement.approvals`: `planner`, `art`, `client`, `server` 각각 `status`, `revision`, `contract_digest`를 가진 객체. status는 `PENDING`, `AGREE`, `CONFLICT` 중 하나다.
- `agreement.unresolved`: 미결정 내용과 담당자. 없으면 반드시 빈 배열. 항목이 하나라도 남아 있으면 네 역할이 모두 `AGREE`여도 구현 승인이 완료되지 않은 것으로 처리한다.
- `ownership.art|client|server`: 각 역할이 수정할 상대경로 glob 목록. 구현 파일마다 서로 다른 소유 역할이 정확히 하나여야 한다.
- `ownership.shared`: 공유 파일의 단일 담당자 목록. 항목 형식은 `{"glob": "실제/상대경로", "owner": "client"}`이다.
- `checks.exclude`: 생성물, 외부 라이브러리, 캐시처럼 검사하지 않을 경로.
- `checks.<role>.roots`: 해당 영역으로 분류할 실제 경로. ownership과 같으면 같은 값을 사용한다.
- `max_file_bytes`: 합의된 경우에만 양의 정수로 기록한다.

## 계약 digest와 승인

digest payload는 `schema_version`, `feature`, `agreement.revision`, `agreement.summary`, `agreement.invariants`, path로 정렬한 `agreement.spec_refs`, `ownership`, `checks`만 포함한다. 다음 Python 규칙과 같은 canonical JSON을 UTF-8로 인코딩하고 SHA-256을 계산한다.

```python
json.dumps(
    payload,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
).encode("utf-8")
```

승인 답변에는 `APPROVAL: AGREE`, `agreement_revision`, 전체 `contract_digest`를 명시한다. 네 approval 모두 현재 revision과 재계산 digest가 일치해야 approved가 된다. 계약·ownership·checks가 바뀌면 revision을 올리고 네 approval을 `PENDING`으로 되돌린 뒤 다시 승인한다. 중복 JSON key, `NaN`·`Infinity`, 허용 목록 밖의 decision·agreement·approval·spec-ref 필드는 거부한다.

## 상세 계약 문서(`spec_refs`)

각 항목은 `path`, `owner`, 양의 정수 `schema_version`, lowercase `sha256`만 가진다. path는 저장소 상대 POSIX 경로이며 절대경로, glob, `.`·`..`, backslash, 중복·대소문자 충돌, symlink·junction을 허용하지 않는다. owner는 해당 파일의 유일한 ownership owner와 같아야 한다.

문서는 UTF-8로 읽고 BOM을 제거한 뒤 CRLF와 CR을 LF로 바꿔 SHA-256을 계산한다. 파일 하나는 1 MiB, 전체는 16 MiB를 넘을 수 없다. approved 상태의 spec 파일은 직접 수정하지 않는다. 먼저 decision-only patch로 planning과 새 revision을 만든 뒤 문서·hash·digest를 갱신하고 재승인한다.

## 아트 에셋 규격

`checks.art.assets` 항목은 다음 키를 지원한다.

- `path`: 저장소 기준 실제 에셋 상대경로. 필수.
- `width`, `height`: 합의된 픽셀 크기. 선택.
- `max_bytes`: 합의된 최대 파일 크기. 선택.

`checks.art.naming_glob`은 파일 이름에만 적용한다. 실제 규칙이 있을 때 `ui_*.png` 같은 glob을 기록한다. 크기 자동 판정은 PNG, JPEG, GIF, WebP, SVG만 지원한다. 다른 포맷에 `width`나 `height`를 선언하면 검증 불가 경고를 낸다. 이름과 바이트 제한은 포맷과 관계없이 검사한다.

임의 빌드·테스트 명령은 이 파일에 넣지 않는다. 프로젝트의 실제 테스트는 구현 완료 단계에서 Codex가 별도로 실행한다.

## 설치된 runtime 검증

AISUPPORT의 source 검증 통과는 현재 PC의 runtime 설치 완료를 뜻하지 않는다. 완료 전에 canonical AISUPPORT checkout에서 설치 때와 같은 custom `CODEX_HOME`, `--target`, `--agents-file` 값으로 통합 installer verify를 먼저 실행한다. Windows 명령은 `powershell -ExecutionPolicy Bypass -File .\install.ps1 -Verify -Target '<same-target>' -AgentsFile '<same-agents-file>'`, macOS·Linux 명령은 `CODEX_HOME='<same-codex-home>' sh ./install.sh --verify --target '<same-target>' --agents-file '<same-agents-file>'`이다. Windows도 설치 때와 같은 `CODEX_HOME` 환경을 유지한다. 이 통합 명령 전체가 exit `0`이고 출력 어디에도 `MISMATCH`가 없어야 한다.

그다음 명시적인 Python 3.10+ 명령으로 같은 환경에서 `<python> -X utf8 scripts/install_gupabal.py --target <exact> --agents-file <exact> --verify`를 실행한다. 두 `<exact>`는 각각 최초 설치와 정확히 같은 target과 agents-file 값을 뜻하며, shell에서 Unicode (공백·한글·이모지 포함) 경로 하나로 안전하게 quote한다. `PYTHONUTF8=0`이어도 `-X utf8`을 제거하지 않는다. 이 두 번째 명령도 exit `0`이고 `MISMATCH`가 없어야 하며, 출력에는 정확히 하나의 `OK <absolute-path>/gupabal_hooks_<sha16>.py` 줄이 있어야 한다.

`OK ` 뒤의 전체 경로를 사용해 같은 Python 명령으로 `<python> -X utf8 <verified-versioned-hook-path> --verify-project <exact-git-root>`를 실행한다. Windows `EncodedCommand`를 수동으로 decode해 Python이나 Hook 경로를 추측하지 않는다. verifier는 `schema_version`, `status`, `checked`, 정렬된 `findings`, 정렬된 `errors`를 한 줄 JSON으로 출력한다. exit `0`은 완전 통과, exit `1`은 검사가 끝났지만 규칙 위반 발견, exit `2`는 정책·입력 오류 또는 완전 검증 불가다. `checked: 0`은 선언된 아트 대상이 없다는 뜻일 뿐 시각 검수, 빌드, import, render 통과를 뜻하지 않는다. 필요한 프로젝트 검증은 별도로 실행한다. source만 준비됐거나 runtime 설치·검증이 끝나지 않았다면 합의 파일을 닫지 않는다.

## 완료와 의도적인 취소

정상 완료는 `enabled: false`, `agreement.status: completed`, `agreement.unresolved: []`, `agreement.contract_digest: null`로 기록한다. agreement 내부 값은 `unresolved: []`, `contract_digest: null`이다. 각 approval은 `status: PENDING`, `revision`은 현재 revision(`current revision`), `contract_digest: null`로 초기화한다.

의도적인 취소는 새 status를 만들지 않는다. `enabled: false`, `agreement.status: planning`, `agreement.contract_digest: null`로 기록하고, 각 approval은 `status: PENDING`, `revision`은 현재 revision(`current revision`), `contract_digest: null`로 초기화한다. `agreement.unresolved`에는 짧은 취소 이유를 정확히 한 항목만 남긴다.

완료나 취소를 다시 열 때는 revision을 올린다. 취소 이유를 제거하거나 해결하고 새 digest를 계산한 뒤 네 역할의 새 승인을 모두 받아야 구현할 수 있다.
