from __future__ import annotations

import json
import random
import sqlite3
import uuid as _uuid
import hashlib
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings

DB_PATH = Path(settings.runtime_db_path)

ACCOUNT_STATUS_NORMAL = "正常"
ACCOUNT_STATUS_ERROR = "异常"
ACCOUNT_STATUS_ALLOWED = {ACCOUNT_STATUS_NORMAL, ACCOUNT_STATUS_ERROR}


TARGET_EXTRA_COLUMNS: Dict[str, str] = {
    "language": "TEXT DEFAULT ''",
    "source": "TEXT DEFAULT ''",
    "tags": "TEXT DEFAULT ''",
    "followers": "INTEGER DEFAULT 0",
    "kol_tier": "TEXT DEFAULT ''",
    "content_type": "TEXT DEFAULT ''",
    "track": "TEXT DEFAULT ''",
    "cooperation": "TEXT DEFAULT ''",
    "chain": "TEXT DEFAULT ''",
    "stage": "TEXT DEFAULT ''",
    "project_type": "TEXT DEFAULT ''",
    "contact_role": "TEXT DEFAULT ''",
    "client_group": "TEXT DEFAULT ''",
    "client_note": "TEXT DEFAULT ''",
    "reply_content": "TEXT DEFAULT ''",
    "display_name": "TEXT DEFAULT ''",
    "nickname": "TEXT DEFAULT ''",
}

LOCAL_ACCOUNT_EXTRA_COLUMNS: Dict[str, str] = {
    "health_score": "INTEGER DEFAULT 100",
    "cooldown_until": "TEXT DEFAULT ''",
    "daily_limit_today": "INTEGER DEFAULT 0",
    "last_action_time": "TEXT DEFAULT ''",
}

TEMPLATE_EXTRA_COLUMNS: Dict[str, str] = {
    "template_type": "TEXT DEFAULT 'first_contact'",
}

CONVERSATION_EXTRA_COLUMNS: Dict[str, str] = {
    "client_group": "TEXT DEFAULT ''",
    "client_note": "TEXT DEFAULT ''",
    "segment_id": "TEXT DEFAULT ''",
    "segment_name": "TEXT DEFAULT ''",
    "project_id": "TEXT DEFAULT ''",
    "project_target_id": "TEXT DEFAULT ''",
    "project_name": "TEXT DEFAULT ''",
    "last_sequence_step": "INTEGER DEFAULT 0",
    "next_sequence_step": "INTEGER DEFAULT 2",
    "next_followup_at": "TEXT DEFAULT ''",
    "reply_analysis": "TEXT DEFAULT ''",
    "extracted_email": "TEXT DEFAULT ''",
    "extracted_telegram": "TEXT DEFAULT ''",
    "extracted_pricing": "TEXT DEFAULT ''",
}

RUNTIME_DEFAULTS: Dict[str, str] = {
    "daily_dm_limit": str(settings.daily_dm_limit),
    "daily_dm_limit_min": str(settings.daily_dm_limit_min),
    "daily_dm_limit_max": str(settings.daily_dm_limit_max),
    "min_interval_sec": str(settings.min_interval_sec),
    "max_interval_sec": str(settings.max_interval_sec),
    "sync_interval_min": str(settings.sync_interval_min),
    "reply_check_interval_min": str(settings.reply_check_interval_min),
    "reply_check_normal_interval_min": str(settings.reply_check_normal_interval_min),
    "reply_check_start_hour": str(settings.reply_check_start_hour),
    "reply_check_end_hour": str(settings.reply_check_end_hour),
    "reply_check_full_interval_min": str(settings.reply_check_full_interval_min),
    "reply_check_full_start_hour": str(settings.reply_check_full_start_hour),
    "reply_check_full_end_hour": str(settings.reply_check_full_end_hour),
    "max_retry_accounts_per_target": str(settings.max_retry_accounts_per_target),
    "followup_days": str(settings.followup_days),
    "cooldown_hours": str(settings.cooldown_hours),
    "business_hours_start": str(settings.business_hours_start),
    "business_hours_end": str(settings.business_hours_end),
    "circuit_breaker_window_min": str(settings.circuit_breaker_window_min),
    "circuit_breaker_threshold": str(settings.circuit_breaker_threshold),
    "feishu_app_id": "",
    "feishu_app_secret": "",
    "feishu_app_token": "",
    "feishu_table_targets": "",
    "feishu_table_accounts": "",
    "feishu_display_name_column": str(settings.feishu_display_name_column),
    "feishu_notify_webhook": "",
    "openai_api_key": str(settings.openai_api_key),
    "openai_model": str(settings.openai_model),
    "twitter_password": str(settings.twitter_password),
}


def _safe_int(value: Any, default: int = 0, minimum: Optional[int] = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    if minimum is not None:
        parsed = max(minimum, parsed)
    return parsed


def _normalize_sequence_step(value: Any) -> int:
    step = _safe_int(value, default=0)
    if step in {1, 2, 3}:
        return step
    return 0


def _sequence_delay_from_row(row: Dict[str, Any], step: int, fallback_days: int) -> int:
    if step == 2:
        return _safe_int(row.get("sequence_step_2_delay_days"), default=fallback_days, minimum=1)
    if step == 3:
        return _safe_int(row.get("sequence_step_3_delay_days"), default=max(fallback_days + 2, fallback_days), minimum=1)
    return 0


def _sequence_enabled_from_row(row: Dict[str, Any], step: int) -> bool:
    if step == 2:
        return bool(_safe_int(row.get("sequence_step_2_enabled", row.get("followup_enabled", 1)), default=1))
    if step == 3:
        return bool(_safe_int(row.get("sequence_step_3_enabled", row.get("followup_enabled", 1)), default=1))
    return False


def _resolve_next_sequence_state(
    sent_step: int,
    sequence_step_2_enabled: bool = True,
    sequence_step_3_enabled: bool = True,
    sequence_step_2_delay_days: int = 3,
    sequence_step_3_delay_days: int = 5,
) -> tuple[int, str]:
    now = datetime.now()
    if int(sent_step) <= 1:
        if sequence_step_2_enabled:
            next_step = 2
            delay_days = max(1, int(sequence_step_2_delay_days or 1))
            return next_step, (now + timedelta(days=delay_days)).isoformat(timespec="seconds")
        if sequence_step_3_enabled:
            next_step = 3
            delay_days = max(1, int(sequence_step_3_delay_days or 1))
            return next_step, (now + timedelta(days=delay_days)).isoformat(timespec="seconds")
        return 0, ""
    if int(sent_step) == 2 and sequence_step_3_enabled:
        delay_days = max(1, int(sequence_step_3_delay_days or 1))
        return 3, (now + timedelta(days=delay_days)).isoformat(timespec="seconds")
    return 0, ""


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r["name"]) for r in rows}


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, col_def: str) -> None:
    if name in _table_columns(conn, table):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_def}")


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                level TEXT,
                account TEXT,
                target TEXT,
                status TEXT,
                message TEXT,
                meta_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS templates (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                description TEXT,
                active INTEGER DEFAULT 1,
                template_type TEXT DEFAULT 'first_contact',
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS local_targets (
                id TEXT PRIMARY KEY,
                twitter_username TEXT NOT NULL,
                type TEXT DEFAULT '',
                project_name TEXT DEFAULT '',
                priority TEXT DEFAULT '中',
                status TEXT DEFAULT '待发送',
                sent_by TEXT DEFAULT '',
                sent_time TEXT,
                fail_reason TEXT DEFAULT '',
                note TEXT DEFAULT '',
                language TEXT DEFAULT '',
                source TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                followers INTEGER DEFAULT 0,
                kol_tier TEXT DEFAULT '',
                content_type TEXT DEFAULT '',
                track TEXT DEFAULT '',
                cooperation TEXT DEFAULT '',
                chain TEXT DEFAULT '',
                stage TEXT DEFAULT '',
                project_type TEXT DEFAULT '',
                contact_role TEXT DEFAULT '',
                client_group TEXT DEFAULT '',
                client_note TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS local_accounts (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                twitter_username TEXT DEFAULT '',
                status TEXT DEFAULT '正常',
                today_sent INTEGER DEFAULT 0,
                total_sent INTEGER DEFAULT 0,
                bound_ip TEXT DEFAULT '',
                health_score INTEGER DEFAULT 100,
                cooldown_until TEXT DEFAULT '',
                daily_limit_today INTEGER DEFAULT 0,
                last_action_time TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS segments (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS segment_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                segment_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                target_source TEXT DEFAULT 'local',
                twitter_username TEXT,
                added_at TEXT,
                UNIQUE(segment_id, target_id),
                FOREIGN KEY(segment_id) REFERENCES segments(id) ON DELETE CASCADE
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS account_runtime (
                account_key TEXT PRIMARY KEY,
                health_score INTEGER DEFAULT 100,
                cooldown_until TEXT DEFAULT '',
                daily_limit_today INTEGER DEFAULT 0,
                last_action_time TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                target_id TEXT NOT NULL,
                target_source TEXT DEFAULT 'local',
                target_username TEXT NOT NULL,
                account_key TEXT NOT NULL,
                account_profile_id TEXT DEFAULT '',
                account_username TEXT DEFAULT '',
                last_contact_time TEXT DEFAULT '',
                contact_count INTEGER DEFAULT 0,
                has_reply INTEGER DEFAULT 0,
                reply_at TEXT DEFAULT '',
                last_reply_preview TEXT DEFAULT '',
                last_message_preview TEXT DEFAULT '',
                last_message_direction TEXT DEFAULT 'outbound',
                last_box TEXT DEFAULT 'inbox',
                last_checked_at TEXT DEFAULT '',
                notify_sent_at TEXT DEFAULT '',
                client_group TEXT DEFAULT '',
                client_note TEXT DEFAULT '',
                segment_id TEXT DEFAULT '',
                segment_name TEXT DEFAULT '',
                project_id TEXT DEFAULT '',
                project_target_id TEXT DEFAULT '',
                project_name TEXT DEFAULT '',
                last_sequence_step INTEGER DEFAULT 0,
                next_sequence_step INTEGER DEFAULT 2,
                next_followup_at TEXT DEFAULT '',
                status TEXT DEFAULT 'contacted',
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(target_source, target_id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS message_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                message_key TEXT NOT NULL,
                direction TEXT DEFAULT '',
                content TEXT DEFAULT '',
                box TEXT DEFAULT 'inbox',
                detected_at TEXT DEFAULT '',
                notified_at TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(conversation_id, message_key)
            )
            """
        )

        # migrate old runtime DB safely
        for col_name, col_def in TARGET_EXTRA_COLUMNS.items():
            _ensure_column(conn, "local_targets", col_name, col_def)
        for col_name, col_def in LOCAL_ACCOUNT_EXTRA_COLUMNS.items():
            _ensure_column(conn, "local_accounts", col_name, col_def)
        for col_name, col_def in TEMPLATE_EXTRA_COLUMNS.items():
            _ensure_column(conn, "templates", col_name, col_def)
        for col_name, col_def in CONVERSATION_EXTRA_COLUMNS.items():
            _ensure_column(conn, "conversations", col_name, col_def)

        # account status migration: keep only 正常 / 异常
        conn.execute(
            """
            UPDATE local_accounts
            SET status = ?
            WHERE status IS NULL OR TRIM(status) = ''
            """,
            (ACCOUNT_STATUS_NORMAL,),
        )
        conn.execute(
            """
            UPDATE local_accounts
            SET status = ?
            WHERE status NOT IN (?, ?)
            """,
            (ACCOUNT_STATUS_ERROR, ACCOUNT_STATUS_NORMAL, ACCOUNT_STATUS_ERROR),
        )

        for k, default_val in RUNTIME_DEFAULTS.items():
            conn.execute(
                """
                INSERT INTO runtime_config (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO NOTHING
                """,
                (k, default_val),
            )


def add_log(
    level: str,
    account: str,
    target: str,
    status: str,
    message: str,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO logs (timestamp, level, account, target, status, message, meta_json) VALUES (?,?,?,?,?,?,?)",
            (
                datetime.now().isoformat(timespec="seconds"),
                level,
                account,
                target,
                status,
                message,
                json.dumps(meta or {}, ensure_ascii=False),
            ),
        )


def get_logs(limit: int = 200) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        try:
            item["meta"] = json.loads(item.get("meta_json") or "{}")
        except Exception:
            item["meta"] = {}
        out.append(item)
    return out


def clear_logs(statuses: Optional[List[str]] = None, older_than_days: Optional[int] = None) -> int:
    status_list = [str(x).strip() for x in (statuses or []) if str(x).strip()]
    cutoff = None
    if older_than_days is not None:
        try:
            days = max(1, int(older_than_days))
            cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        except Exception:
            cutoff = None
    with get_conn() as conn:
        where_parts: List[str] = []
        params: List[Any] = []
        if status_list:
            marks = ",".join(["?"] * len(status_list))
            where_parts.append(f"status IN ({marks})")
            params.extend(status_list)
        if cutoff:
            where_parts.append("timestamp < ?")
            params.append(cutoff)

        if where_parts:
            where_sql = " WHERE " + " AND ".join(where_parts)
            count = conn.execute(
                f"SELECT COUNT(*) FROM logs{where_sql}",
                tuple(params),
            ).fetchone()[0]
            conn.execute(
                f"DELETE FROM logs{where_sql}",
                tuple(params),
            )
            return int(count or 0)

        count = conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
        conn.execute("DELETE FROM logs")
        return int(count or 0)


def get_today_stats() -> Dict[str, int]:
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        sent = conn.execute(
            "SELECT COUNT(*) FROM logs WHERE timestamp LIKE ? AND status IN ('sent','followup_sent')",
            (f"{today}%",),
        ).fetchone()[0]
        skipped = conn.execute(
            "SELECT COUNT(*) FROM logs WHERE timestamp LIKE ? AND status IN ('skipped','cannot_dm','target_not_found','blocked_verification')",
            (f"{today}%",),
        ).fetchone()[0]
        errors = conn.execute(
            "SELECT COUNT(*) FROM logs WHERE timestamp LIKE ? AND status IN ('error','captcha')",
            (f"{today}%",),
        ).fetchone()[0]
        replies = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE reply_at LIKE ?",
            (f"{today}%",),
        ).fetchone()[0]
    return {"sent": int(sent), "skipped": int(skipped), "errors": int(errors), "replies": int(replies or 0)}


def get_templates() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, content, description, active, template_type, created_at, updated_at FROM templates ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_template(
    template_id: str,
    content: str,
    description: str = "",
    active: int = 1,
    template_type: str = "first_contact",
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO templates (id, content, description, active, template_type, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                content=excluded.content,
                description=excluded.description,
                active=excluded.active,
                template_type=excluded.template_type,
                updated_at=excluded.updated_at
            """,
            (template_id, content, description, int(active), template_type, now, now),
        )


def delete_template(template_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))


def _new_local_id() -> str:
    return "local_" + _uuid.uuid4().hex[:12]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def normalize_account_status(value: Any) -> str:
    return ACCOUNT_STATUS_NORMAL if str(value or "").strip() == ACCOUNT_STATUS_NORMAL else ACCOUNT_STATUS_ERROR


def _normalized_target_payload(data: dict) -> dict:
    return {
        "twitter_username": str(data.get("twitter_username", "")).replace("@", "").strip(),
        "type": str(data.get("type", "") or ""),
        "project_name": str(data.get("project_name", "") or ""),
        "priority": str(data.get("priority", "中") or "中"),
        "status": str(data.get("status", "待发送") or "待发送"),
        "sent_by": str(data.get("sent_by", "") or ""),
        "sent_time": data.get("sent_time"),
        "fail_reason": str(data.get("fail_reason", "") or ""),
        "note": str(data.get("note", "") or ""),
        "language": str(data.get("language", "") or ""),
        "source": str(data.get("source", "") or ""),
        "tags": str(data.get("tags", "") or ""),
        "followers": _safe_int(data.get("followers", 0), 0),
        "kol_tier": str(data.get("kol_tier", "") or ""),
        "content_type": str(data.get("content_type", "") or ""),
        "track": str(data.get("track", "") or ""),
        "cooperation": str(data.get("cooperation", "") or ""),
        "chain": str(data.get("chain", "") or ""),
        "stage": str(data.get("stage", "") or ""),
        "project_type": str(data.get("project_type", "") or ""),
        "contact_role": str(data.get("contact_role", "") or ""),
        "client_group": str(data.get("client_group", "") or ""),
        "client_note": str(data.get("client_note", "") or ""),
        "reply_content": str(data.get("reply_content", "") or ""),
    }


def create_local_target(data: dict) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    tid = _new_local_id()
    payload = _normalized_target_payload(data)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO local_targets (
                id, twitter_username, type, project_name, priority, status,
                sent_by, sent_time, fail_reason, note,
                language, source, tags, followers, kol_tier, content_type,
                track, cooperation, chain, stage, project_type, contact_role,
                client_group, client_note, created_at, updated_at
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                tid,
                payload["twitter_username"],
                payload["type"],
                payload["project_name"],
                payload["priority"],
                "待发送",
                "",
                None,
                "",
                payload["note"],
                payload["language"],
                payload["source"],
                payload["tags"],
                payload["followers"],
                payload["kol_tier"],
                payload["content_type"],
                payload["track"],
                payload["cooperation"],
                payload["chain"],
                payload["stage"],
                payload["project_type"],
                payload["contact_role"],
                payload["client_group"],
                payload["client_note"],
                now,
                now,
            ),
        )
    return tid


def import_local_targets(rows: List[Dict[str, Any]]) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    count = 0
    with get_conn() as conn:
        for row in rows:
            payload = _normalized_target_payload(row)
            if not payload["twitter_username"]:
                continue
            tid = _new_local_id()
            conn.execute(
                """
                INSERT INTO local_targets (
                    id, twitter_username, type, project_name, priority, status,
                    sent_by, sent_time, fail_reason, note,
                    language, source, tags, followers, kol_tier, content_type,
                    track, cooperation, chain, stage, project_type, contact_role,
                    client_group, client_note, created_at, updated_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    tid,
                    payload["twitter_username"],
                    payload["type"],
                    payload["project_name"],
                    payload["priority"],
                    "待发送",
                    "",
                    None,
                    "",
                    payload["note"],
                    payload["language"],
                    payload["source"],
                    payload["tags"],
                    payload["followers"],
                    payload["kol_tier"],
                    payload["content_type"],
                    payload["track"],
                    payload["cooperation"],
                    payload["chain"],
                    payload["stage"],
                    payload["project_type"],
                    payload["contact_role"],
                    payload["client_group"],
                    payload["client_note"],
                    now,
                    now,
                ),
            )
            count += 1
    return count


def _split_multi(v: Optional[str]) -> List[str]:
    if not v:
        return []
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return []


def get_local_targets(
    status: Optional[str] = None,
    type_: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = None,
    language: Optional[str] = None,
    source: Optional[str] = None,
    tags: Optional[str] = None,
    kol_tier: Optional[str] = None,
    content_type: Optional[str] = None,
    track: Optional[str] = None,
    cooperation: Optional[str] = None,
    followers_min: Optional[int] = None,
    followers_max: Optional[int] = None,
    chain: Optional[str] = None,
    stage: Optional[str] = None,
    project_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM local_targets WHERE 1=1"
    params: list[Any] = []

    if status:
        sql += " AND status = ?"
        params.append(status)
    if type_:
        sql += " AND type = ?"
        params.append(type_)
    if priority:
        sql += " AND priority = ?"
        params.append(priority)
    if search:
        sql += " AND (twitter_username LIKE ? OR project_name LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    languages = _split_multi(language)
    if languages:
        sql += " AND (" + " OR ".join("language = ?" for _ in languages) + ")"
        params.extend(languages)

    sources = _split_multi(source)
    if sources:
        sql += " AND (" + " OR ".join("source = ?" for _ in sources) + ")"
        params.extend(sources)

    tag_values = _split_multi(tags)
    if tag_values:
        sql += " AND (" + " OR ".join("tags LIKE ?" for _ in tag_values) + ")"
        params.extend([f"%{x}%" for x in tag_values])

    if kol_tier:
        sql += " AND kol_tier = ?"
        params.append(kol_tier)
    if content_type:
        sql += " AND content_type = ?"
        params.append(content_type)
    if track:
        sql += " AND track = ?"
        params.append(track)
    if cooperation:
        sql += " AND cooperation = ?"
        params.append(cooperation)
    if followers_min is not None:
        sql += " AND followers >= ?"
        params.append(int(followers_min))
    if followers_max is not None:
        sql += " AND followers <= ?"
        params.append(int(followers_max))
    if chain:
        sql += " AND chain = ?"
        params.append(chain)
    if stage:
        sql += " AND stage = ?"
        params.append(stage)
    if project_type:
        sql += " AND project_type = ?"
        params.append(project_type)

    sql += " ORDER BY CASE priority WHEN '高' THEN 0 WHEN '中' THEN 1 ELSE 2 END, created_at"
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_local_pending_targets() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM local_targets WHERE status = '待发送' ORDER BY CASE priority WHEN '高' THEN 0 WHEN '中' THEN 1 ELSE 2 END, created_at"
        ).fetchall()
    return [dict(r) for r in rows]


def get_local_targets_by_ids(target_ids: List[str]) -> List[Dict[str, Any]]:
    ids = [x for x in target_ids if x]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    with get_conn() as conn:
        rows = conn.execute(f"SELECT * FROM local_targets WHERE id IN ({placeholders})", ids).fetchall()
    return [dict(r) for r in rows]


def update_local_target(target_id: str, fields: dict) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    allowed = {
        "status",
        "sent_by",
        "sent_time",
        "fail_reason",
        "note",
        "priority",
        "type",
        "project_name",
        "language",
        "source",
        "tags",
        "followers",
        "kol_tier",
        "content_type",
        "track",
        "cooperation",
        "chain",
        "stage",
        "project_type",
        "contact_role",
        "client_group",
        "client_note",
        "reply_content",
        "twitter_username",
        "display_name",
        "nickname",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = now
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [target_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE local_targets SET {set_clause} WHERE id = ?", vals)


def delete_local_target(target_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM local_targets WHERE id = ?", (target_id,))


def create_local_account(data: dict) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    aid = _new_local_id()
    daily_limit_today = _safe_int(data.get("daily_limit_today", 0), 0)
    if daily_limit_today <= 0:
        low = max(1, _safe_int(get_runtime_config().get("daily_dm_limit_min", settings.daily_dm_limit_min), settings.daily_dm_limit_min))
        high = max(low, _safe_int(get_runtime_config().get("daily_dm_limit_max", settings.daily_dm_limit_max), settings.daily_dm_limit_max))
        daily_limit_today = random.randint(low, high)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO local_accounts (id, profile_id, twitter_username, status,
                today_sent, total_sent, bound_ip, health_score, cooldown_until,
                daily_limit_today, last_action_time, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                aid,
                str(data.get("profile_id", "")).strip(),
                str(data.get("twitter_username", "")).replace("@", "").strip(),
                normalize_account_status(data.get("status", ACCOUNT_STATUS_NORMAL)),
                0,
                0,
                str(data.get("bound_ip", "") or ""),
                _safe_int(data.get("health_score", 100), 100),
                str(data.get("cooldown_until", "") or ""),
                daily_limit_today,
                str(data.get("last_action_time", "") or ""),
                now,
                now,
            ),
        )
    return aid


def delete_local_account(account_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM local_accounts WHERE id = ?", (account_id,))


def get_local_accounts() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM local_accounts ORDER BY created_at").fetchall()
    out = [dict(r) for r in rows]
    for item in out:
        item["status"] = normalize_account_status(item.get("status"))
    return out


def update_local_account(account_id: str, fields: dict) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    allowed = {
        "status",
        "today_sent",
        "total_sent",
        "bound_ip",
        "twitter_username",
        "profile_id",
        "health_score",
        "cooldown_until",
        "daily_limit_today",
        "last_action_time",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    if "status" in updates:
        updates["status"] = normalize_account_status(updates.get("status"))
    if "health_score" in updates:
        updates["health_score"] = max(0, min(100, _safe_int(updates.get("health_score"), 100)))
    if "daily_limit_today" in updates:
        updates["daily_limit_today"] = max(0, _safe_int(updates.get("daily_limit_today"), 0))
    updates["updated_at"] = now
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [account_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE local_accounts SET {set_clause} WHERE id = ?", vals)


def get_local_accounts_by_ids(account_ids: List[str]) -> List[Dict[str, Any]]:
    ids = [x for x in account_ids if x]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    with get_conn() as conn:
        rows = conn.execute(f"SELECT * FROM local_accounts WHERE id IN ({placeholders})", ids).fetchall()
    return [dict(r) for r in rows]


def get_account_runtime_map(account_keys: List[str]) -> Dict[str, Dict[str, Any]]:
    keys = [str(x).strip() for x in account_keys if str(x).strip()]
    if not keys:
        return {}
    placeholders = ",".join("?" for _ in keys)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM account_runtime WHERE account_key IN ({placeholders})",
            keys,
        ).fetchall()
    return {str(r["account_key"]): dict(r) for r in rows}


def upsert_account_runtime(account_key: str, fields: Dict[str, Any]) -> None:
    key = str(account_key or "").strip()
    if not key:
        return
    now = datetime.now().isoformat(timespec="seconds")
    current = get_account_runtime_map([key]).get(key, {})
    payload = {
        "health_score": max(0, min(100, _safe_int(fields.get("health_score", current.get("health_score", 100)), 100))),
        "cooldown_until": str(fields.get("cooldown_until", current.get("cooldown_until", "")) or ""),
        "daily_limit_today": max(0, _safe_int(fields.get("daily_limit_today", current.get("daily_limit_today", 0)), 0)),
        "last_action_time": str(fields.get("last_action_time", current.get("last_action_time", "")) or ""),
    }
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO account_runtime (
                account_key, health_score, cooldown_until, daily_limit_today,
                last_action_time, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_key) DO UPDATE SET
                health_score=excluded.health_score,
                cooldown_until=excluded.cooldown_until,
                daily_limit_today=excluded.daily_limit_today,
                last_action_time=excluded.last_action_time,
                updated_at=excluded.updated_at
            """,
            (
                key,
                payload["health_score"],
                payload["cooldown_until"],
                payload["daily_limit_today"],
                payload["last_action_time"],
                current.get("created_at", now) or now,
                now,
            ),
        )


def reset_local_account_daily_stats(daily_limits: Dict[str, int]) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        rows = conn.execute("SELECT id FROM local_accounts").fetchall()
        for row in rows:
            account_id = str(row["id"])
            conn.execute(
                """
                UPDATE local_accounts
                SET today_sent = 0, daily_limit_today = ?, updated_at = ?
                WHERE id = ?
                """,
                (max(0, _safe_int(daily_limits.get(account_id, 0), 0)), now, account_id),
            )


def reset_account_runtime_daily(daily_limits: Dict[str, int]) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        for account_key, daily_limit in daily_limits.items():
            key = str(account_key or "").strip()
            if not key:
                continue
            conn.execute(
                """
                INSERT INTO account_runtime (
                    account_key, health_score, cooldown_until, daily_limit_today,
                    last_action_time, created_at, updated_at
                )
                VALUES (?, 100, '', ?, '', ?, ?)
                ON CONFLICT(account_key) DO UPDATE SET
                    daily_limit_today=excluded.daily_limit_today,
                    updated_at=excluded.updated_at
                """,
                (key, max(0, _safe_int(daily_limit, 0)), now, now),
            )


CONFIG_KEYS = set(RUNTIME_DEFAULTS.keys())


def get_runtime_config() -> Dict[str, Any]:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM runtime_config").fetchall()
    return {r["key"]: r["value"] for r in rows}


def set_runtime_config(key: str, value: str) -> None:
    if key not in CONFIG_KEYS:
        raise ValueError(f"Unknown config key: {key}")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO runtime_config (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def set_runtime_configs(data: Dict[str, Any]) -> None:
    for key, value in data.items():
        set_runtime_config(key, str(value))


def get_conversation_by_target(target_id: str, target_source: str = "local") -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM conversations
            WHERE target_id = ? AND target_source = ?
            """,
            (str(target_id or "").strip(), str(target_source or "local")),
        ).fetchone()
    return dict(row) if row else None


def upsert_conversation_for_send(
    target: Dict[str, Any],
    account: Dict[str, Any],
    message_preview: str,
    sequence_step: int = 1,
    next_sequence_step: Optional[int] = None,
    next_followup_at: Optional[str] = None,
    segment_id: str = "",
    segment_name: str = "",
    client_group: str = "",
    project_id: str = "",
    project_target_id: str = "",
    project_name: str = "",
) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    target_id = str(target.get("record_id") or target.get("id") or "").strip()
    target_source = str(target.get("_source") or target.get("target_source") or "local")
    target_username = str(target.get("twitter_username") or "").replace("@", "").strip()
    account_key = str(account.get("record_id") or account.get("id") or account.get("profile_id") or "").strip()
    account_profile_id = str(account.get("profile_id") or "").strip()
    account_username = str(account.get("twitter_username") or "").replace("@", "").strip()
    # Prefer explicitly passed client_group (from run context) over target's own field
    client_group = str(client_group or target.get("client_group") or "").strip()
    client_note = str(target.get("client_note") or "").strip()
    seg_id = str(segment_id or target.get("segment_id") or "").strip()
    seg_name = str(segment_name or target.get("segment_name") or "").strip()
    project_id_value = str(project_id or target.get("project_id") or "").strip()
    project_target_value = str(project_target_id or target.get("project_target_id") or "").strip()
    project_name_value = str(project_name or target.get("project_name") or "").strip()
    preview = str(message_preview or "").strip()[:300]
    existing = get_conversation_by_target(target_id, target_source) if target_id else None
    conversation_id = str(existing.get("id")) if existing else _new_conversation_id()
    contact_count = int(existing.get("contact_count", 0) or 0) + 1 if existing else 1
    has_reply = int(existing.get("has_reply", 0) or 0) if existing else 0
    reply_at = str(existing.get("reply_at", "") or "") if existing else ""
    last_reply_preview = str(existing.get("last_reply_preview", "") or "") if existing else ""
    notify_sent_at = str(existing.get("notify_sent_at", "") or "") if existing else ""
    existing_status = str(existing.get("status", "") or "") if existing else ""
    # Preserve segment attribution if already set and caller didn't specify a new one
    if existing and not seg_id:
        seg_id = str(existing.get("segment_id") or "").strip()
        seg_name = str(existing.get("segment_name") or "").strip()
    if existing and not project_id_value:
        project_id_value = str(existing.get("project_id") or "").strip()
        project_target_value = str(existing.get("project_target_id") or "").strip()
        project_name_value = str(existing.get("project_name") or "").strip()
    current_sequence_step = _normalize_sequence_step(sequence_step or (existing.get("last_sequence_step") if existing else 0))
    current_next_step = _normalize_sequence_step(next_sequence_step)
    current_next_followup_at = str(next_followup_at or "").strip()
    if not current_next_step and existing and not current_next_followup_at:
        current_next_step = _normalize_sequence_step(existing.get("next_sequence_step"))
        current_next_followup_at = str(existing.get("next_followup_at") or "").strip()
    if existing_status in {"manual_takeover", "completed"}:
        status = existing_status
    else:
        status = "replied" if has_reply else "contacted"

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO conversations (
                id, target_id, target_source, target_username, account_key,
                account_profile_id, account_username, last_contact_time, contact_count,
                has_reply, reply_at, last_reply_preview, last_message_preview,
                last_message_direction, last_box, last_checked_at, notify_sent_at,
                client_group, client_note, segment_id, segment_name,
                project_id, project_target_id, project_name,
                last_sequence_step, next_sequence_step, next_followup_at,
                status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(target_source, target_id) DO UPDATE SET
                target_username=excluded.target_username,
                account_key=excluded.account_key,
                account_profile_id=excluded.account_profile_id,
                account_username=excluded.account_username,
                last_contact_time=excluded.last_contact_time,
                contact_count=excluded.contact_count,
                last_message_preview=excluded.last_message_preview,
                last_message_direction=excluded.last_message_direction,
                last_box=excluded.last_box,
                last_checked_at=excluded.last_checked_at,
                client_group=CASE WHEN excluded.client_group != '' THEN excluded.client_group ELSE conversations.client_group END,
                client_note=excluded.client_note,
                segment_id=CASE WHEN excluded.segment_id != '' THEN excluded.segment_id ELSE conversations.segment_id END,
                segment_name=CASE WHEN excluded.segment_name != '' THEN excluded.segment_name ELSE conversations.segment_name END,
                project_id=CASE WHEN excluded.project_id != '' THEN excluded.project_id ELSE conversations.project_id END,
                project_target_id=CASE WHEN excluded.project_target_id != '' THEN excluded.project_target_id ELSE conversations.project_target_id END,
                project_name=CASE WHEN excluded.project_name != '' THEN excluded.project_name ELSE conversations.project_name END,
                last_sequence_step=CASE WHEN excluded.last_sequence_step > 0 THEN excluded.last_sequence_step ELSE conversations.last_sequence_step END,
                next_sequence_step=excluded.next_sequence_step,
                next_followup_at=excluded.next_followup_at,
                status=excluded.status,
                updated_at=excluded.updated_at
            """,
            (
                conversation_id,
                target_id,
                target_source,
                target_username,
                account_key,
                account_profile_id,
                account_username,
                now,
                contact_count,
                has_reply,
                reply_at,
                last_reply_preview,
                preview,
                "outbound",
                "inbox",
                now,
                notify_sent_at,
                client_group,
                client_note,
                seg_id,
                seg_name,
                project_id_value,
                project_target_value,
                project_name_value,
                current_sequence_step,
                current_next_step,
                current_next_followup_at,
                status,
                existing.get("created_at", now) if existing else now,
                now,
            ),
        )
    return conversation_id


def list_conversations(
    has_reply: Optional[bool] = None,
    status: Optional[str] = None,
    account_key: Optional[str] = None,
    search: Optional[str] = None,
    segment_id: Optional[str] = None,
    client_group: Optional[str] = None,
    project_id: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM conversations WHERE 1=1"
    params: List[Any] = []
    if has_reply is not None:
        sql += " AND has_reply = ?"
        params.append(1 if has_reply else 0)
    if status:
        sql += " AND status = ?"
        params.append(status)
    if account_key:
        sql += " AND account_key = ?"
        params.append(str(account_key))
    if segment_id:
        sql += " AND segment_id = ?"
        params.append(str(segment_id))
    if client_group:
        sql += " AND client_group = ?"
        params.append(str(client_group))
    if project_id:
        sql += " AND project_id = ?"
        params.append(str(project_id))
    if search:
        sql += " AND (target_username LIKE ? OR account_username LIKE ? OR account_profile_id LIKE ? OR segment_name LIKE ? OR client_group LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(max(1, int(limit or 200)))
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_conversation_counts_by_client_group() -> List[Dict[str, Any]]:
    """Return per-client_group conversation and reply counts."""
    sql = """
        SELECT
            client_group,
            COUNT(*) AS total,
            SUM(has_reply) AS replied,
            SUM(CASE WHEN status = 'manual_takeover' THEN 1 ELSE 0 END) AS manual_takeover,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed
        FROM conversations
        WHERE client_group != ''
        GROUP BY client_group
        ORDER BY total DESC
    """
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def get_conversation_counts_by_segment() -> List[Dict[str, Any]]:
    """Return per-segment conversation and reply counts."""
    sql = """
        SELECT
            segment_id,
            segment_name,
            COUNT(*) AS total,
            SUM(has_reply) AS replied,
            SUM(CASE WHEN status = 'manual_takeover' THEN 1 ELSE 0 END) AS manual_takeover,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed
        FROM conversations
        WHERE segment_id != ''
        GROUP BY segment_id
        ORDER BY total DESC
    """
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    return dict(row) if row else None


def update_conversation(conversation_id: str, fields: Dict[str, Any]) -> None:
    allowed = {
        "target_username",
        "account_key",
        "account_profile_id",
        "account_username",
        "last_contact_time",
        "contact_count",
        "has_reply",
        "reply_at",
        "last_reply_preview",
        "last_message_preview",
        "last_message_direction",
        "last_box",
        "last_checked_at",
        "notify_sent_at",
        "client_group",
        "client_note",
        "segment_id",
        "segment_name",
        "project_id",
        "project_target_id",
        "project_name",
        "last_sequence_step",
        "next_sequence_step",
        "next_followup_at",
        "status",
        "reply_analysis",
        "extracted_email",
        "extracted_telegram",
        "extracted_pricing",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = datetime.now().isoformat(timespec="seconds")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [conversation_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE conversations SET {set_clause} WHERE id = ?", vals)


def mark_conversation_reply(
    conversation_id: str,
    reply_preview: str,
    reply_at: Optional[str] = None,
    last_box: str = "inbox",
) -> None:
    current = get_conversation(conversation_id) or {}
    current_reply_at = reply_at or datetime.now().isoformat(timespec="seconds")
    next_status = str(current.get("status", "") or "")
    if next_status not in {"manual_takeover", "completed"}:
        next_status = "replied"
    update_conversation(
        conversation_id,
        {
            "has_reply": 1,
            "reply_at": current_reply_at,
            "last_reply_preview": str(reply_preview or "")[:500],
            "last_message_preview": str(reply_preview or "")[:500],
            "last_message_direction": "inbound",
            "last_box": last_box,
            "last_checked_at": current_reply_at,
            "notify_sent_at": "",
            "next_sequence_step": 0,
            "next_followup_at": "",
            "status": next_status or "replied",
        },
    )


def mark_conversation_checked(conversation_id: str, last_box: str = "inbox") -> None:
    update_conversation(
        conversation_id,
        {
            "last_checked_at": datetime.now().isoformat(timespec="seconds"),
            "last_box": last_box,
        },
    )


def mark_conversation_notified(conversation_id: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    update_conversation(
        conversation_id,
        {"notify_sent_at": now},
    )
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE message_events
            SET notified_at = ?, updated_at = ?
            WHERE conversation_id = ?
              AND direction = 'inbound'
              AND (notified_at IS NULL OR notified_at = '')
            """,
            (now, now, conversation_id),
        )


def get_reply_pending_notifications(limit: int = 50) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM conversations
            WHERE has_reply = 1
              AND (notify_sent_at IS NULL OR notify_sent_at = '')
            ORDER BY reply_at DESC
            LIMIT ?
            """,
            (max(1, int(limit or 50)),),
        ).fetchall()
    return [dict(r) for r in rows]


def _message_event_key(conversation_id: str, message_key: str, direction: str, content: str) -> str:
    raw = str(message_key or "").strip()
    if raw:
        return raw[:160]
    digest = hashlib.sha1(f"{conversation_id}|{direction}|{content}".encode("utf-8", errors="ignore")).hexdigest()
    return f"synthetic_{digest[:32]}"


def record_message_events(
    conversation_id: str,
    events: List[Dict[str, Any]],
    last_box: str = "inbox",
) -> List[Dict[str, Any]]:
    if not conversation_id or not events:
        return []

    now = datetime.now().isoformat(timespec="seconds")
    inserted: List[Dict[str, Any]] = []
    cleaned: List[Dict[str, Any]] = []

    with get_conn() as conn:
        for item in events:
            direction = "inbound" if str(item.get("direction") or "").strip() == "inbound" else "outbound"
            content = str(item.get("content") or "").strip()
            message_key = _message_event_key(conversation_id, str(item.get("message_key") or ""), direction, content)
            box = str(item.get("box") or last_box or "inbox")
            payload = {
                "conversation_id": conversation_id,
                "message_key": message_key,
                "direction": direction,
                "content": content[:2000],
                "box": box,
                "detected_at": str(item.get("detected_at") or now),
            }
            cleaned.append(payload)
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO message_events (
                    conversation_id, message_key, direction, content, box,
                    detected_at, notified_at, created_at, updated_at
                )
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    payload["conversation_id"],
                    payload["message_key"],
                    payload["direction"],
                    payload["content"],
                    payload["box"],
                    payload["detected_at"],
                    "",
                    now,
                    now,
                ),
            )
            if int(cur.rowcount or 0) > 0:
                inserted.append(payload)

    latest = cleaned[-1] if cleaned else None
    if latest:
        update_conversation(
            conversation_id,
            {
                "last_message_preview": str(latest.get("content") or "")[:500],
                "last_message_direction": str(latest.get("direction") or "outbound"),
                "last_box": str(latest.get("box") or last_box or "inbox"),
                "last_checked_at": now,
            },
        )
    return inserted


def list_message_events(
    conversation_id: str,
    direction: Optional[str] = None,
    only_unnotified: bool = False,
    limit: int = 200,
    ascending: bool = True,
) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM message_events WHERE conversation_id = ?"
    params: List[Any] = [conversation_id]
    if direction:
        sql += " AND direction = ?"
        params.append(str(direction))
    if only_unnotified:
        sql += " AND (notified_at IS NULL OR notified_at = '')"
    order = "ASC" if ascending else "DESC"
    sql += f" ORDER BY id {order} LIMIT ?"
    params.append(max(1, int(limit or 200)))
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_conversation_counts() -> Dict[str, int]:
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM conversations").fetchone()["c"]
        replied = conn.execute("SELECT COUNT(*) AS c FROM conversations WHERE has_reply = 1").fetchone()["c"]
        contacted = conn.execute(
            "SELECT COUNT(*) AS c FROM conversations WHERE status = 'contacted'"
        ).fetchone()["c"]
        manual_takeover = conn.execute(
            "SELECT COUNT(*) AS c FROM conversations WHERE status = 'manual_takeover'"
        ).fetchone()["c"]
        completed = conn.execute(
            "SELECT COUNT(*) AS c FROM conversations WHERE status = 'completed'"
        ).fetchone()["c"]
        replied_today = conn.execute(
            "SELECT COUNT(*) AS c FROM conversations WHERE reply_at LIKE ?",
            (f"{today}%",),
        ).fetchone()["c"]
    return {
        "total": int(total or 0),
        "contacted": int(contacted or 0),
        "replied": int(replied or 0),
        "manual_takeover": int(manual_takeover or 0),
        "completed": int(completed or 0),
        "replied_today": int(replied_today or 0),
    }


def get_followup_candidates(followup_days: int, limit: int = 100) -> List[Dict[str, Any]]:
    fallback_days = max(1, int(followup_days or 1))
    now = datetime.now()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                conversations.*,
                projects.followup_enabled,
                projects.sequence_step_2_enabled,
                projects.sequence_step_3_enabled,
                projects.sequence_step_2_delay_days,
                projects.sequence_step_3_delay_days
            FROM conversations
            LEFT JOIN projects ON projects.id = conversations.project_id
            WHERE conversations.has_reply = 0
              AND conversations.status = 'contacted'
              AND conversations.last_contact_time != ''
            ORDER BY last_contact_time ASC
            LIMIT ?
            """,
            (max(1, int(limit or 100)) * 4,),
        ).fetchall()
    items: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        contact_count = _safe_int(item.get("contact_count"), default=0)
        next_step = _normalize_sequence_step(item.get("next_sequence_step"))
        if next_step <= 0:
            if contact_count <= 1:
                next_step = 2
            elif contact_count == 2:
                next_step = 3
            else:
                next_step = 0
        if next_step <= 0:
            continue
        if not _sequence_enabled_from_row(item, next_step):
            continue
        due_at = str(item.get("next_followup_at") or "").strip()
        if not due_at:
            base_time = str(item.get("last_contact_time") or "").strip()
            if not base_time:
                continue
            try:
                due_dt = datetime.fromisoformat(base_time) + timedelta(
                    days=_sequence_delay_from_row(item, next_step, fallback_days)
                )
            except ValueError:
                continue
            due_at = due_dt.isoformat(timespec="seconds")
        try:
            due_dt = datetime.fromisoformat(due_at)
        except ValueError:
            continue
        if due_dt > now:
            continue
        item["next_sequence_step"] = next_step
        item["next_followup_at"] = due_at
        items.append(item)
        if len(items) >= max(1, int(limit or 100)):
            break
    return items


def _new_segment_id() -> str:
    return "seg_" + _uuid.uuid4().hex[:10]


def _new_conversation_id() -> str:
    return "conv_" + _uuid.uuid4().hex[:12]


def create_segment(name: str, description: str = "") -> str:
    sid = _new_segment_id()
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO segments (id, name, description, created_at, updated_at)
            VALUES (?,?,?,?,?)
            """,
            (sid, name.strip(), description.strip(), now, now),
        )
    return sid


def get_segments() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM segments ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_segment(segment_id: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM segments WHERE id = ?", (segment_id,)).fetchone()
    return dict(row) if row else None


def delete_segment(segment_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM segments WHERE id = ?", (segment_id,))


def add_targets_to_segment(segment_id: str, targets: List[Dict[str, str]]) -> int:
    if not targets:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    inserted = 0
    with get_conn() as conn:
        for t in targets:
            target_id = str(t.get("id", "")).strip()
            if not target_id:
                continue
            target_source = str(t.get("source", "local") or "local")
            username = str(t.get("username", "") or "")
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO segment_targets (
                    segment_id, target_id, target_source, twitter_username, added_at
                )
                VALUES (?,?,?,?,?)
                """,
                (segment_id, target_id, target_source, username, now),
            )
            inserted += int(cur.rowcount or 0)
    return inserted


def remove_target_from_segment(segment_id: str, target_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM segment_targets WHERE segment_id = ? AND target_id = ?",
            (segment_id, target_id),
        )


def get_segment_targets(segment_id: str, page: int = 1, page_size: int = 50) -> List[Dict[str, Any]]:
    offset = max(page - 1, 0) * max(page_size, 1)
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, segment_id, target_id, target_source, twitter_username, added_at
            FROM segment_targets
            WHERE segment_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (segment_id, page_size, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def get_segment_target_count(segment_id: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM segment_targets WHERE segment_id = ?",
            (segment_id,),
        ).fetchone()
    return int(row["c"]) if row else 0
