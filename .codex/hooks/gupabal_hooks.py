#!/usr/bin/env python3
"""Deterministic AISUPPORT lifecycle checks for the opt-in Gupabal game team."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import stat
import struct
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = 2
DECISION_PARTS = (".codex", "gupabal", "decision.json")
REQUIRED_APPROVALS = ("planner", "art", "client", "server")
MAX_FILES_PER_CALL = 128
MAX_TEXT_BYTES = 1_048_576
MAX_TOTAL_READ_BYTES = 16_777_216
MAX_PATCH_CHARS = 4_194_304
MAX_EVENT_CHARS = 8_388_608
POST_TIME_BUDGET_SECONDS = 2.0
MAX_SPEC_TOTAL_BYTES = 16_777_216
IMAGE_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
JPEG_SOF_MARKERS = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}
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


def fail_open_context(event_name: str | None, message: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "systemMessage": "구파발게임 Hook 입력을 완전히 검사하지 못했습니다."
    }
    if event_name in {"SubagentStop", "PreToolUse", "PostToolUse"}:
        payload["hookSpecificOutput"] = {
            "hookEventName": event_name,
            "additionalContext": message,
        }
    return payload


def deny_pre_tool(message: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": message,
        }
    }


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
    return None


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"중복 JSON key: {key}")
        result[key] = value
    return result


def reject_json_constant(value: str) -> None:
    raise ValueError(f"허용되지 않는 JSON 숫자: {value}")


def load_policy(cwd: str) -> tuple[Path | None, Path | None, dict[str, Any] | None, str | None]:
    root = find_repository_root(cwd)
    if root is None:
        return None, None, None, None
    decision_path = root.joinpath(*DECISION_PARTS)
    if decision_path.is_symlink():
        return root, decision_path, None, "decision.json이 symbolic link라 정책으로 사용할 수 없습니다."
    if not decision_path.exists():
        return root, decision_path, None, None
    if not decision_path.is_file():
        return root, decision_path, None, "decision.json이 일반 파일이 아닙니다."
    try:
        if decision_path.stat().st_size > MAX_TEXT_BYTES:
            return root, decision_path, None, "decision.json이 1MB를 초과합니다."
        policy = json.loads(
            decision_path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_json_constant,
        )
    except (OSError, UnicodeError, ValueError, RecursionError):
        return root, decision_path, None, "decision.json을 읽거나 해석할 수 없습니다."
    if not isinstance(policy, dict):
        return root, decision_path, None, "decision.json의 최상위 값이 객체가 아닙니다."
    enabled = policy.get("enabled")
    schema_version = policy.get("schema_version")
    if type(enabled) is not bool:
        return root, decision_path, None, "decision.json의 enabled는 boolean이어야 합니다."
    if type(schema_version) is not int:
        return root, decision_path, None, "decision.json의 schema_version은 정수여야 합니다."
    if schema_version == 1 and enabled is False:
        return root, decision_path, None, None
    if schema_version != SCHEMA_VERSION:
        return root, decision_path, None, "지원하지 않는 decision.json 버전입니다."
    if enabled is False:
        closure_errors = validate_contract_schema(policy, inactive_closure=True)
        if not closure_errors:
            closure_errors.extend(validate_spec_refs(policy, root))
        if closure_errors:
            return (
                root,
                decision_path,
                None,
                "비활성 decision.json 종료 상태가 올바르지 않습니다: "
                + ", ".join(closure_errors),
            )
        return root, decision_path, None, None
    return root, decision_path, policy, None


def extract_patch_operations(tool_input: Any) -> list[tuple[str, str]]:
    if not isinstance(tool_input, dict):
        return []
    command = tool_input.get("command")
    if not isinstance(command, str) or len(command) > MAX_PATCH_CHARS:
        return []
    operations: list[tuple[str, str]] = []
    for match in re.finditer(
        r"^\*\*\* (Add|Update|Delete) File:\s*(.+?)\s*$",
        command,
        flags=re.MULTILINE,
    ):
        value = match.group(2).strip().strip('"\'')
        if value:
            operations.append((match.group(1), value))
    for match in re.finditer(
        r"^\*\*\* Move to:\s*(.+?)\s*$", command, flags=re.MULTILINE
    ):
        value = match.group(1).strip().strip('"\'')
        if value:
            operations.append(("Move", value))
    return operations


def is_decision_only_repair(
    tool_input: Any, root: Path, decision_path: Path
) -> bool:
    operations = extract_patch_operations(tool_input)
    if len(operations) != 1:
        return False
    operation, raw_path = operations[0]
    supplied = Path(raw_path)
    if ".." in supplied.parts:
        return False
    try:
        candidate = supplied if supplied.is_absolute() else root / supplied
        relative = candidate.absolute().relative_to(root.absolute()).as_posix()
    except (OSError, RuntimeError, ValueError):
        return False
    if relative != decision_path.relative_to(root).as_posix():
        return False
    if decision_path.is_symlink():
        return operation == "Delete"
    return operation in {"Add", "Update"}


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


def path_is_excluded_by_patterns(relative_path: str, patterns: list[str]) -> bool:
    candidates = [relative_path]
    parent = PurePosixPath(relative_path).parent
    while parent.as_posix() not in {"", "."}:
        candidates.append(parent.as_posix())
        parent = parent.parent
    for pattern in patterns:
        if any(glob_matches(candidate, pattern) for candidate in candidates):
            return True
        if pattern.endswith("/**"):
            base_pattern = pattern[:-3].rstrip("/")
            if base_pattern and any(
                glob_matches(candidate, base_pattern) for candidate in candidates
            ):
                return True
    return False


def excluded(relative_path: str, policy: dict[str, Any]) -> bool:
    checks = policy.get("checks")
    if not isinstance(checks, dict):
        return False
    return path_is_excluded_by_patterns(
        relative_path, list_patterns(checks.get("exclude"))
    )


def contract_payload(policy: dict[str, Any]) -> dict[str, Any]:
    agreement = policy["agreement"]
    spec_refs = agreement["spec_refs"]
    if not isinstance(agreement, dict) or not isinstance(spec_refs, list):
        raise ValueError("agreement 또는 spec_refs 형식이 올바르지 않습니다.")
    ordered_refs = sorted(spec_refs, key=lambda item: item["path"])
    return {
        "schema_version": policy["schema_version"],
        "feature": policy["feature"],
        "revision": agreement["revision"],
        "summary": agreement["summary"],
        "invariants": agreement["invariants"],
        "spec_refs": ordered_refs,
        "ownership": policy["ownership"],
        "checks": policy["checks"],
    }


def compute_contract_digest(policy: dict[str, Any]) -> str:
    canonical = json.dumps(
        contract_payload(policy),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def find_float(value: Any, location: str = "contract") -> str | None:
    if type(value) is float:
        return location
    if isinstance(value, dict):
        for key, item in value.items():
            found = find_float(item, f"{location}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = find_float(item, f"{location}[{index}]")
            if found:
                return found
    return None


def validate_contract_schema(
    policy: dict[str, Any], *, inactive_closure: bool = False
) -> list[str]:
    errors: list[str] = []
    allowed_top = {
        "schema_version",
        "enabled",
        "feature",
        "planning_allow",
        "agreement",
        "ownership",
        "checks",
    }
    unknown_top = sorted(set(policy) - allowed_top)
    if unknown_top:
        errors.append(f"허용되지 않은 필드: {', '.join(unknown_top)}")
    missing_top = sorted(allowed_top - set(policy))
    if missing_top:
        errors.append(f"누락된 필드: {', '.join(missing_top)}")
    feature = policy.get("feature")
    if not isinstance(feature, str) or not feature.strip():
        errors.append("feature")
    if not isinstance(policy.get("ownership"), dict):
        errors.append("ownership 형식")
    if not isinstance(policy.get("checks"), dict):
        errors.append("checks 형식")

    agreement = policy.get("agreement")
    if not isinstance(agreement, dict):
        errors.append("agreement 형식")
        return errors
    allowed_agreement = {
        "status",
        "revision",
        "summary",
        "invariants",
        "spec_refs",
        "contract_digest",
        "approvals",
        "unresolved",
    }
    unknown_agreement = sorted(set(agreement) - allowed_agreement)
    if unknown_agreement:
        errors.append(
            f"agreement의 허용되지 않은 필드: {', '.join(unknown_agreement)}"
        )
    missing_agreement = sorted(allowed_agreement - set(agreement))
    if missing_agreement:
        errors.append(f"agreement 누락 필드: {', '.join(missing_agreement)}")
    revision = agreement.get("revision")
    if type(revision) is not int or revision <= 0:
        errors.append("revision")
    summary = agreement.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        errors.append("summary")
    invariants = agreement.get("invariants")
    if (
        not isinstance(invariants, list)
        or not invariants
        or any(not isinstance(item, str) or not item.strip() for item in invariants)
    ):
        errors.append("invariants")
    spec_refs = agreement.get("spec_refs")
    if not isinstance(spec_refs, list):
        errors.append("spec_refs 형식")
        spec_refs = []
    digest = agreement.get("contract_digest")
    if inactive_closure:
        if digest is not None:
            errors.append("비활성 contract_digest는 null")
    elif not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        errors.append("contract_digest 형식")
    unresolved = agreement.get("unresolved")
    if not isinstance(unresolved, list):
        errors.append("unresolved 형식")

    if inactive_closure:
        status = agreement.get("status")
        if status == "completed":
            if unresolved != []:
                errors.append("완료 상태의 unresolved는 빈 배열")
        elif status == "planning":
            if (
                not isinstance(unresolved, list)
                or len(unresolved) != 1
                or not isinstance(unresolved[0], str)
                or not unresolved[0].strip()
            ):
                errors.append("취소 상태의 unresolved는 사유 한 건")
        else:
            errors.append("비활성 agreement status")

    approvals = agreement.get("approvals")
    required_roles = set(REQUIRED_APPROVALS)
    if not isinstance(approvals, dict):
        errors.append("approvals 형식")
    else:
        if set(approvals) != required_roles:
            errors.append("approvals 역할 목록")
        for role in REQUIRED_APPROVALS:
            approval = approvals.get(role)
            if not isinstance(approval, dict):
                errors.append(f"{role} approval 형식")
                continue
            allowed_approval = {"status", "revision", "contract_digest"}
            if set(approval) != allowed_approval:
                errors.append(f"{role} approval 필드")
            if inactive_closure and approval.get("status") != "PENDING":
                errors.append(f"{role} approval status")
            elif not inactive_closure and approval.get("status") not in {
                "PENDING",
                "AGREE",
                "CONFLICT",
            }:
                errors.append(f"{role} approval status")
            approval_revision = approval.get("revision")
            if type(approval_revision) is not int or approval_revision <= 0:
                errors.append(f"{role} approval revision")
            elif inactive_closure and approval_revision != revision:
                errors.append(f"{role} approval revision")
            approval_digest = approval.get("contract_digest")
            if inactive_closure and approval_digest is not None:
                errors.append(f"{role} approval contract_digest")
            elif not inactive_closure and (
                not isinstance(approval_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", approval_digest) is None
            ):
                errors.append(f"{role} approval contract_digest")

    allowed_spec_ref = {"path", "owner", "schema_version", "sha256"}
    for index, spec_ref in enumerate(spec_refs):
        if not isinstance(spec_ref, dict):
            errors.append(f"spec_refs[{index}] 형식")
            continue
        if set(spec_ref) != allowed_spec_ref:
            errors.append(f"spec_refs[{index}] 필드")
        if type(spec_ref.get("schema_version")) is not int or spec_ref.get(
            "schema_version", 0
        ) <= 0:
            errors.append(f"spec_refs[{index}].schema_version")
        sha256 = spec_ref.get("sha256")
        if not isinstance(sha256, str) or re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
            errors.append(f"spec_refs[{index}].sha256")

    try:
        payload = contract_payload(policy)
    except (KeyError, TypeError, ValueError):
        errors.append("contract payload 형식")
    else:
        float_location = find_float(payload)
        if float_location:
            errors.append(f"실수형 숫자 금지: {float_location}")
    return errors


def normalized_spec_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    if value == ".":
        return None
    if "\\" in value or "\x00" in value or re.search(r"[*?\[]", value):
        return None
    if re.match(r"^[A-Za-z]:", value):
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        return None
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path.as_posix()


def is_link_or_junction(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(reparse_flag and attributes & reparse_flag)
    except OSError:
        return True


def validate_spec_refs(policy: dict[str, Any], root: Path) -> list[str]:
    agreement = policy.get("agreement")
    spec_refs = agreement.get("spec_refs") if isinstance(agreement, dict) else None
    if not isinstance(spec_refs, list):
        return ["spec_refs 형식"]
    errors: list[str] = []
    seen: set[str] = set()
    seen_casefold: set[str] = set()
    total_bytes = 0
    try:
        resolved_root = root.resolve(strict=True)
    except (OSError, RuntimeError):
        return ["spec_refs 저장소 루트를 확인할 수 없음"]
    for index, spec_ref in enumerate(spec_refs):
        label = f"spec_refs[{index}]"
        if not isinstance(spec_ref, dict):
            continue
        relative = normalized_spec_path(spec_ref.get("path"))
        if relative is None:
            errors.append(f"{label}.path")
            continue
        folded = relative.casefold()
        if relative in seen or folded in seen_casefold:
            errors.append(f"{label}.path 중복")
            continue
        seen.add(relative)
        seen_casefold.add(folded)
        owner = spec_ref.get("owner")
        if owner not in {"art", "client", "server"}:
            errors.append(f"{label}.owner")
        elif owners_for(relative, policy) != {owner}:
            errors.append(f"{label}.owner가 고유 ownership과 불일치")

        candidate = root.joinpath(*PurePosixPath(relative).parts)
        current = root
        linked = False
        for part in PurePosixPath(relative).parts:
            current = current / part
            if is_link_or_junction(current):
                linked = True
                break
        if linked:
            errors.append(f"{label}.path symlink 또는 junction")
            continue
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(resolved_root)
        except (OSError, RuntimeError, ValueError):
            errors.append(f"{label}.path 파일 없음 또는 저장소 밖")
            continue
        if not candidate.is_file():
            errors.append(f"{label}.path 일반 파일 아님")
            continue
        try:
            size = candidate.stat().st_size
        except OSError:
            errors.append(f"{label}.path 크기 확인 실패")
            continue
        if size > MAX_TEXT_BYTES:
            errors.append(f"{label}.path 1MB 초과")
            continue
        total_bytes += size
        if total_bytes > MAX_SPEC_TOTAL_BYTES:
            errors.append("spec_refs 전체 크기 16MB 초과")
            break
        try:
            text = candidate.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            errors.append(f"{label}.path UTF-8 텍스트 아님")
            continue
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        actual_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if spec_ref.get("sha256") != actual_hash:
            errors.append(f"{label}.sha256 불일치")
    return errors


def agreement_ready(policy: dict[str, Any], root: Path) -> tuple[bool, list[str]]:
    agreement = policy.get("agreement")
    if not isinstance(agreement, dict) or agreement.get("status") != "approved":
        return False, list(REQUIRED_APPROVALS)
    missing = validate_contract_schema(policy)
    if missing:
        return False, missing
    try:
        computed_digest = compute_contract_digest(policy)
    except (KeyError, TypeError, ValueError):
        return False, ["contract_digest 계산 실패"]
    if agreement.get("contract_digest") != computed_digest:
        missing.append("contract_digest 불일치")
    approvals = agreement["approvals"]
    revision = agreement["revision"]
    for role in REQUIRED_APPROVALS:
        approval = approvals[role]
        if approval.get("status") != "AGREE":
            missing.append(f"{role} approval status")
        if approval.get("revision") != revision:
            missing.append(f"{role} approval revision")
        if approval.get("contract_digest") != computed_digest:
            missing.append(f"{role} approval contract_digest")
    unresolved = agreement.get("unresolved")
    if unresolved:
        missing.append(f"미결정 {len(unresolved)}건")
    missing.extend(validate_spec_refs(policy, root))
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
        if root is not None and decision_path is not None and is_decision_only_repair(
            tool_input, root, decision_path
        ):
            return None
        return deny_pre_tool(
            f"구파발게임 합의 파일을 적용하지 못해 구현 변경을 중단했습니다: {policy_error} "
            "Git 루트의 .codex/gupabal/decision.json만 별도의 작은 apply_patch로 복구하세요."
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

    ready, missing = agreement_ready(policy, root)
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

    agreement = policy["agreement"]
    protected_specs = {
        spec_ref["path"]
        for spec_ref in agreement["spec_refs"]
        if isinstance(spec_ref, dict) and isinstance(spec_ref.get("path"), str)
    }
    changed_specs = [path for path in implementation_paths if path in protected_specs]
    if changed_specs:
        return deny_pre_tool(
            "승인된 spec_refs 파일은 현재 revision에서 직접 바꿀 수 없습니다: "
            + ", ".join(changed_specs[:10])
            + ". decision.json을 planning으로 되돌리고 revision을 올린 뒤 재승인하세요."
        )

    owners_by_path = {
        path: owners_for(path, policy) for path in implementation_paths
    }
    outside = [path for path, owners in owners_by_path.items() if not owners]
    ambiguous = [path for path, owners in owners_by_path.items() if len(owners) > 1]
    ownership_findings: list[str] = []
    if outside:
        preview = ", ".join(outside[:10])
        suffix = f" 외 {len(outside) - 10}개" if len(outside) > 10 else ""
        ownership_findings.append(f"소유 역할이 없는 파일: {preview}{suffix}")
    if ambiguous:
        preview = ", ".join(ambiguous[:10])
        suffix = f" 외 {len(ambiguous) - 10}개" if len(ambiguous) > 10 else ""
        ownership_findings.append(f"소유 역할이 둘 이상인 파일: {preview}{suffix}")
    if ownership_findings:
        return deny_pre_tool(
            "구파발게임 구현 파일은 정확히 한 소유 역할에만 배정되어야 합니다. "
            + "; ".join(ownership_findings)
            + ". decision.json의 ownership을 먼저 고치세요."
        )
    return None


def validate_png_structure(path: Path) -> str | None:
    import zlib

    try:
        with path.open("rb") as image_file:
            if image_file.read(8) != b"\x89PNG\r\n\x1a\n":
                return "PNG 헤더가 올바르지 않습니다"
            first_chunk = True
            saw_idat = False
            idat_payload_bytes = 0
            while True:
                length_bytes = image_file.read(4)
                if len(length_bytes) != 4:
                    return "PNG IEND 청크가 없습니다"
                length = int.from_bytes(length_bytes, "big")
                kind = image_file.read(4)
                if len(kind) != 4:
                    return "PNG 청크 헤더가 불완전합니다"
                if first_chunk and (kind != b"IHDR" or length != 13):
                    return "PNG 첫 청크가 IHDR이 아닙니다"
                first_chunk = False
                checksum = zlib.crc32(kind)
                remaining = length
                while remaining:
                    block = image_file.read(min(remaining, 65_536))
                    if not block:
                        return "PNG 청크 데이터가 불완전합니다"
                    checksum = zlib.crc32(block, checksum)
                    remaining -= len(block)
                expected_crc = image_file.read(4)
                if len(expected_crc) != 4 or int.from_bytes(
                    expected_crc, "big"
                ) != checksum & 0xFFFFFFFF:
                    return "PNG 청크 CRC가 올바르지 않습니다"
                if kind == b"IDAT":
                    saw_idat = True
                    idat_payload_bytes += length
                if kind == b"IEND":
                    if length != 0 or not saw_idat or idat_payload_bytes == 0:
                        return "PNG IDAT 또는 IEND 청크가 올바르지 않습니다"
                    if image_file.read(1):
                        return "PNG IEND 뒤에 데이터가 남아 있습니다"
                    return None
    except OSError:
        return "PNG 파일을 읽을 수 없습니다"


def read_jpeg_dimensions(path: Path) -> tuple[int | None, int | None, str | None]:
    try:
        with path.open("rb") as image_file:
            if image_file.read(2) != b"\xff\xd8":
                return None, None, "JPEG 헤더가 올바르지 않습니다"
            while True:
                prefix = image_file.read(1)
                if not prefix:
                    return None, None, "JPEG 크기 표식이 없습니다"
                if prefix != b"\xff":
                    continue
                marker_byte = image_file.read(1)
                while marker_byte == b"\xff":
                    marker_byte = image_file.read(1)
                if not marker_byte:
                    return None, None, "JPEG marker가 불완전합니다"
                marker = marker_byte[0]
                if marker in {0xD9, 0xDA}:
                    return None, None, "JPEG 크기 표식이 없습니다"
                if marker == 0x01 or 0xD0 <= marker <= 0xD8:
                    continue
                length_bytes = image_file.read(2)
                if len(length_bytes) != 2:
                    return None, None, "JPEG segment가 불완전합니다"
                segment_length = int.from_bytes(length_bytes, "big")
                if segment_length < 2:
                    return None, None, "JPEG segment 길이가 올바르지 않습니다"
                if marker in JPEG_SOF_MARKERS:
                    if segment_length < 7:
                        return None, None, "JPEG SOF segment가 불완전합니다"
                    dimensions = image_file.read(5)
                    if len(dimensions) != 5:
                        return None, None, "JPEG SOF segment가 불완전합니다"
                    height = int.from_bytes(dimensions[1:3], "big")
                    width = int.from_bytes(dimensions[3:5], "big")
                    return (
                        width,
                        height,
                        None if width > 0 and height > 0 else "JPEG 크기가 0입니다",
                    )
                image_file.seek(segment_length - 2, 1)
    except OSError:
        return None, None, "JPEG 파일을 읽을 수 없습니다"


def validate_jpeg_structure(path: Path) -> str | None:
    saw_sof = False
    saw_sos = False
    saw_scan_data = False
    in_scan = False
    current_scan_has_data = False
    pending_marker: int | None = None
    try:
        with path.open("rb") as image_file:
            if image_file.read(2) != b"\xff\xd8":
                return "JPEG 헤더가 올바르지 않습니다"
            while True:
                if in_scan:
                    value = image_file.read(1)
                    if not value:
                        return "JPEG EOI marker가 없습니다"
                    if value != b"\xff":
                        current_scan_has_data = True
                        continue
                    marker_byte = image_file.read(1)
                    while marker_byte == b"\xff":
                        marker_byte = image_file.read(1)
                    if not marker_byte:
                        return "JPEG scan marker가 불완전합니다"
                    marker = marker_byte[0]
                    if marker == 0x00:
                        current_scan_has_data = True
                        continue
                    if 0xD0 <= marker <= 0xD7:
                        current_scan_has_data = True
                        continue
                    if not current_scan_has_data:
                        return "JPEG scan 데이터가 없습니다"
                    saw_scan_data = True
                    if marker == 0xD9:
                        return None
                    in_scan = False
                    pending_marker = marker
                    continue

                if pending_marker is None:
                    prefix = image_file.read(1)
                    if not prefix:
                        return "JPEG EOI marker가 없습니다"
                    if prefix != b"\xff":
                        return "JPEG segment marker가 올바르지 않습니다"
                    marker_byte = image_file.read(1)
                    while marker_byte == b"\xff":
                        marker_byte = image_file.read(1)
                    if not marker_byte:
                        return "JPEG marker가 불완전합니다"
                    marker = marker_byte[0]
                else:
                    marker = pending_marker
                    pending_marker = None

                if marker == 0xD9:
                    return None if saw_sos and saw_scan_data else "JPEG scan 데이터가 없습니다"
                if marker in {0x00, 0xD8} or 0xD0 <= marker <= 0xD7:
                    return "JPEG marker 순서가 올바르지 않습니다"
                if marker == 0x01:
                    continue
                length_bytes = image_file.read(2)
                if len(length_bytes) != 2:
                    return "JPEG segment가 불완전합니다"
                segment_length = int.from_bytes(length_bytes, "big")
                if segment_length < 2:
                    return "JPEG segment 길이가 올바르지 않습니다"
                payload = image_file.read(segment_length - 2)
                if len(payload) != segment_length - 2:
                    return "JPEG segment 데이터가 불완전합니다"
                if marker in JPEG_SOF_MARKERS:
                    if len(payload) < 6:
                        return "JPEG SOF segment가 불완전합니다"
                    components = payload[5]
                    if (
                        components == 0
                        or len(payload) != 6 + 3 * components
                        or int.from_bytes(payload[1:3], "big") == 0
                        or int.from_bytes(payload[3:5], "big") == 0
                    ):
                        return "JPEG SOF segment가 올바르지 않습니다"
                    saw_sof = True
                elif marker == 0xDA:
                    if not saw_sof or len(payload) < 4:
                        return "JPEG SOS segment가 올바르지 않습니다"
                    components = payload[0]
                    if components == 0 or len(payload) != 1 + 2 * components + 3:
                        return "JPEG SOS segment가 올바르지 않습니다"
                    saw_sos = True
                    in_scan = True
                    current_scan_has_data = False
    except OSError:
        return "JPEG 파일을 읽을 수 없습니다"


def read_gif_sub_blocks(image_file: Any) -> tuple[bool, str | None]:
    saw_data = False
    while True:
        size_byte = image_file.read(1)
        if not size_byte:
            return saw_data, "GIF data sub-block이 불완전합니다"
        size = size_byte[0]
        if size == 0:
            return saw_data, None
        saw_data = True
        if len(image_file.read(size)) != size:
            return saw_data, "GIF data sub-block이 불완전합니다"


def validate_gif_structure(path: Path) -> str | None:
    saw_image = False
    try:
        with path.open("rb") as image_file:
            header = image_file.read(13)
            if len(header) != 13 or header[:6] not in {b"GIF87a", b"GIF89a"}:
                return "GIF 헤더가 올바르지 않습니다"
            if int.from_bytes(header[6:8], "little") == 0 or int.from_bytes(
                header[8:10], "little"
            ) == 0:
                return "GIF 크기가 0입니다"
            packed = header[10]
            if packed & 0x80:
                table_size = 3 * (2 ** ((packed & 0x07) + 1))
                if len(image_file.read(table_size)) != table_size:
                    return "GIF global color table이 불완전합니다"
            while True:
                block_type = image_file.read(1)
                if not block_type:
                    return "GIF trailer가 없습니다"
                if block_type == b"\x3b":
                    if not saw_image:
                        return "GIF image block이 없습니다"
                    if image_file.read(1):
                        return "GIF trailer 뒤에 데이터가 남아 있습니다"
                    return None
                if block_type == b"\x21":
                    if len(image_file.read(1)) != 1:
                        return "GIF extension label이 불완전합니다"
                    _, error = read_gif_sub_blocks(image_file)
                    if error:
                        return error
                    continue
                if block_type != b"\x2c":
                    return "GIF block marker가 올바르지 않습니다"
                descriptor = image_file.read(9)
                if len(descriptor) != 9:
                    return "GIF image descriptor가 불완전합니다"
                if int.from_bytes(descriptor[4:6], "little") == 0 or int.from_bytes(
                    descriptor[6:8], "little"
                ) == 0:
                    return "GIF image 크기가 0입니다"
                image_packed = descriptor[8]
                if image_packed & 0x80:
                    table_size = 3 * (2 ** ((image_packed & 0x07) + 1))
                    if len(image_file.read(table_size)) != table_size:
                        return "GIF local color table이 불완전합니다"
                code_size = image_file.read(1)
                if len(code_size) != 1 or not 2 <= code_size[0] <= 8:
                    return "GIF LZW code size가 올바르지 않습니다"
                saw_data, error = read_gif_sub_blocks(image_file)
                if error:
                    return error
                if not saw_data:
                    return "GIF image data가 없습니다"
                saw_image = True
    except OSError:
        return "GIF 파일을 읽을 수 없습니다"


def validate_webp_visual_payload(
    kind: bytes, size: int, prefix: bytes
) -> str | None:
    if kind == b"VP8 ":
        if size <= 10 or len(prefix) < 10 or prefix[3:6] != b"\x9d\x01\x2a":
            return "WebP VP8 payload가 불완전합니다"
        frame_tag = int.from_bytes(prefix[:3], "little")
        first_partition_length = (frame_tag >> 5) & 0x7FFFF
        if (
            first_partition_length == 0
            or first_partition_length > size - 10
        ):
            return "WebP VP8 first partition 길이가 올바르지 않습니다"
        return None
    if kind == b"VP8L":
        if size <= 5 or len(prefix) < 5 or prefix[0] != 0x2F:
            return "WebP VP8L payload가 불완전합니다"
        if int.from_bytes(prefix[1:5], "little") >> 29:
            return "WebP VP8L version bit가 올바르지 않습니다"
        return None
    return "WebP visual chunk가 올바르지 않습니다"


def validate_anmf_structure(
    image_file: Any, data_start: int, size: int
) -> str | None:
    if size <= 16:
        return "WebP ANMF frame payload가 불완전합니다"
    payload_end = data_start + size
    offset = data_start + 16
    saw_visual_chunk = False
    while offset < payload_end:
        image_file.seek(offset)
        chunk_header = image_file.read(8)
        if len(chunk_header) != 8:
            return "WebP ANMF 내부 청크 헤더가 불완전합니다"
        kind = chunk_header[:4]
        nested_size = int.from_bytes(chunk_header[4:8], "little")
        padded_size = nested_size + (nested_size % 2)
        chunk_end = offset + 8 + padded_size
        if chunk_end > payload_end:
            return "WebP ANMF 내부 청크가 frame 경계를 벗어납니다"
        prefix = image_file.read(min(nested_size, 16))
        if len(prefix) != min(nested_size, 16):
            return "WebP ANMF 내부 청크 데이터가 불완전합니다"
        if kind in {b"VP8 ", b"VP8L"}:
            visual_error = validate_webp_visual_payload(kind, nested_size, prefix)
            if visual_error:
                return visual_error
            saw_visual_chunk = True
        elif kind != b"ALPH":
            return "WebP ANMF 내부 청크 종류가 올바르지 않습니다"
        offset = chunk_end
    if offset != payload_end:
        return "WebP ANMF 내부 청크 경계가 올바르지 않습니다"
    if not saw_visual_chunk:
        return "WebP ANMF 내부 이미지 데이터 청크가 없습니다"
    return None


def validate_webp_structure(path: Path, actual_size: int) -> str | None:
    saw_visual_chunk = False
    offset = 12
    try:
        with path.open("rb") as image_file:
            image_file.seek(offset)
            while offset < actual_size:
                chunk_header = image_file.read(8)
                if len(chunk_header) != 8:
                    return "WebP 청크 헤더가 불완전합니다"
                kind = chunk_header[:4]
                size = int.from_bytes(chunk_header[4:8], "little")
                padded_size = size + (size % 2)
                chunk_end = offset + 8 + padded_size
                if chunk_end > actual_size:
                    return "WebP 청크 크기가 파일 경계를 벗어납니다"
                prefix = image_file.read(min(size, 16))
                if len(prefix) != min(size, 16):
                    return "WebP 청크 데이터가 불완전합니다"
                if kind == b"VP8X" and size != 10:
                    return "WebP VP8X 헤더가 불완전합니다"
                if kind in {b"VP8 ", b"VP8L"}:
                    visual_error = validate_webp_visual_payload(kind, size, prefix)
                    if visual_error:
                        return visual_error
                    saw_visual_chunk = True
                elif kind == b"ANMF":
                    frame_error = validate_anmf_structure(
                        image_file, offset + 8, size
                    )
                    if frame_error:
                        return frame_error
                    saw_visual_chunk = True
                image_file.seek(chunk_end)
                offset = chunk_end
    except OSError:
        return "WebP 파일을 읽을 수 없습니다"
    if offset != actual_size:
        return "WebP 청크 경계가 올바르지 않습니다"
    if not saw_visual_chunk:
        return "WebP 이미지 데이터 청크가 없습니다"
    return None


def read_image_info(
    path: Path, *, complete: bool = False
) -> tuple[int | None, int | None, str | None]:
    extension = path.suffix.lower()
    try:
        with path.open("rb") as image_file:
            header = image_file.read(65_536)
    except OSError:
        return None, None, "파일을 읽을 수 없습니다"
    if extension == ".png":
        import zlib

        if (
            len(header) < 33
            or header[:8] != b"\x89PNG\r\n\x1a\n"
            or header[8:12] != b"\x00\x00\x00\x0d"
            or header[12:16] != b"IHDR"
        ):
            return None, None, "PNG 헤더가 올바르지 않습니다"
        expected_crc = int.from_bytes(header[29:33], "big")
        if expected_crc != zlib.crc32(header[12:29]) & 0xFFFFFFFF:
            return None, None, "PNG IHDR CRC가 올바르지 않습니다"
        width, height = struct.unpack(">II", header[16:24])
        if complete:
            structure_error = validate_png_structure(path)
            if structure_error:
                return None, None, structure_error
        return width, height, None if width > 0 and height > 0 else "PNG 크기가 0입니다"
    if extension in {".jpg", ".jpeg"}:
        width, height, error = read_jpeg_dimensions(path)
        if error is None and complete:
            error = validate_jpeg_structure(path)
        return width, height, error
    if extension == ".gif":
        if len(header) < 13 or header[:6] not in {b"GIF87a", b"GIF89a"}:
            return None, None, "GIF 헤더가 올바르지 않습니다"
        width, height = struct.unpack("<HH", header[6:10])
        error = None if width > 0 and height > 0 else "GIF 크기가 0입니다"
        if error is None and complete:
            error = validate_gif_structure(path)
        return width, height, error
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
        if complete:
            structure_error = validate_webp_structure(path, actual_size)
            if structure_error:
                return None, None, structure_error
        chunk = header[12:16]
        chunk_size = int.from_bytes(header[16:20], "little")
        chunk_end = 20 + chunk_size + (chunk_size % 2)
        if chunk_end > actual_size:
            return None, None, "WebP 청크 크기가 파일 경계를 벗어납니다"
        if chunk == b"VP8X":
            if (
                chunk_size != 10
                or len(header) < 30
                or actual_size < chunk_end + 8
            ):
                return None, None, "WebP VP8X 헤더가 불완전합니다"
            width = 1 + int.from_bytes(header[24:27], "little")
            height = 1 + int.from_bytes(header[27:30], "little")
            return width, height, None
        if chunk == b"VP8L":
            if chunk_size < 5 or len(header) < 25 or header[20] != 0x2F:
                return None, None, "WebP VP8L 헤더가 불완전합니다"
            bits = int.from_bytes(header[21:25], "little")
            if bits >> 29:
                return None, None, "WebP VP8L version bit가 올바르지 않습니다"
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
        from xml.etree import ElementTree

        try:
            if path.stat().st_size > MAX_TEXT_BYTES:
                return None, None, "SVG가 1MB를 초과해 안전하게 해석할 수 없습니다"
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            return None, None, "SVG가 UTF-8 텍스트가 아닙니다"
        declarations = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        if "<!DOCTYPE" in declarations.upper() or "<!ENTITY" in declarations.upper():
            return None, None, "SVG의 DTD 또는 ENTITY 선언은 허용되지 않습니다"
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError:
            return None, None, "SVG XML 문법이 올바르지 않습니다"
        if root.tag.rsplit("}", 1)[-1] != "svg":
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


def inspect_file(
    path: Path,
    relative_path: str,
    domains: set[str],
    policy: dict[str, Any],
    *,
    complete: bool = False,
) -> list[str]:
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
                width, height, image_error = read_image_info(path, complete=complete)
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


def verifier_result(
    status: str,
    checked: int,
    findings: list[dict[str, str]],
    errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    def ordered(items: list[dict[str, str]]) -> list[dict[str, str]]:
        return sorted(
            items,
            key=lambda item: (
                item.get("path", ""),
                item.get("code", ""),
                item.get("message", ""),
            ),
        )

    return {
        "schema_version": 1,
        "status": status,
        "checked": checked,
        "findings": ordered(findings),
        "errors": ordered(errors or []),
    }


def verifier_error(message: str, code: str = "policy_error") -> dict[str, Any]:
    return verifier_result(
        "error",
        0,
        [],
        [{"code": code, "path": "", "message": message}],
    )


def valid_glob_list(value: Any, label: str) -> tuple[list[str], list[str]]:
    if not isinstance(value, list):
        return [], [f"{label}은 배열이어야 합니다."]
    patterns: list[str] = []
    errors: list[str] = []
    for index, item in enumerate(value):
        pattern = normalize_pattern(item)
        if (
            pattern is None
            or ".." in PurePosixPath(pattern).parts
            or any(character in pattern for character in "[]{}")
        ):
            errors.append(f"{label}[{index}] glob 패턴이 올바르지 않습니다.")
        else:
            patterns.append(pattern)
    return patterns, errors


def verifier_art_configuration(
    policy: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    checks = policy.get("checks")
    if not isinstance(checks, dict):
        return None, ["checks 형식이 올바르지 않습니다."]
    exclude_patterns, exclude_errors = valid_glob_list(
        checks.get("exclude"), "checks.exclude"
    )
    errors.extend(exclude_errors)
    art = checks.get("art")
    if not isinstance(art, dict):
        return None, errors + ["checks.art 형식이 올바르지 않습니다."]
    allowed_art = {"roots", "max_file_bytes", "naming_glob", "assets"}
    if set(art) - allowed_art:
        errors.append("checks.art에 허용되지 않은 필드가 있습니다.")
    roots, root_errors = valid_glob_list(art.get("roots"), "checks.art.roots")
    errors.extend(root_errors)
    maximum = art.get("max_file_bytes")
    if maximum is not None and (type(maximum) is not int or maximum <= 0):
        errors.append("checks.art.max_file_bytes는 null 또는 양의 정수여야 합니다.")
    naming_glob = art.get("naming_glob")
    if naming_glob is not None:
        normalized_name = normalize_pattern(naming_glob)
        if (
            normalized_name is None
            or "/" in normalized_name
            or any(character in normalized_name for character in "[]{}")
        ):
            errors.append(
                "checks.art.naming_glob은 지원되는 파일 이름 glob이어야 합니다."
            )
    assets = art.get("assets")
    if not isinstance(assets, list):
        return None, errors + ["checks.art.assets는 배열이어야 합니다."]
    declared: dict[str, dict[str, Any]] = {}
    folded_paths: set[str] = set()
    allowed_asset = {"path", "width", "height", "max_bytes"}
    for index, asset in enumerate(assets):
        label = f"checks.art.assets[{index}]"
        if not isinstance(asset, dict):
            errors.append(f"{label} 형식이 올바르지 않습니다.")
            continue
        if set(asset) - allowed_asset:
            errors.append(f"{label}에 허용되지 않은 필드가 있습니다.")
        relative = normalized_spec_path(asset.get("path"))
        if relative is None:
            errors.append(f"{label}.path가 올바르지 않습니다.")
            continue
        folded = relative.casefold()
        if relative in declared or folded in folded_paths:
            errors.append(f"{label}.path가 중복됩니다.")
            continue
        folded_paths.add(folded)
        for field in ("width", "height", "max_bytes"):
            value = asset.get(field)
            if value is not None and (type(value) is not int or value <= 0):
                errors.append(f"{label}.{field}는 양의 정수여야 합니다.")
        if path_is_excluded_by_patterns(relative, exclude_patterns):
            errors.append(f"{label}.path가 checks.exclude와 충돌합니다.")
        declared[relative] = asset
    if errors:
        return None, errors
    return {
        "roots": roots,
        "exclude": exclude_patterns,
        "declared": declared,
    }, []


def directory_is_excluded(relative: str, policy: dict[str, Any]) -> bool:
    return excluded(relative, policy)


def link_may_affect_roots(relative: str, roots: list[str]) -> bool:
    for pattern in roots:
        if glob_matches(relative, pattern):
            return True
        wildcard_positions = [
            position
            for character in ("*", "?")
            if (position := pattern.find(character)) >= 0
        ]
        if wildcard_positions:
            fixed_text = pattern[: min(wildcard_positions)]
            separator = fixed_text.rfind("/")
            prefix = fixed_text[:separator].rstrip("/") if separator >= 0 else ""
        else:
            prefix = pattern.rstrip("/")
        if not prefix:
            return True
        if (
            relative == prefix
            or relative.startswith(prefix + "/")
            or prefix.startswith(relative + "/")
        ):
            return True
    return False


def collect_repository_files(
    root: Path, policy: dict[str, Any], roots: list[str]
) -> tuple[list[tuple[str, Path]], str | None]:
    files: list[tuple[str, Path]] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(
                directory.iterdir(), key=lambda path: (path.name.casefold(), path.name)
            )
        except OSError:
            return [], "저장소 파일 목록을 읽을 수 없습니다."
        child_directories: list[Path] = []
        for entry in entries:
            relative = entry.relative_to(root).as_posix()
            if is_link_or_junction(entry):
                if not excluded(relative, policy) and link_may_affect_roots(
                    relative, roots
                ):
                    return [], (
                        "아트 root 범위의 symlink 또는 junction을 따라가지 않아 "
                        f"완전 검증할 수 없습니다: {relative}"
                    )
                continue
            try:
                if entry.is_dir():
                    if (
                        not directory_is_excluded(relative, policy)
                        and link_may_affect_roots(relative, roots)
                    ):
                        child_directories.append(entry)
                elif (
                    entry.is_file()
                    and not excluded(relative, policy)
                    and any(glob_matches(relative, pattern) for pattern in roots)
                ):
                    files.append((relative, entry))
            except OSError:
                return [], f"저장소 경로를 확인할 수 없습니다: {relative}"
        stack.extend(reversed(child_directories))
    return files, None


def declared_asset_path_error(root: Path, relative: str) -> str | None:
    current = root
    for part in PurePosixPath(relative).parts:
        if not current.exists():
            return None
        try:
            children = list(current.iterdir())
        except OSError:
            return "상위 디렉터리를 읽을 수 없습니다."
        exact = next((child for child in children if child.name == part), None)
        if exact is None:
            if any(child.name.casefold() == part.casefold() for child in children):
                return "선언 경로의 대소문자가 실제 경로와 다릅니다."
            return None
        current = exact
        if is_link_or_junction(current):
            return "symlink 또는 junction 경로는 검사할 수 없습니다."
    if not current.exists():
        return None
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (OSError, RuntimeError, ValueError):
        return "저장소 밖 경로는 검사할 수 없습니다."
    if not current.is_file():
        return "일반 파일이 아닙니다."
    return None


def verifier_message_is_incomplete(message: str) -> bool:
    return any(
        marker in message
        for marker in (
            "검증할 수 없습니다",
            "읽을 수 없습니다",
            "안전하게 해석할 수 없습니다",
            "완료 검증으로 넘겼습니다",
        )
    )


def verify_project(project_argument: str) -> tuple[int, dict[str, Any]]:
    try:
        root = Path(project_argument).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return 2, verifier_error("프로젝트 경로를 찾을 수 없습니다.", "input_error")
    if not root.is_dir():
        return 2, verifier_error("프로젝트 경로가 디렉터리가 아닙니다.", "input_error")
    repository_root = find_repository_root(str(root))
    if repository_root is None or repository_root != root:
        return 2, verifier_error(
            "--verify-project에는 정확한 Git 저장소 루트를 지정해야 합니다.",
            "input_error",
        )
    loaded_root, decision_path, policy, policy_error = load_policy(str(root))
    if policy_error:
        return 2, verifier_error(policy_error)
    if loaded_root != root or decision_path is None or policy is None:
        return 2, verifier_error("활성 schema v2 decision.json이 없습니다.")
    ready, agreement_errors = agreement_ready(policy, root)
    if not ready:
        return 2, verifier_error(
            "승인 계약을 완전 검증할 수 없습니다: " + ", ".join(agreement_errors)
        )
    configuration, configuration_errors = verifier_art_configuration(policy)
    if configuration is None:
        return 2, verifier_error("; ".join(configuration_errors))

    repository_files, walk_error = collect_repository_files(
        root, policy, configuration["roots"]
    )
    if walk_error:
        return 2, verifier_error(walk_error, "read_error")
    roots = configuration["roots"]
    declared = configuration["declared"]
    targets = {
        relative: path
        for relative, path in repository_files
        if any(glob_matches(relative, pattern) for pattern in roots)
    }
    findings: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    for relative in sorted(declared):
        path_error = declared_asset_path_error(root, relative)
        if path_error:
            return 2, verifier_error(
                f"{relative}: {path_error}", "policy_error"
            )
        candidate = root.joinpath(*PurePosixPath(relative).parts)
        if not candidate.exists():
            findings.append(
                {
                    "code": "missing_declared_asset",
                    "path": relative,
                    "message": "선언된 아트 에셋 파일이 없습니다.",
                }
            )
        else:
            targets[relative] = candidate

    checked = 0
    for relative in sorted(targets):
        path = targets[relative]
        try:
            with path.open("rb") as readable:
                readable.read(1)
        except OSError:
            return 2, verifier_error(
                f"{relative}: 파일을 읽을 권한이 없거나 파일 상태가 바뀌었습니다.",
                "read_error",
            )
        file_findings = inspect_file(
            path, relative, {"art"}, policy, complete=True
        )
        checked += 1
        prefix = f"{relative}: "
        for message in file_findings:
            detail = message[len(prefix):] if message.startswith(prefix) else message
            target = errors if verifier_message_is_incomplete(detail) else findings
            target.append(
                {
                    "code": (
                        "verification_incomplete" if target is errors else "asset_check"
                    ),
                    "path": relative,
                    "message": detail,
                }
            )
    if errors:
        return 2, verifier_result("error", checked, findings, errors)
    if findings:
        return 1, verifier_result("findings", checked, findings)
    return 0, verifier_result("ok", checked, [])


def verify_project_cli(arguments: list[str]) -> int:
    if len(arguments) != 1:
        emit(verifier_error("사용법: gupabal_hooks.py --verify-project <repo>", "usage"))
        return 2
    try:
        exit_code, payload = verify_project(arguments[0])
    except Exception as error:
        exit_code = 2
        payload = verifier_error(
            f"완전 검증 중 내부 오류가 발생했습니다: {type(error).__name__}",
            "internal_error",
        )
    emit(payload)
    return exit_code


def validate_post_tool(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("tool_name") != "apply_patch":
        return None
    root, decision_path, policy, policy_error = load_policy(str(event.get("cwd", "")))
    if policy_error:
        return post_context(
            f"구파발게임 합의 파일 오류로 변경 후 검사를 실행하지 못했습니다: {policy_error}"
        )
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
    if len(sys.argv) > 1 and sys.argv[1] == "--verify-project":
        return verify_project_cli(sys.argv[2:])
    event_hint = sys.argv[1] if len(sys.argv) > 1 else None
    raw_input = sys.stdin.read(MAX_EVENT_CHARS + 1)
    if len(raw_input) > MAX_EVENT_CHARS:
        emit(
            fail_open_context(
                event_hint,
                "구파발게임 Hook 입력이 8MB를 넘어 검사하지 못했습니다. "
                "이번 변경은 차단하지 않았습니다.",
            )
        )
        return 0
    try:
        event = json.loads(raw_input)
    except (UnicodeError, json.JSONDecodeError):
        emit(
            fail_open_context(
                event_hint,
                "구파발게임 Hook 입력이 올바른 JSON이 아니어서 검사하지 못했습니다. "
                "이번 변경은 차단하지 않았습니다.",
            )
        )
        return 0
    if not isinstance(event, dict):
        emit(
            fail_open_context(
                event_hint,
                "구파발게임 Hook 입력의 최상위 값이 객체가 아니어서 검사하지 못했습니다. "
                "이번 변경은 차단하지 않았습니다.",
            )
        )
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
    except Exception as error:
        # Hooks are guardrails, not an enforcement boundary. Unexpected failures stay visible.
        message = f"구파발게임 Hook 내부 오류로 검사를 완료하지 못했습니다: {type(error).__name__}"
        if event_name == "PreToolUse":
            emit(additional_context(message + ". 이번 변경은 차단하지 않았습니다."))
        elif event_name == "PostToolUse":
            emit(post_context(message))
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
