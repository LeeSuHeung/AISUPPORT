# 구파발게임 합의 파일

`<repo>/.codex/gupabal/decision.json`은 현재 다역할 기능의 합의 상태와 파일 담당자를 기록한다. 실제 프로젝트에서 확인한 값만 사용한다.

## 생명주기

1. 구현 요청을 받으면 `enabled: true`, `agreement.status: planning`으로 연다.
2. 네 역할이 합의하면 모든 approval을 `AGREE`, status를 `approved`로 바꾼다.
3. 구현과 검증을 마치면 `enabled: false`, status를 `completed`로 바꾼다.

`planning` 중에는 decision 파일과 `planning_allow`에 명시한 기획 문서만 수정할 수 있다. 중단된 작업을 재개하지 않을 때는 메인 조정자가 `enabled: false`로 닫는다.

## 필드

- `feature`: 사용자가 요청한 실제 기능 이름.
- `planning_allow`: 합의 전에 작성하도록 사용자가 요청한 문서 경로 패턴. 없으면 빈 배열.
- `agreement.approvals`: `planner`, `art`, `client`, `server` 각각 `PENDING`, `AGREE`, `CONFLICT` 중 하나.
- `agreement.unresolved`: 미결정 내용과 담당자. 없으면 반드시 빈 배열. 항목이 하나라도 남아 있으면 네 역할이 모두 `AGREE`여도 구현 승인이 완료되지 않은 것으로 처리한다.
- `ownership.art|client|server`: 각 역할이 수정할 상대경로 glob 목록. glob은 `Client/**`처럼 여러 파일을 나타내는 간단한 패턴이다.
- `ownership.shared`: 공유 파일의 단일 담당자 목록. 항목 형식은 `{"glob": "실제/상대경로", "owner": "client"}`이다.
- `checks.exclude`: 생성물, 외부 라이브러리, 캐시처럼 검사하지 않을 경로.
- `checks.<role>.roots`: 해당 영역으로 분류할 실제 경로. ownership과 같으면 같은 값을 사용한다.
- `max_file_bytes`: 합의된 경우에만 양의 정수로 기록한다.

## 아트 에셋 규격

`checks.art.assets` 항목은 다음 키를 지원한다.

- `path`: 저장소 기준 실제 에셋 상대경로. 필수.
- `width`, `height`: 합의된 픽셀 크기. 선택.
- `max_bytes`: 합의된 최대 파일 크기. 선택.

`checks.art.naming_glob`은 파일 이름에만 적용한다. 실제 규칙이 있을 때 `ui_*.png` 같은 glob을 기록한다. 크기 자동 판정은 PNG, JPEG, GIF, WebP, SVG만 지원한다. 다른 포맷에 `width`나 `height`를 선언하면 검증 불가 경고를 낸다. 이름과 바이트 제한은 포맷과 관계없이 검사한다.

임의 빌드·테스트 명령은 이 파일에 넣지 않는다. 프로젝트의 실제 테스트는 구현 완료 단계에서 Codex가 별도로 실행한다.
