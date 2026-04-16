from __future__ import annotations

import time
import socket
from typing import Any, Dict, Tuple

import requests

from config import settings

API_BASE = f"{settings.adspower_host}:{settings.adspower_port}/api/v1"


class AdsPowerError(RuntimeError):
    pass


def _request(path: str, params: Dict[str, Any] | None = None) -> dict:
    resp = requests.get(f"{API_BASE}{path}", params=params or {}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    code = data.get("code")
    if code not in (0, "0"):
        raise AdsPowerError(f"AdsPower API error code={code}, msg={data.get('msg')}, path={path}")
    return data


def _tcp_ready(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def start_browser(profile_id: str, retries: int = 6, wait_seconds: float = 1.0) -> Tuple[str, str]:
    last_error: Exception | None = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            data = _request("/browser/start", params={"user_id": profile_id})
            payload = data.get("data", {})
            ws = str(payload.get("ws", {}).get("puppeteer", "") or "").strip()
            debug_port = str(payload.get("debug_port", "") or "").strip()
            if ws:
                for _ in range(8):
                    try:
                        port_ready = bool(debug_port) and _tcp_ready("127.0.0.1", int(debug_port), timeout=0.5)
                        if check_browser_active(profile_id) and (not debug_port or port_ready):
                            return ws, debug_port
                    except Exception:
                        pass
                    time.sleep(0.5)
                return ws, debug_port
            last_error = AdsPowerError(f"AdsPower ws missing for profile={profile_id}")
        except Exception as exc:
            last_error = exc
        if attempt < retries:
            time.sleep(wait_seconds * attempt)
    raise last_error or AdsPowerError(f"AdsPower start failed for profile={profile_id}")


def stop_browser(profile_id: str):
    _request("/browser/stop", params={"user_id": profile_id})


def get_all_profiles() -> list:
    data = _request("/user/list", params={"page_size": 100})
    return data.get("data", {}).get("list", [])


def check_browser_active(profile_id: str) -> bool:
    data = _request("/browser/active", params={"user_id": profile_id})
    return data.get("data", {}).get("status") == "Active"
