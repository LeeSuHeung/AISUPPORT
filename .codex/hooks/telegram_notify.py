#!/usr/bin/env python3
"""Send a minimal Telegram message when a Codex turn completes."""

from __future__ import annotations

import getpass
import json
import ntpath
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


CONFIG_NAME = "telegram-notify.json"
EVENT_TYPE = "agent-turn-complete"
MAX_RESPONSE_BYTES = 1_000_000


class TelegramError(RuntimeError):
    """A safe-to-display Telegram configuration or API error."""


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def credentials_path() -> Path:
    return codex_home() / CONFIG_NAME


def api_call(token: str, method: str, values: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=urllib.parse.urlencode(values).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        try:
            payload = json.loads(error.read(MAX_RESPONSE_BYTES).decode("utf-8"))
            description = payload.get("description")
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            description = None
        raise TelegramError(str(description or "Telegram API request was rejected")) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise TelegramError("Telegram network connection failed") from None

    if len(raw) > MAX_RESPONSE_BYTES:
        raise TelegramError("Telegram API response was too large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TelegramError("Telegram API returned invalid data") from None
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        description = payload.get("description") if isinstance(payload, dict) else None
        raise TelegramError(str(description or "Telegram API request failed"))
    return payload


def send_message(token: str, chat_id: str, text: str) -> None:
    api_call(token, "sendMessage", {"chat_id": chat_id, "text": text})


def load_credentials() -> tuple[str, str] | None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if token or chat_id:
        if not token or not chat_id:
            raise TelegramError(
                "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must both be set"
            )
        return token, chat_id

    path = credentials_path()
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise TelegramError(f"Credentials must be a regular file: {path}")
    if path.stat().st_size > 64 * 1024:
        raise TelegramError(f"Credentials file is too large: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise TelegramError(f"Credentials file is invalid: {path}") from None
    if not isinstance(payload, dict):
        raise TelegramError(f"Credentials file is invalid: {path}")
    token = payload.get("bot_token")
    chat_id = payload.get("chat_id")
    if not isinstance(token, str) or not token.strip():
        raise TelegramError("Telegram bot token is missing")
    if not isinstance(chat_id, (str, int)) or not str(chat_id).strip():
        raise TelegramError("Telegram chat ID is missing")
    return token.strip(), str(chat_id).strip()


def project_name(cwd: Any) -> str:
    if not isinstance(cwd, str) or not cwd.strip():
        return "알 수 없음"
    normalized = cwd.rstrip("/\\")
    name = ntpath.basename(normalized) if "\\" in normalized else Path(normalized).name
    return name or "알 수 없음"


def completion_message(notification: dict[str, Any]) -> str:
    return f"Codex 작업 완료\n프로젝트: {project_name(notification.get('cwd'))}"


def run_delegate(command: list[str], payload: str) -> None:
    if not command:
        return
    try:
        subprocess.run(
            [*command, payload],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def notify(arguments: list[str]) -> int:
    if not arguments:
        return 0
    payload_text = arguments[-1]
    delegate = arguments[1:-1] if arguments[0] == "--delegate" else []
    run_delegate(delegate, payload_text)

    try:
        notification = json.loads(payload_text)
    except json.JSONDecodeError:
        return 0
    if not isinstance(notification, dict) or notification.get("type") != EVENT_TYPE:
        return 0
    try:
        credentials = load_credentials()
        if credentials is not None:
            send_message(*credentials, completion_message(notification))
    except TelegramError as error:
        print(f"Telegram completion notification failed: {error}", file=sys.stderr)
    return 0


def save_credentials(token: str, chat_id: str) -> Path:
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise TelegramError(f"Credentials target must be a regular file: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            json.dump(
                {"bot_token": token, "chat_id": chat_id},
                output,
                ensure_ascii=False,
                indent=2,
            )
            output.write("\n")
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def configure() -> int:
    token = getpass.getpass("Telegram Bot Token: ").strip()
    if not token or any(character.isspace() for character in token):
        raise TelegramError("Bot token is empty or contains whitespace")

    bot = api_call(token, "getMe", {}).get("result")
    username = bot.get("username") if isinstance(bot, dict) else None
    if not isinstance(username, str) or not username:
        raise TelegramError("Telegram bot username was not returned")
    print(f"Telegram에서 https://t.me/{username} 를 열고 /start를 보내세요.")
    input("보낸 뒤 Enter를 누르세요: ")

    updates = api_call(token, "getUpdates", {}).get("result")
    chat_id = None
    if isinstance(updates, list):
        for update in reversed(updates):
            message = update.get("message") if isinstance(update, dict) else None
            chat = message.get("chat") if isinstance(message, dict) else None
            if isinstance(chat, dict) and chat.get("type") == "private":
                candidate = chat.get("id")
                if isinstance(candidate, (str, int)):
                    chat_id = str(candidate)
                    break
    if chat_id is None:
        raise TelegramError("/start 메시지를 찾지 못했습니다. 다시 보내고 재실행하세요")

    send_message(token, chat_id, "Codex 텔레그램 완료 알림 연결 성공")
    path = save_credentials(token, chat_id)
    print(f"연결 완료: {path}")
    return 0


def main(arguments: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    try:
        if arguments == ["--configure"]:
            return configure()
        if arguments == ["--test"]:
            credentials = load_credentials()
            if credentials is None:
                raise TelegramError("Telegram credentials are not configured")
            send_message(*credentials, "Codex 텔레그램 완료 알림 테스트")
            print("테스트 메시지 전송 완료")
            return 0
        return notify(arguments)
    except (TelegramError, EOFError, KeyboardInterrupt) as error:
        print(f"Telegram notifier error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
