#!/usr/bin/env python3
"""Deterministic, opt-in lifecycle checks for the Gupabal game team."""

from __future__ import annotations

import fnmatch
import json
import re
import struct
import sys
import time
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DECISION_PARTS = (".codex", "gupabal", "decision.json")
REQUIRED_APPROVALS = ("planner", "art", "client", "server")
MAX_FILES_PER_CALL = 128
MAX_TEXT_BYTES = 1_048_576
MAX_TOTAL_READ_BYTES = 16_777_216
MAX_PATCH_CHARS = 4_194_304
MAX_EVENT_CHARS = 8_388_608
POST_TIME_BUDGET_SECONDS = 2.0
IMAGE_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
TEXT_EXTENSIONS = {
    ".asmdef",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".gd",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".kt",
    ".lua",
    ".md",
    ".php",
    ".properties",
    ".py",
    ".rs",
    ".shader",
    ".sh",
    ".sql",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".uxml",
    ".uss",
    ".xml",
    ".yaml",
    ".yml",
}
ROLE_ALIASES = {
    "planner": ("gupabal_planner", "구파발기획자"),
    "art": ("gupabal_art_designer", "구파발아트디자이너"),
    "client": ("gupabal_client", "구파발클라이언트"),
    "server": ("gupabal_server", "구파발서버"),
}


def emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")


def additional_context(message: str) -> dict[str, Any]:
    return {
        "systemMessage": "구파발게임 Hook이 확인할 항목을 발견했습니다.",
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": message,
        },
    }


def post_context(message: str) -> dict[str, Any]:
    return {
        "systemMessage": "구파발게임 경량 검사에서 확인할 항목을 발견했습니다.",
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        },
    }


def deny_pre_tool(message: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": message,
        }
    }


def find_decision_file(cwd: str) -> tuple[Path, Path] | None:
    try:
        current = Path(cwd).expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        return None
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        decision = candidate.joinpath(*DECISION_PARTS)
        if decision.is_file():
            return candidate, decision
        if (candidate / ".git").exists():
            break
    return None


def find_repository_root(cwd: str) -> Path | None:
    try:
        current = Path(cwd).expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        return None
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


def load_policy(cwd: str) -> tuple[Path | None, Path | None, dict[str, Any] | None, str | None]:
    located = find_decision_file(cwd)
    if located is None:
        return None, None, None, None
    root, decision_path = located
    try:
        if decision_path.stat().st_size > MAX_TEXT_BYTES:
            return root, decision_path, None, "decision.json이 1MB를 초과해 검사를 건너뜁니다."
        policy = json.loads(decision_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return root, decision_path, None, "decision.json을 읽거나 해석할 수 없어 이번 검사는 통과시킵니다."
    if not isinstance(policy, dict):
        return root, decision_path, None, "decision.json의 최상위 값이 객체가 아니어서 이번 검사는 통과시킵니다."
    if policy.get("schema_version") != SCHEMA_VERSION:
        return root, decision_path, None, "지원하지 않는 decision.json 버전이어서 이번 검사는 통과시킵니다."
    if policy.get("enabled") is not True:
        return root, decision_path, None, None
    return root, decision_path, policy, None


def extract_patch_paths(tool_input: Any) -> list[str]:
    if not isinstance(tool_input, dict):
        return []
    command = tool_input.get("command")
    if not isinstance(command, str) or len(command) > MAX_PATCH_CHARS:
        return []
    patterns = (
        r"^\*\*\* (?:Add|Update|Delete) File:\s*(.+?)\s*$",
        r"^\*\*\* Move to:\s*(.+?)\s*$",
    )
    found: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, command, flags=re.MULTILINE):
            value = match.group(1).strip().strip('"\'')
            if value and value not in found:
                found.append(value)
    return found


def normalize_relative(root: Path, raw_path: str) -> tuple[Path | None, str | None]:
    try:
        supplied = Path(raw_path)
        absolute = supplied.resolve(strict=False) if supplied.is_absolute() else (root / supplied).resolve(strict=False)
        relative = absolute.relative_to(root.resolve(strict=False))
    except (OSError, RuntimeError, ValueError):
        return None, None
    return absolute, relative.as_posix()


def normalize_pattern(pattern: Any) -> str | None:
    if not isinstance(pattern, str):
        return None
    normalized = pattern.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        return None
    return normalized or None


def glob_matches(relative_path: str, pattern: Any) -> bool:
    normalized = normalize_pattern(pattern)
    if normalized is None:
        return False
    expression: list[str] = ["^"]
    index = 0
    while index < len(normalized):
        if normalized.startswith("**/", index):
            expression.append("(?:.*/)?")
            index += 3
        elif normalized.startswith("**", index):
            expression.append(".*")
            index += 2
        elif normalized[index] == "*":
            expression.append("[^/]*")
            index += 1
        elif normalized[index] == "?":
            expression.append("[^/]")
            index += 1
        else:
            expression.append(re.escape(normalized[index]))
            index += 1
    expression.append("$")
    return re.match("".join(expression), relative_path) is not None


def list_patterns(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [pattern for item in value if (pattern := normalize_pattern(item)) is not None]


def ownership_entries(policy: dict[str, Any]) -> list[tuple[str, str]]:
    ownership = policy.get("ownership")
    if not isinstance(ownership, dict):
        return []
    entries: list[tuple[str, str]] = []
    for role in ("art", "client", "server"):
        for pattern in list_patterns(ownership.get(role)):
            entries.append((pattern, role))
    shared = ownership.get("shared")
    if isinstance(shared, list):
        for item in shared:
            if not isinstance(item, dict):
                continue
            pattern = normalize_pattern(item.get("glob"))
            owner = item.get("owner")
            normalized_owner = owner.strip().lower() if isinstance(owner, str) else None
            if pattern is not None and normalized_owner in {"art", "client", "server"}:
                entries.append((pattern, normalized_owner))
    return entries


def owners_for(relative_path: str, policy: dict[str, Any]) -> set[str]:
    return {owner for pattern, owner in ownership_entries(policy) if glob_matches(relative_path, pattern)}


def check_domains_for(relative_path: str, policy: dict[str, Any]) -> set[str]:
    domains = owners_for(relative_path, policy)
    checks = policy.get("checks")
    if isinstance(checks, dict):
        for role in ("art", "client", "server"):
            section = checks.get(role)
            if isinstance(section, dict) and any(glob_matches(relative_path, pattern) for pattern in list_patterns(section.get("roots"))):
                domains.add(role)
    return domains


def excluded(relative_path: str, policy: dict[str, Any]) -> bool:
    checks = policy.get("checks")
    if not isinstance(checks, dict):
        return False
    return any(glob_matches(relative_path, pattern) for pattern in list_patterns(checks.get("exclude")))


def agreement_ready(policy: dict[str, Any]) -> tuple[bool, list[str]]:
    agreement = policy.get("agreement")
    if not isinstance(agreement, dict) or agreement.get("status") != "approved":
        return False, list(REQUIRED_APPROVALS)
    approvals = agreement.get("approvals")
    if not isinstance(approvals, dict):
        return False, list(REQUIRED_APPROVALS)
    missing = [role for role in REQUIRED_APPROVALS if str(approvals.get(role, "")).upper() != "AGREE"]
    unresolved = agreement.get("unresolved")
    if not isinstance(unresolved, list):
        missing.append("unresolved 형식")
    elif unresolved:
        missing.append(f"미결정 {len(unresolved)}건")
    return not missing, missing


def role_from_agent_type(agent_type: Any) -> str | None:
    if not isinstance(agent_type, str):
        return None
    lowered = agent_type.lower()
    for role, aliases in ROLE_ALIASES.items():
        if any(alias.lower() in lowered for alias in aliases):
            return role
    return None


def validate_subagent_stop(event: dict[str, Any]) -> dict[str, Any] | None:
    role = role_from_agent_type(event.get("agent_type"))
    if role is None or event.get("stop_hook_active") is True:
        return None
    message = event.get("last_assistant_message")
    if not isinstance(message, str):
        message = ""
    block_match = re.search(r"(?ms)^GUPABAL_RESULT\s*$\s*(.*?)^END_GUPABAL_RESULT\s*\Z", message)
    fields: dict[str, str] = {}
    if block_match:
        for line in block_match.group(1).splitlines():
            key, separator, value = line.partition(":")
            if separator:
                fields[key.strip().lower()] = value.strip()
    required = ("scope", "risks", "verification")
    missing = [key for key in required if not fields.get(key)]
    if not missing:
        return None
    return {
        "decision": "block",
        "reason": (
            f"구파발게임 역할 결과 표식이 불완전합니다. 누락: {', '.join(missing)}. "
            "마지막 답변 끝에 GUPABAL_RESULT, scope:, risks:, verification:, "
            "END_GUPABAL_RESULT를 실제 내용과 함께 한 번만 보완하세요."
        ),
    }


def validate_pre_tool(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("tool_name") != "apply_patch":
        return None
    tool_input = event.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    oversized = isinstance(command, str) and len(command) > MAX_PATCH_CHARS
    root, decision_path, policy, policy_error = load_policy(str(event.get("cwd", "")))
    if policy_error:
        return additional_context(
            f"구파발게임 합의 파일을 적용하지 못했습니다: {policy_error} "
            "decision.json을 고친 뒤 작업을 계속하세요. 이번 변경은 차단하지 않습니다."
        )
    raw_paths = extract_patch_paths(tool_input)

    if root is None or decision_path is None or policy is None:
        repository_root = find_repository_root(str(event.get("cwd", "")))
        if repository_root is None:
            return None
        normalized = [normalize_relative(repository_root, raw_path) for raw_path in raw_paths]
        relative_paths = [relative for _, relative in normalized if relative is not None]
        decision_relative = "/".join(DECISION_PARTS)
        if oversized and isinstance(command, str) and re.search(
            r"^\*\*\* (?:Add|Update) File:\s*(?:\./)?\.codex[\\/]gupabal[\\/]decision\.json\s*$",
            command,
            flags=re.MULTILINE,
        ):
            return deny_pre_tool(
                "구파발게임 합의 파일을 포함한 4MB 초과 패치는 안전하게 분리 여부를 검사할 수 없습니다. "
                "decision.json만 작은 패치로 먼저 생성하거나 수정하세요."
            )
        if decision_relative in relative_paths and len(relative_paths) > 1:
            return deny_pre_tool(
                "구파발게임 합의 파일은 구현 파일과 분리해 먼저 생성해야 합니다. "
                "decision.json만 포함한 패치로 다시 실행하세요."
            )
        return None

    if oversized:
        return deny_pre_tool(
            "구파발게임 합의가 활성화된 상태에서 4MB가 넘는 패치는 안전하게 검사할 수 없습니다. "
            "변경을 작은 패치로 나눠 다시 실행하세요."
        )
    if not raw_paths:
        return None
    normalized: list[tuple[Path, str]] = []
    for raw_path in raw_paths:
        absolute, relative = normalize_relative(root, raw_path)
        if absolute is None or relative is None:
            return deny_pre_tool(f"구파발게임 합의 범위 밖 경로를 수정하려 해 중단했습니다: {raw_path}")
        normalized.append((absolute, relative))

    decision_relative = decision_path.relative_to(root).as_posix()
    implementation_paths = [relative for _, relative in normalized if relative != decision_relative]
    if len(implementation_paths) != len(normalized):
        if implementation_paths:
            return deny_pre_tool(
                "구파발게임 합의 파일과 구현 파일은 같은 패치에서 수정할 수 없습니다. "
                "decision.json 변경을 별도 패치로 실행하세요."
            )
    if not implementation_paths:
        return None

    ready, missing = agreement_ready(policy)
    if not ready:
        planning_allow = list_patterns(policy.get("planning_allow"))
        blocked_paths = [
            path
            for path in implementation_paths
            if not any(glob_matches(path, pattern) for pattern in planning_allow)
        ]
        if not blocked_paths:
            return None
        detail = ", ".join(missing) if missing else "합의 상태"
        return deny_pre_tool(
            "구파발게임 합의가 승인되기 전이라 구현 파일 수정을 중단했습니다. "
            f"decision.json에서 확인할 항목: {detail}."
        )

    entries = ownership_entries(policy)
    if not entries:
        return None
    outside = [path for path in implementation_paths if not owners_for(path, policy)]
    ambiguous = [path for path in implementation_paths if len(owners_for(path, policy)) > 1]
    ownership_findings: list[str] = []
    if outside:
        preview = ", ".join(outside[:10])
        suffix = f" 외 {len(outside) - 10}개" if len(outside) > 10 else ""
        ownership_findings.append(f"소유 경로에 포함되지 않은 파일: {preview}{suffix}")
    if ambiguous:
        preview = ", ".join(ambiguous[:10])
        suffix = f" 외 {len(ambiguous) - 10}개" if len(ambiguous) > 10 else ""
        ownership_findings.append(f"담당자가 둘 이상인 파일: {preview}{suffix}")
    if ownership_findings:
        return additional_context(
            "구파발게임 파일 담당 범위를 확인하세요. " + "; ".join(ownership_findings) + ". "
            "현재 역할을 Hook 입력으로 확정할 수 없어 차단하지 않았습니다. "
            "조정자가 소유자를 확인하거나 decision.json을 갱신하세요."
        )
    return None


def read_image_info(path: Path) -> tuple[int | None, int | None, str | None]:
    extension = path.suffix.lower()
    try:
        with path.open("rb") as image_file:
            header = image_file.read(65_536)
    except OSError:
        return None, None, "파일을 읽을 수 없습니다"
    if extension == ".png":
        if (
            len(header) < 33
            or header[:8] != b"\x89PNG\r\n\x1a\n"
            or header[8:12] != b"\x00\x00\x00\x0d"
            or header[12:16] != b"IHDR"
        ):
            return None, None, "PNG 헤더가 올바르지 않습니다"
        width, height = struct.unpack(">II", header[16:24])
        return width, height, None if width > 0 and height > 0 else "PNG 크기가 0입니다"
    if extension in {".jpg", ".jpeg"}:
        if len(header) < 4 or header[:2] != b"\xff\xd8":
            return None, None, "JPEG 헤더가 올바르지 않습니다"
        index = 2
        while index + 9 < len(header):
            if header[index] != 0xFF:
                index += 1
                continue
            marker = header[index + 1]
            index += 2
            if marker in {0xD8, 0xD9}:
                continue
            if index + 2 > len(header):
                break
            segment_length = int.from_bytes(header[index:index + 2], "big")
            if segment_length < 2 or index + segment_length > len(header):
                break
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                height = int.from_bytes(header[index + 3:index + 5], "big")
                width = int.from_bytes(header[index + 5:index + 7], "big")
                return width, height, None if width > 0 and height > 0 else "JPEG 크기가 0입니다"
            index += segment_length
        return None, None, None
    if extension == ".gif":
        if len(header) < 10 or header[:6] not in {b"GIF87a", b"GIF89a"}:
            return None, None, "GIF 헤더가 올바르지 않습니다"
        width, height = struct.unpack("<HH", header[6:10])
        return width, height, None if width > 0 and height > 0 else "GIF 크기가 0입니다"
    if extension == ".webp":
        if len(header) < 20 or header[:4] != b"RIFF" or header[8:12] != b"WEBP":
            return None, None, "WebP 헤더가 올바르지 않습니다"
        declared_size = int.from_bytes(header[4:8], "little") + 8
        try:
            actual_size = path.stat().st_size
        except OSError:
            return None, None, "WebP 파일 크기를 읽을 수 없습니다"
        if declared_size != actual_size:
            return None, None, "WebP RIFF 크기가 실제 파일과 다릅니다"
        chunk = header[12:16]
        chunk_size = int.from_bytes(header[16:20], "little")
        chunk_end = 20 + chunk_size + (chunk_size % 2)
        if chunk_end > actual_size:
            return None, None, "WebP 청크 크기가 파일 경계를 벗어납니다"
        if chunk == b"VP8X":
            if chunk_size != 10 or len(header) < 30 or actual_size <= chunk_end:
                return None, None, "WebP VP8X 헤더가 불완전합니다"
            width = 1 + int.from_bytes(header[24:27], "little")
            height = 1 + int.from_bytes(header[27:30], "little")
            return width, height, None
        if chunk == b"VP8L":
            if chunk_size < 5 or len(header) < 25 or header[20] != 0x2F:
                return None, None, "WebP VP8L 헤더가 불완전합니다"
            bits = int.from_bytes(header[21:25], "little")
            width = 1 + (bits & 0x3FFF)
            height = 1 + ((bits >> 14) & 0x3FFF)
            return width, height, None
        if chunk == b"VP8 ":
            if chunk_size < 10 or len(header) < 30 or header[23:26] != b"\x9d\x01\x2a":
                return None, None, "WebP VP8 헤더가 불완전합니다"
            width = int.from_bytes(header[26:28], "little") & 0x3FFF
            height = int.from_bytes(header[28:30], "little") & 0x3FFF
            return width, height, None if width > 0 and height > 0 else "WebP 크기가 0입니다"
        return None, None, "지원하지 않는 WebP 청크입니다"
    if extension == ".svg":
        try:
            if path.stat().st_size > MAX_TEXT_BYTES:
                return None, None, "SVG가 1MB를 초과해 안전하게 해석할 수 없습니다"
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            return None, None, "SVG가 UTF-8 텍스트가 아닙니다"
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            return None, None, "SVG의 DTD 또는 ENTITY 선언은 허용되지 않습니다"
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError:
            return None, None, "SVG XML 문법이 올바르지 않습니다"
        if root.tag.rsplit("}", 1)[-1].lower() != "svg":
            return None, None, "SVG 루트 요소를 찾을 수 없습니다"

        def pixel_dimension(value: str | None) -> int | None:
            if value is None:
                return None
            match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:px)?\s*", value, flags=re.IGNORECASE)
            if match is None:
                return None
            number = float(match.group(1))
            return int(number) if number.is_integer() and number > 0 else None

        return pixel_dimension(root.get("width")), pixel_dimension(root.get("height")), None
    return None, None, None


def asset_rule_for(relative_path: str, section: dict[str, Any]) -> dict[str, Any] | None:
    assets = section.get("assets")
    if not isinstance(assets, list):
        return None
    for item in assets:
        if isinstance(item, dict) and normalize_pattern(item.get("path")) == relative_path:
            return item
    return None


def inspect_file(path: Path, relative_path: str, domains: set[str], policy: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    try:
        size = path.stat().st_size
    except OSError:
        return [f"{relative_path}: 수정된 파일을 읽을 수 없습니다"]

    suffix = path.suffix.lower()
    if suffix == ".json" and size > MAX_TEXT_BYTES:
        findings.append(f"{relative_path}: JSON이 1MB를 초과해 완료 검증으로 넘겼습니다")
    if suffix in TEXT_EXTENSIONS and size <= MAX_TEXT_BYTES:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            findings.append(f"{relative_path}: UTF-8 텍스트로 읽을 수 없습니다")
        else:
            if all(marker in text for marker in ("<<<<<<<", "=======", ">>>>>>>")):
                findings.append(f"{relative_path}: 병합 충돌 표식이 남아 있습니다")
            if suffix == ".json":
                try:
                    json.loads(text)
                except json.JSONDecodeError as error:
                    findings.append(f"{relative_path}: JSON 문법 오류({error.lineno}행 {error.colno}열)")

    checks = policy.get("checks")
    checks = checks if isinstance(checks, dict) else {}
    for domain in domains:
        section = checks.get(domain)
        if not isinstance(section, dict):
            continue
        maximum = section.get("max_file_bytes")
        if type(maximum) is int and maximum > 0 and size > maximum:
            findings.append(f"{relative_path}: {domain} 파일 제한 {maximum}바이트를 초과했습니다({size}바이트)")

    if "art" in domains:
        art_section = checks.get("art")
        if isinstance(art_section, dict):
            naming_glob = normalize_pattern(art_section.get("naming_glob"))
            if naming_glob and not fnmatch.fnmatchcase(path.name, naming_glob):
                findings.append(f"{relative_path}: 아트 파일 이름 규칙과 맞지 않습니다")
            rule = asset_rule_for(relative_path, art_section)
            if rule:
                expected_width = rule.get("width")
                expected_height = rule.get("height")
                expected_maximum = rule.get("max_bytes")
                if type(expected_maximum) is int and expected_maximum > 0 and size > expected_maximum:
                    findings.append(f"{relative_path}: 에셋 제한 {expected_maximum}바이트를 초과했습니다")
            else:
                expected_width = None
                expected_height = None

            if suffix in IMAGE_EXTENSIONS:
                width, height, image_error = read_image_info(path)
                if image_error:
                    findings.append(f"{relative_path}: {image_error}")
                if image_error is None and type(expected_width) is int:
                    if width is None:
                        findings.append(f"{relative_path}: 선언된 너비 {expected_width}px를 검증할 수 없습니다")
                    elif width != expected_width:
                        findings.append(f"{relative_path}: 너비 {width}px, 합의값 {expected_width}px")
                if image_error is None and type(expected_height) is int:
                    if height is None:
                        findings.append(f"{relative_path}: 선언된 높이 {expected_height}px를 검증할 수 없습니다")
                    elif height != expected_height:
                        findings.append(f"{relative_path}: 높이 {height}px, 합의값 {expected_height}px")
            elif type(expected_width) is int or type(expected_height) is int:
                findings.append(f"{relative_path}: 이 포맷의 선언된 이미지 크기를 검증할 수 없습니다")
    return findings


def validate_post_tool(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("tool_name") != "apply_patch":
        return None
    root, decision_path, policy, policy_error = load_policy(str(event.get("cwd", "")))
    if policy_error:
        return None
    if root is None or decision_path is None or policy is None:
        return None

    raw_paths = extract_patch_paths(event.get("tool_input"))
    if not raw_paths:
        return None
    findings: list[str] = []
    decision_relative = decision_path.relative_to(root).as_posix()
    inspected = 0
    read_budget = 0
    started = time.monotonic()
    for raw_path in raw_paths:
        if inspected >= MAX_FILES_PER_CALL:
            findings.append(f"검사 파일이 {MAX_FILES_PER_CALL}개를 넘어 나머지는 완료 검증으로 넘겼습니다")
            break
        absolute, relative = normalize_relative(root, raw_path)
        if absolute is None or relative is None or relative == decision_relative:
            continue
        if excluded(relative, policy):
            continue
        domains = check_domains_for(relative, policy).intersection({"art", "client", "server"})
        if not domains:
            continue
        if not absolute.is_file():
            checks = policy.get("checks")
            art_section = checks.get("art") if isinstance(checks, dict) else None
            if "art" in domains and isinstance(art_section, dict) and asset_rule_for(relative, art_section):
                findings.append(f"{relative}: 합의에 선언된 아트 에셋 파일이 없습니다")
            continue
        try:
            size = absolute.stat().st_size
        except OSError:
            continue
        estimated_read = 0
        if absolute.suffix.lower() in TEXT_EXTENSIONS and size <= MAX_TEXT_BYTES:
            estimated_read += size
        if absolute.suffix.lower() in IMAGE_EXTENSIONS:
            estimated_read += min(size, MAX_TEXT_BYTES if absolute.suffix.lower() == ".svg" else 65_536)
        if read_budget + estimated_read > MAX_TOTAL_READ_BYTES or time.monotonic() - started > POST_TIME_BUDGET_SECONDS:
            findings.append("경량 검사 한도에 도달해 나머지는 완료 검증으로 넘겼습니다")
            break
        findings.extend(inspect_file(absolute, relative, domains, policy))
        read_budget += estimated_read
        inspected += 1
    if not findings:
        return None
    shown = findings[:10]
    if len(findings) > 10:
        shown.append(f"그 밖의 항목 {len(findings) - 10}개")
    return post_context(
        "구파발게임 PostToolUse 경량 검사 결과입니다. 변경은 이미 적용되었으므로 다음 작업 전에 확인하세요:\n- "
        + "\n- ".join(shown)
    )


def main() -> int:
    event_hint = sys.argv[1] if len(sys.argv) > 1 else None
    raw_input = sys.stdin.read(MAX_EVENT_CHARS + 1)
    if len(raw_input) > MAX_EVENT_CHARS:
        if event_hint == "PreToolUse":
            emit(
                deny_pre_tool(
                    "구파발게임 Hook 입력이 8MB를 넘어 안전하게 검사할 수 없습니다. "
                    "변경을 작은 패치로 나눠 다시 실행하세요."
                )
            )
        return 0
    try:
        event = json.loads(raw_input)
    except (UnicodeError, json.JSONDecodeError):
        return 0
    if not isinstance(event, dict):
        return 0
    try:
        event_name = event.get("hook_event_name") or event_hint
        result: dict[str, Any] | None = None
        if event_name == "SubagentStop":
            result = validate_subagent_stop(event)
        elif event_name == "PreToolUse":
            result = validate_pre_tool(event)
        elif event_name == "PostToolUse":
            result = validate_post_tool(event)
        if result is not None:
            emit(result)
    except Exception:
        # Hooks are guardrails, not an enforcement boundary. Unexpected input fails open.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
