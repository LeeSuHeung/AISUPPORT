# Glif for Codex

AISUPPORT connects Codex to the same Glif MCP media service supported by
Claude. The integration creates and revises images, video, and audio, reads
personal Glif skills, and keeps media in durable Glif projects.

## Install on a new computer

Run the normal AISUPPORT installer:

```powershell
git clone https://github.com/LeeSuHeung/AISUPPORT.git
cd AISUPPORT
powershell -ExecutionPolicy Bypass -File .\AISUPPORTinstall.ps1
```

On macOS or Linux:

```sh
git clone https://github.com/LeeSuHeung/AISUPPORT.git
cd AISUPPORT
sh ./install.sh
```

The installer copies the `glif` skill and safely adds this managed entry to
`$CODEX_HOME/config.toml` without storing credentials:

```toml
[mcp_servers.glif]
url = "https://glif.app/api/mcp"
auth = "oauth"
default_tools_approval_mode = "writes"
```

Restart Codex, open **Settings > MCP servers**, and authenticate Glif once on
each computer. OAuth credentials stay on that computer and must never be
committed to this repository.

## Check the connection

```text
$glif로 whoami만 실행해 연결 상태와 잔액을 확인해줘. 미디어는 생성하지 마.
```

## Create an image

```text
$glif로 새 이미지 프로젝트를 만들어줘.
목적: 캐주얼 매치3 게임 아이콘
대상: 파란색 얼음 보석
스타일: 밝은 3D 카툰
구도: 중앙 정면
배경: 투명
제외: 글자와 잘린 그림자
완료될 때까지 확인하고 결과를 보여줘.
```

## Revise the same project

```text
$glif로 방금 프로젝트를 이어서 수정해줘.
형태와 색은 유지하고 광택만 줄여줘.
```

## Use reference media

Attach an image, video, or audio file, then ask:

```text
$glif로 첨부 파일을 참고 자료로 업로드하고 같은 화풍의 새 게임 아이콘을 만들어줘.
```

## Control credit use

Ask for text-only directions before generation:

```text
$glif로 생성하기 전에 화풍 4개를 글로만 제안해줘. 아직 생성하지 마.
내가 선택하면 한 장만 생성해줘.
```

Glif billing is separate from Codex. Glif is an external service, so review its
privacy terms before uploading confidential assets. The MCP/API is in beta and
may change.
