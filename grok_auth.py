from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import config

logger = logging.getLogger(__name__)

AUTH_FILE = Path.home() / ".grok" / "auth.json"
TOKEN_URL = "https://auth.x.ai/oauth2/token"

_mem: dict[str, str] = {}


def _parse_exp(raw: str) -> float:
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _load_file() -> dict:
    if not AUTH_FILE.exists():
        return {}
    data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    entry = next(iter(data.values()))
    return {
        "key": (entry.get("key") or "").strip(),
        "refresh_token": (entry.get("refresh_token") or "").strip(),
        "client_id": (entry.get("oidc_client_id") or "").strip(),
        "expires_at": entry.get("expires_at") or "",
        "_slot": next(iter(data)),
        "_raw": data,
    }


def _current() -> dict:
    if _mem.get("key") or _mem.get("refresh_token"):
        return dict(_mem)
    env_key = os.getenv("GROK_ACCESS_TOKEN", "").strip()
    env_refresh = os.getenv("GROK_REFRESH_TOKEN", "").strip()
    env_client = os.getenv("GROK_CLIENT_ID", "").strip()
    if env_key or env_refresh:
        return {
            "key": env_key,
            "refresh_token": env_refresh,
            "client_id": env_client,
            "expires_at": os.getenv("GROK_EXPIRES_AT", ""),
        }
    return _load_file()


def _save(entry: dict) -> None:
    _mem.update(
        {
            "key": entry.get("key") or "",
            "refresh_token": entry.get("refresh_token") or "",
            "client_id": entry.get("client_id") or "",
            "expires_at": entry.get("expires_at") or "",
        }
    )
    file_state = _load_file()
    if not file_state.get("_raw"):
        return
    slot = file_state["_slot"]
    raw = file_state["_raw"]
    raw[slot]["key"] = entry.get("key") or raw[slot].get("key")
    if entry.get("refresh_token"):
        raw[slot]["refresh_token"] = entry["refresh_token"]
    if entry.get("expires_at"):
        raw[slot]["expires_at"] = entry["expires_at"]
    AUTH_FILE.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    try:
        AUTH_FILE.chmod(0o600)
    except OSError:
        pass


def _refresh(entry: dict) -> dict:
    refresh = entry.get("refresh_token")
    client_id = entry.get("client_id")
    if not refresh or not client_id:
        raise RuntimeError("нет refresh_token/client_id для Grok")
    body = urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": client_id,
        }
    ).encode()
    req = Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    access = payload.get("access_token")
    if not access:
        raise RuntimeError(f"refresh без access_token: {list(payload)}")
    entry["key"] = access
    if payload.get("refresh_token"):
        entry["refresh_token"] = payload["refresh_token"]
    expires_in = int(payload.get("expires_in") or 7200)
    entry["expires_at"] = datetime.fromtimestamp(
        time.time() + expires_in, tz=timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    logger.info("grok token refreshed, exp %s", entry["expires_at"])
    return entry


def grok_session_token() -> str:
    entry = _current()
    token = (entry.get("key") or "").strip()
    exp = _parse_exp(entry.get("expires_at") or "")
    if token and exp - time.time() > 90:
        return token
    if token and not entry.get("refresh_token"):
        return token
    try:
        entry = _refresh(entry)
        _save(entry)
        return (entry.get("key") or "").strip()
    except Exception as exc:
        logger.warning("grok token refresh failed: %s", exc)
        return token


def bearer_token() -> str:
    if config.XAI_API_KEY:
        return config.XAI_API_KEY
    return grok_session_token()


def grok_ready() -> bool:
    return bool(bearer_token())
