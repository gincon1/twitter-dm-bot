from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import sqlite3
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from adspower import start_browser, stop_browser
from config import settings
from database import (
    ACCOUNT_STATUS_ALLOWED,
    ACCOUNT_STATUS_NORMAL,
    CONFIG_KEYS,
    add_log,
    add_targets_to_segment,
    clear_logs,
    create_local_account,
    create_local_target,
    create_segment,
    delete_local_account,
    delete_local_target,
    delete_segment,
    delete_template,
    get_account_runtime_map,
    get_conversation,
    get_conversation_counts,
    get_conversation_counts_by_segment,
    get_conversation_counts_by_client_group,
    get_local_accounts,
    get_local_targets,
    get_local_targets_by_ids,
    get_logs,
    list_message_events,
    list_conversations,
    get_runtime_config,
    get_segment,
    get_segment_target_count,
    get_segment_targets,
    get_segments,
    get_templates,
    get_today_stats,
    import_local_targets,
    init_db,
    normalize_account_status,
    remove_target_from_segment,
    set_runtime_config,
    set_runtime_configs,
    update_conversation,
    update_local_account,
    update_local_target,
    upsert_template,
)
from feishu import FeishuError, get_all_accounts, get_all_targets, get_pending_targets, get_token, update_account, update_target
from message_gen import (
    DEFAULT_TEMPLATES,
    TEMPLATE_TYPE_STEP_1,
    TEMPLATE_TYPE_STEP_2,
    TEMPLATE_TYPE_STEP_3,
    generate,
)
from notifier import send_feishu_test_message
from scheduler import (
    auto_followup,
    get_circuit_breaker_status,
    get_followup_run_status,
    get_status,
    pause,
    check_replies,
    ensure_reply_monitor_job,
    preview_followups,
    reset_circuit_breaker,
    resume,
    run_batch,
    run_batch_for_segment,
    start,
    stop,
    sync_feishu_cache,
    run_warming_batch,
)
from warming import (
    schedule_warming_for_target,
    get_warming_status,
    is_target_warmed,
)
from project_manager import (
    DEFAULT_SEQUENCE_STEP_2_DELAY_DAYS,
    DEFAULT_SEQUENCE_STEP_3_DELAY_DAYS,
    PROJECT_STATUS_ARCHIVED,
    PROJECT_STATUS_COMPLETED,
    PROJECT_STATUS_PAUSED,
    PROJECT_STATUS_READY,
    PROJECT_STATUS_RUNNING,
    create_project,
    get_project,
    get_project_detail,
    list_projects,
    get_project_accounts,
    get_project_targets,
    pause_project,
    refresh_project_stats,
    resume_project,
    start_project_sending,
    sync_project_targets_from_segment,
    upsert_project_accounts,
    set_project_target_status,
)

app = FastAPI(title="Twitter DM System")

origins = [x.strip() for x in settings.cors_origins.split(",") if x.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

TEMPLATE_TYPE_ALIASES = {
    "first_contact": TEMPLATE_TYPE_STEP_1,
    "followup": TEMPLATE_TYPE_STEP_2,
    TEMPLATE_TYPE_STEP_1: TEMPLATE_TYPE_STEP_1,
    TEMPLATE_TYPE_STEP_2: TEMPLATE_TYPE_STEP_2,
    TEMPLATE_TYPE_STEP_3: TEMPLATE_TYPE_STEP_3,
}


def _normalize_template_type(value: str) -> str:
    return TEMPLATE_TYPE_ALIASES.get(str(value or "").strip(), TEMPLATE_TYPE_STEP_1)


def _serialize_template(item: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(item or {})
    payload["template_type"] = _normalize_template_type(payload.get("template_type", TEMPLATE_TYPE_STEP_1))
    return payload


def _serialize_project(project_obj: Any) -> Dict[str, Any]:
    step_1_template_id = str(getattr(project_obj, "sequence_step_1_template_id", "") or getattr(project_obj, "template_id", "") or "")
    step_2_template_id = str(getattr(project_obj, "sequence_step_2_template_id", "") or getattr(project_obj, "followup_template_id", "") or "")
    step_3_template_id = str(getattr(project_obj, "sequence_step_3_template_id", "") or getattr(project_obj, "followup_template_id", "") or "")
    step_2_enabled = bool(getattr(project_obj, "sequence_step_2_enabled", getattr(project_obj, "followup_enabled", True)))
    step_3_enabled = bool(getattr(project_obj, "sequence_step_3_enabled", getattr(project_obj, "followup_enabled", True)))
    step_2_delay_days = max(1, int(getattr(project_obj, "sequence_step_2_delay_days", DEFAULT_SEQUENCE_STEP_2_DELAY_DAYS) or DEFAULT_SEQUENCE_STEP_2_DELAY_DAYS))
    step_3_delay_days = max(1, int(getattr(project_obj, "sequence_step_3_delay_days", DEFAULT_SEQUENCE_STEP_3_DELAY_DAYS) or DEFAULT_SEQUENCE_STEP_3_DELAY_DAYS))
    return {
        "id": project_obj.id,
        "name": project_obj.name,
        "client_group": project_obj.client_group,
        "description": project_obj.description,
        "status": project_obj.status,
        "segment_id": project_obj.segment_id,
        "segment_name": project_obj.segment_name,
        "template_id": project_obj.template_id,
        "followup_template_id": project_obj.followup_template_id,
        "sequence_step_1_template_id": step_1_template_id,
        "sequence_step_2_template_id": step_2_template_id,
        "sequence_step_3_template_id": step_3_template_id,
        "sequence_step_2_delay_days": step_2_delay_days,
        "sequence_step_3_delay_days": step_3_delay_days,
        "sequence_step_2_enabled": step_2_enabled,
        "sequence_step_3_enabled": step_3_enabled,
        "created_at": project_obj.created_at,
        "updated_at": project_obj.updated_at,
        "last_run_at": project_obj.last_run_at,
        "total_targets": project_obj.total_targets,
        "pending_count": project_obj.pending_count,
        "sent_count": project_obj.sent_count,
        "replied_count": project_obj.replied_count,
        "manual_takeover_count": project_obj.manual_takeover_count,
        "completed_count": project_obj.completed_count,
        "warming_enabled": project_obj.warming_enabled,
        "followup_enabled": project_obj.followup_enabled,
        "progress": round((project_obj.sent_count + project_obj.replied_count + project_obj.completed_count) / project_obj.total_targets * 100, 1) if project_obj.total_targets > 0 else 0,
        "reply_rate": round(project_obj.replied_count / project_obj.sent_count * 100, 1) if project_obj.sent_count > 0 else 0,
    }

INT_CONFIG_KEYS = {
    "daily_dm_limit",
    "daily_dm_limit_min",
    "daily_dm_limit_max",
    "min_interval_sec",
    "max_interval_sec",
    "sync_interval_min",
    "reply_check_interval_min",
    "reply_check_normal_interval_min",
    "reply_check_start_hour",
    "reply_check_end_hour",
    "reply_check_full_interval_min",
    "reply_check_full_start_hour",
    "reply_check_full_end_hour",
    "max_retry_accounts_per_target",
    "followup_days",
    "cooldown_hours",
    "business_hours_start",
    "business_hours_end",
    "circuit_breaker_window_min",
    "circuit_breaker_threshold",
}

FEISHU_KEYS = [
    "feishu_app_id",
    "feishu_app_secret",
    "feishu_app_token",
    "feishu_table_targets",
    "feishu_table_accounts",
]


def _account_health(item: dict) -> int:
    try:
        return max(0, min(100, int(item.get("health_score", 100) or 100)))
    except Exception:
        return 100


def _account_daily_limit(item: dict) -> int:
    try:
        current = int(item.get("daily_limit_today", 0) or 0)
    except Exception:
        current = 0
    if current > 0:
        return current
    fallback = max(int(settings.daily_dm_limit_max or settings.daily_dm_limit or 1), 1)
    return fallback


def _cooldown_active(item: dict) -> bool:
    raw = str(item.get("cooldown_until", "") or "").strip()
    if not raw:
        return False
    try:
        return datetime.fromisoformat(raw) > datetime.now()
    except Exception:
        return False


def _validate_account_status(value: str) -> str:
    status = normalize_account_status(value)
    raw = str(value or "").strip()
    if raw and raw not in ACCOUNT_STATUS_ALLOWED:
        raise HTTPException(status_code=400, detail=f"账号状态仅支持：{ACCOUNT_STATUS_NORMAL}/异常")
    return status


def _apply_runtime_config_to_settings():
    cfg = get_runtime_config()
    for key, val in cfg.items():
        if key in INT_CONFIG_KEYS:
            try:
                setattr(settings, key, int(val))
            except Exception:
                continue
        elif key in CONFIG_KEYS:
            setattr(settings, key, str(val))


def _resolve_runtime_db_path() -> Path:
    db_path = Path(settings.runtime_db_path)
    if db_path.is_absolute():
        return db_path
    return Path(__file__).resolve().parent / db_path


def _resolve_screenshot_dir() -> Path:
    screenshot_dir = Path(settings.screenshot_dir)
    if screenshot_dir.is_absolute():
        return screenshot_dir
    return Path(__file__).resolve().parent / screenshot_dir


def _cleanup_file(path: str) -> None:
    try:
        os.remove(path)
    except Exception:
        pass


def _export_db_snapshot() -> tuple[str, str]:
    source_path = _resolve_runtime_db_path()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp = tempfile.NamedTemporaryFile(prefix="runtime_export_", suffix=".db", delete=False)
    tmp.close()

    src = sqlite3.connect(str(source_path))
    dst = sqlite3.connect(tmp.name)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return tmp.name, f"runtime_{stamp}.db"


def _export_logs_file(fmt: str = "csv", days: Optional[int] = None) -> tuple[str, str, str]:
    db_path = _resolve_runtime_db_path()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = ".json" if fmt == "json" else ".csv"
    tmp = tempfile.NamedTemporaryFile(prefix="logs_export_", suffix=suffix, delete=False)
    tmp.close()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        sql = "SELECT * FROM logs"
        params: List[Any] = []
        if days is not None:
            cutoff = (datetime.now() - timedelta(days=max(1, int(days)))).isoformat(timespec="seconds")
            sql += " WHERE timestamp >= ?"
            params.append(cutoff)
        sql += " ORDER BY id DESC"
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()

    if fmt == "json":
        with open(tmp.name, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=2)
        return tmp.name, f"logs_{stamp}.json", "application/json"

    with open(tmp.name, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "timestamp", "level", "account", "target", "status", "message", "meta_json"])
        for row in rows:
            writer.writerow([
                row.get("id", ""),
                row.get("timestamp", ""),
                row.get("level", ""),
                row.get("account", ""),
                row.get("target", ""),
                row.get("status", ""),
                row.get("message", ""),
                row.get("meta_json", ""),
            ])
    return tmp.name, f"logs_{stamp}.csv", "text/csv"


def _split_multi(v: Optional[str]) -> List[str]:
    if not v:
        return []
    return [x.strip() for x in str(v).split(",") if x.strip()]


def _matches_multi_value(value: str, allowed_csv: Optional[str]) -> bool:
    allowed = _split_multi(allowed_csv)
    if not allowed:
        return True
    return value in allowed


def _matches_tags(value: str, tags_csv: Optional[str]) -> bool:
    tags = _split_multi(tags_csv)
    if not tags:
        return True
    lv = str(value or "").lower()
    return any(t.lower() in lv for t in tags)


def _target_match(
    item: dict,
    status: Optional[str],
    type_: Optional[str],
    priority: Optional[str],
    search: Optional[str],
    language: Optional[str],
    source: Optional[str],
    tags: Optional[str],
    kol_tier: Optional[str],
    content_type: Optional[str],
    track: Optional[str],
    cooperation: Optional[str],
    followers_min: Optional[int],
    followers_max: Optional[int],
    chain: Optional[str],
    stage: Optional[str],
    project_type: Optional[str],
) -> bool:
    if status and item.get("status") != status:
        return False
    if type_ and item.get("type") != type_:
        return False
    if priority and item.get("priority") != priority:
        return False
    if search:
        kw = search.lower()
        s1 = str(item.get("twitter_username", "")).lower()
        s2 = str(item.get("project_name", "")).lower()
        if kw not in s1 and kw not in s2:
            return False
    if not _matches_multi_value(str(item.get("language", "")), language):
        return False
    if not _matches_multi_value(str(item.get("source", "")), source):
        return False
    if not _matches_tags(str(item.get("tags", "")), tags):
        return False
    if kol_tier and str(item.get("kol_tier", "")) != kol_tier:
        return False
    if content_type and str(item.get("content_type", "")) != content_type:
        return False
    if track and str(item.get("track", "")) != track:
        return False
    if cooperation and str(item.get("cooperation", "")) != cooperation:
        return False
    followers = int(item.get("followers", 0) or 0)
    if followers_min is not None and followers < int(followers_min):
        return False
    if followers_max is not None and followers > int(followers_max):
        return False
    if chain and str(item.get("chain", "")) != chain:
        return False
    if stage and str(item.get("stage", "")) != stage:
        return False
    if project_type and str(item.get("project_type", "")) != project_type:
        return False
    return True


def _mask_secret(v: str) -> str:
    if not v:
        return ""
    return "***"


def _get_feishu_current_config() -> Dict[str, str]:
    cfg = get_runtime_config()
    return {
        "feishu_app_id": str(cfg.get("feishu_app_id", settings.feishu_app_id or "")),
        "feishu_app_secret": str(cfg.get("feishu_app_secret", settings.feishu_app_secret or "")),
        "feishu_app_token": str(cfg.get("feishu_app_token", settings.feishu_app_token or "")),
        "feishu_table_targets": str(cfg.get("feishu_table_targets", settings.feishu_table_targets or "")),
        "feishu_table_accounts": str(cfg.get("feishu_table_accounts", settings.feishu_table_accounts or "")),
        "feishu_notify_webhook": str(cfg.get("feishu_notify_webhook", settings.feishu_notify_webhook or "")),
    }


def _is_feishu_ready() -> bool:
    cfg = _get_feishu_current_config()
    return all(cfg.get(k, "").strip() for k in FEISHU_KEYS)


def _load_all_accounts() -> List[dict]:
    local = get_local_accounts()
    for a in local:
        a["record_id"] = a["id"]
        a["_source"] = "local"
        a["status"] = normalize_account_status(a.get("status"))
        a["health_score"] = _account_health(a)
        a["daily_limit_today"] = _account_daily_limit(a)

    feishu_accounts: list = []
    if _is_feishu_ready():
        try:
            token = get_token()
            feishu_accounts = get_all_accounts(token)
            runtime_map = get_account_runtime_map(
                [str(a.get("record_id") or a.get("profile_id") or "") for a in feishu_accounts]
            )
            for a in feishu_accounts:
                a["_source"] = "feishu"
                a["status"] = normalize_account_status(a.get("status"))
                runtime = runtime_map.get(str(a.get("record_id") or a.get("profile_id") or ""), {})
                if runtime:
                    a["health_score"] = runtime.get("health_score", a.get("health_score", 100))
                    a["cooldown_until"] = runtime.get("cooldown_until", a.get("cooldown_until", ""))
                    a["daily_limit_today"] = runtime.get("daily_limit_today", a.get("daily_limit_today", 0))
                    a["last_action_time"] = runtime.get("last_action_time", a.get("last_action_time", ""))
                a["health_score"] = _account_health(a)
                a["daily_limit_today"] = _account_daily_limit(a)
        except Exception as e:
            add_log("WARN", "system", "", "feishu_skip", f"账号读取降级为本地: {e}")
    return feishu_accounts + local


def _load_all_targets(
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
) -> List[dict]:
    local = get_local_targets(
        status=status,
        type_=type_,
        priority=priority,
        search=search,
        language=language,
        source=source,
        tags=tags,
        kol_tier=kol_tier,
        content_type=content_type,
        track=track,
        cooperation=cooperation,
        followers_min=followers_min,
        followers_max=followers_max,
        chain=chain,
        stage=stage,
        project_type=project_type,
    )
    for t in local:
        t["record_id"] = t["id"]
        t["_source"] = "local"

    feishu_targets: list = []
    if _is_feishu_ready():
        try:
            token = get_token()
            feishu_targets = get_all_targets(token)
            feishu_targets = [
                t
                for t in feishu_targets
                if _target_match(
                    t,
                    status=status,
                    type_=type_,
                    priority=priority,
                    search=search,
                    language=language,
                    source=source,
                    tags=tags,
                    kol_tier=kol_tier,
                    content_type=content_type,
                    track=track,
                    cooperation=cooperation,
                    followers_min=followers_min,
                    followers_max=followers_max,
                    chain=chain,
                    stage=stage,
                    project_type=project_type,
                )
            ]
            for t in feishu_targets:
                t["_source"] = "feishu"
        except Exception as e:
            add_log("WARN", "system", "", "feishu_skip", f"目标读取降级为本地: {e}")

    return feishu_targets + local


def _set_target_status(record_id: str, source: str, status: str, reply_content: str = "") -> None:
    if str(source or "local") == "local" and str(record_id).startswith("local_"):
        payload: Dict[str, Any] = {"status": status}
        if reply_content:
            payload["reply_content"] = reply_content[:500]
        update_local_target(str(record_id), payload)
        return

    token = get_token()
    fields: Dict[str, Any] = {"状态": status}
    if reply_content:
        fields["回复内容"] = reply_content[:500]
    update_target(token, str(record_id), fields)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"ok": False, "message": str(exc.detail)},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    first = ""
    try:
        first = exc.errors()[0].get("msg", "")
    except Exception:
        first = str(exc)
    return JSONResponse(
        status_code=422,
        content={"ok": False, "message": first or "请求参数校验失败"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    add_log("ERROR", "system", "", "api_error", str(exc))
    return JSONResponse(
        status_code=500,
        content={"ok": False, "message": str(exc)},
    )


_apply_runtime_config_to_settings()


@app.on_event("startup")
def startup_background_jobs():
    ensure_reply_monitor_job()


@app.get("/api/health")
def api_health():
    return {"ok": True, "time": datetime.now().isoformat(timespec="seconds")}


# ---- System control ----
@app.post("/api/start")
def api_start():
    try:
        start()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    add_log("INFO", "system", "", "start", "系统已启动")
    return {"ok": True}


@app.post("/api/pause")
def api_pause():
    pause()
    add_log("INFO", "system", "", "pause", "系统已暂停")
    return {"ok": True}


@app.post("/api/resume")
def api_resume():
    try:
        resume()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    add_log("INFO", "system", "", "resume", "系统已恢复")
    return {"ok": True}


@app.post("/api/stop")
def api_stop():
    stop()
    add_log("INFO", "system", "", "stop", "系统已停止")
    return {"ok": True}


@app.get("/api/status")
def api_status():
    status = get_status()
    stats = get_today_stats()
    status["today_total_sent"] = stats["sent"]

    local_pending = get_local_targets(status="待发送")
    try:
        if _is_feishu_ready():
            token = get_token()
            feishu_pending = get_pending_targets(token)
            status["pending_targets"] = len(feishu_pending) + len(local_pending)
        else:
            status["pending_targets"] = len(local_pending)
    except Exception:
        status["pending_targets"] = len(local_pending)

    accounts = _load_all_accounts()
    status["active_accounts"] = len(
        [
            a
            for a in accounts
            if a.get("status") == "正常"
            and not _cooldown_active(a)
            and _account_health(a) >= 20
            and int(a.get("today_sent", 0) or 0) < _account_daily_limit(a)
        ]
    )
    return status


@app.post("/api/run-now")
def api_run_now():
    thread = threading.Thread(target=lambda: run_batch(wait_between=False), daemon=True)
    thread.start()
    add_log("INFO", "system", "", "run_now", "已手动触发立即执行")
    return {"ok": True, "message": "立即执行已触发"}


@app.post("/api/check-replies")
def api_check_replies():
    add_log("INFO", "system", "", "reply_check_manual", "已手动触发普通同步")
    thread = threading.Thread(target=lambda: check_replies(force=True, include_replied=False), daemon=True)
    thread.start()
    return {"ok": True, "message": "回复检测已触发"}


@app.post("/api/check-replies-full")
def api_check_replies_full():
    add_log("INFO", "system", "", "reply_check_manual", "已手动触发全部同步")
    thread = threading.Thread(target=lambda: check_replies(force=True, include_replied=True), daemon=True)
    thread.start()
    return {"ok": True, "message": "全部同步已触发"}


@app.post("/api/run-followups")
def api_run_followups():
    current = get_followup_run_status()
    if current.get("running"):
        raise HTTPException(status_code=409, detail="续跟任务正在执行中")
    thread = threading.Thread(target=lambda: auto_followup(wait_between=False, trigger="manual"), daemon=True)
    thread.start()
    return {"ok": True, "message": "自动跟进已触发", "run_id": int(current.get("run_id", 0) or 0) + 1}


@app.get("/api/followups/preview")
def api_followups_preview():
    return {"ok": True, **preview_followups()}


@app.get("/api/followups/status")
def api_followups_status():
    return {"ok": True, **get_followup_run_status()}


@app.post("/api/run-warming")
def api_run_warming():
    """手动触发预热任务执行"""
    thread = threading.Thread(target=lambda: run_warming_batch(limit=20), daemon=True)
    thread.start()
    return {"ok": True, "message": "预热任务已触发"}


@app.get("/api/targets/{record_id}/warming")
def api_get_warming_status(record_id: str):
    """获取目标的预热状态"""
    return {"ok": True, **get_warming_status(record_id)}


@app.post("/api/targets/{record_id}/warming")
def api_schedule_warming(record_id: str, hours_before: int = 6):
    """为目标创建预热任务"""
    targets = _load_all_targets()
    target = next((t for t in targets if t.get("record_id") == record_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="目标不存在")

    task_id = schedule_warming_for_target(target, hours_before)
    if task_id:
        return {"ok": True, "task_id": task_id, "message": f"预热任务已创建，{hours_before}小时后执行"}
    return {"ok": False, "message": "预热任务已存在或创建失败"}


@app.get("/api/circuit-breaker")
def api_circuit_breaker():
    return {"ok": True, **get_circuit_breaker_status()}


class CircuitResetBody(BaseModel):
    reset_by: str = "manual"


@app.post("/api/circuit-breaker/reset")
def api_circuit_breaker_reset(body: CircuitResetBody):
    return {"ok": True, **reset_circuit_breaker(body.reset_by or "manual")}


# ---- Accounts ----
@app.get("/api/accounts")
def api_accounts():
    return _load_all_accounts()


class AccountCreate(BaseModel):
    profile_id: str
    twitter_username: str = ""
    status: str = ACCOUNT_STATUS_NORMAL
    bound_ip: str = ""


@app.post("/api/accounts")
def api_create_account(body: AccountCreate):
    if not body.profile_id.strip():
        raise HTTPException(status_code=400, detail="profile_id 不能为空")
    payload = body.model_dump()
    payload["status"] = _validate_account_status(payload.get("status", ACCOUNT_STATUS_NORMAL))
    aid = create_local_account(payload)
    add_log("INFO", "system", "", "account_add", f"本地添加账号 {body.profile_id}")
    return {"ok": True, "id": aid}


class AccountToggle(BaseModel):
    status: str


@app.post("/api/accounts/{record_id}/toggle")
def api_toggle_account(record_id: str, body: AccountToggle):
    next_status = _validate_account_status(body.status)
    if record_id.startswith("local_"):
        update_local_account(record_id, {"status": next_status})
    else:
        token = get_token()
        update_account(token, record_id, {"状态": next_status})
    add_log("INFO", "system", "", "account_toggle", f"账号 {record_id} -> {next_status}")
    return {"ok": True}


@app.post("/api/accounts/{record_id}/test")
def api_test_account(record_id: str):
    accounts = _load_all_accounts()
    target = next((a for a in accounts if a.get("record_id") == record_id), None)
    if not target:
        return {"ok": False, "message": "账号不存在"}

    profile_id = target.get("profile_id", "")
    try:
        ws_url, _debug_port = start_browser(profile_id)
        stop_browser(profile_id)
        return {"ok": True, "message": "连接正常", "ws": bool(ws_url)}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@app.delete("/api/accounts/{record_id}")
def api_delete_account(record_id: str):
    if not record_id.startswith("local_"):
        raise HTTPException(status_code=400, detail="只能删除本地账号")
    delete_local_account(record_id)
    return {"ok": True}


# ---- Feishu Config ----
@app.get("/api/feishu-config")
def api_get_feishu_config():
    cfg = _get_feishu_current_config()
    return {
        "ok": True,
        "feishu_app_id": cfg["feishu_app_id"],
        "feishu_app_secret": _mask_secret(cfg["feishu_app_secret"]),
        "feishu_app_token": cfg["feishu_app_token"],
        "feishu_table_targets": cfg["feishu_table_targets"],
        "feishu_table_accounts": cfg["feishu_table_accounts"],
        "feishu_notify_webhook": cfg["feishu_notify_webhook"],
    }


class FeishuConfigBody(BaseModel):
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_app_token: str = ""
    feishu_table_targets: str = ""
    feishu_table_accounts: str = ""
    feishu_notify_webhook: str = ""


@app.post("/api/feishu-config")
def api_save_feishu_config(body: FeishuConfigBody):
    current = _get_feishu_current_config()
    updates = body.model_dump()
    if updates.get("feishu_app_secret") == "***":
        updates["feishu_app_secret"] = current.get("feishu_app_secret", "")

    set_runtime_configs(updates)
    for key, value in updates.items():
        setattr(settings, key, str(value or ""))

    return {"ok": True, "message": "飞书配置已保存"}


@app.post("/api/feishu-config/test")
def api_test_feishu_config():
    try:
        token = get_token()
        if not token:
            return {"ok": False, "message": "无法获取 tenant_access_token"}
        return {"ok": True, "message": "飞书连接成功"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


class FeishuWebhookTestBody(BaseModel):
    feishu_notify_webhook: str = ""


@app.post("/api/feishu-config/test-webhook")
def api_test_feishu_webhook(body: FeishuWebhookTestBody):
    webhook = str(body.feishu_notify_webhook or "").strip() or _get_feishu_current_config().get("feishu_notify_webhook", "")
    if not str(webhook or "").strip():
        return {"ok": False, "message": "请先填写机器人 Webhook"}
    try:
        send_feishu_test_message(webhook)
        return {"ok": True, "message": "机器人测试消息已发送，请检查飞书"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


# ---- Targets ----
@app.get("/api/targets")
def api_targets(
    status: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    kol_tier: Optional[str] = Query(None),
    content_type: Optional[str] = Query(None),
    track: Optional[str] = Query(None),
    cooperation: Optional[str] = Query(None),
    followers_min: Optional[int] = Query(None),
    followers_max: Optional[int] = Query(None),
    chain: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),
    project_type: Optional[str] = Query(None),
):
    return _load_all_targets(
        status=status,
        type_=type,
        priority=priority,
        search=search,
        language=language,
        source=source,
        tags=tags,
        kol_tier=kol_tier,
        content_type=content_type,
        track=track,
        cooperation=cooperation,
        followers_min=followers_min,
        followers_max=followers_max,
        chain=chain,
        stage=stage,
        project_type=project_type,
    )


class TargetCreate(BaseModel):
    twitter_username: str
    type: str = ""
    project_name: str = ""
    client_group: str = ""
    client_note: str = ""
    priority: str = "中"
    language: str = ""
    source: str = ""
    tags: str = ""
    followers: int = 0
    kol_tier: str = ""
    content_type: str = ""
    track: str = ""
    cooperation: str = ""
    chain: str = ""
    stage: str = ""
    project_type: str = ""
    contact_role: str = ""
    note: str = ""


class TargetImportRow(BaseModel):
    twitter_username: str
    type: str = ""
    client_group: str = ""
    client_note: str = ""
    priority: str = "中"
    language: str = ""
    source: str = ""
    tags: str = ""
    followers: int = 0
    kol_tier: str = ""
    content_type: str = ""
    track: str = ""
    cooperation: str = ""
    project_name: str = ""
    chain: str = ""
    stage: str = ""
    project_type: str = ""
    contact_role: str = ""
    note: str = ""


class TargetImportBody(BaseModel):
    rows: List[TargetImportRow]


@app.post("/api/targets")
def api_create_target(body: TargetCreate):
    username = body.twitter_username.replace("@", "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="twitter_username 不能为空")
    data = body.model_dump()
    data["twitter_username"] = username
    tid = create_local_target(data)
    add_log("INFO", "system", username, "target_add", f"手动添加目标 @{username}")
    return {"ok": True, "id": tid}


@app.post("/api/targets/import")
def api_import_targets(body: TargetImportBody):
    rows = [r.model_dump() for r in body.rows]
    count = import_local_targets(rows)
    add_log("INFO", "system", "", "target_import", f"批量导入 {count} 条目标")
    return {"ok": True, "imported": count}


@app.get("/api/targets/template")
def api_targets_template():
    headers = [
        "twitter_username",
        "type",
        "client_group",
        "client_note",
        "priority",
        "language",
        "source",
        "tags",
        "followers",
        "kol_tier",
        "content_type",
        "track",
        "cooperation",
        "project_name",
        "chain",
        "stage",
        "project_type",
        "contact_role",
        "note",
    ]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    content = buf.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="targets_template.csv"'},
    )


class SkipBody(BaseModel):
    reason: str = "手动跳过"


@app.post("/api/targets/{record_id}/skip")
def api_skip_target(record_id: str, body: SkipBody):
    if record_id.startswith("local_"):
        update_local_target(record_id, {"status": "跳过", "fail_reason": body.reason})
    else:
        token = get_token()
        update_target(token, record_id, {"状态": "跳过", "失败原因": body.reason})
    add_log("INFO", "system", record_id, "skip", body.reason)
    return {"ok": True}


@app.post("/api/targets/{record_id}/reset")
def api_reset_target(record_id: str):
    if record_id.startswith("local_"):
        update_local_target(record_id, {"status": "待发送", "fail_reason": ""})
    else:
        token = get_token()
        update_target(token, record_id, {"状态": "待发送", "失败原因": ""})
    add_log("INFO", "system", record_id, "reset", "目标重置为待发送")
    return {"ok": True}


@app.delete("/api/targets/{record_id}")
def api_delete_target(record_id: str):
    if not record_id.startswith("local_"):
        raise HTTPException(status_code=400, detail="只能删除本地目标")
    delete_local_target(record_id)
    return {"ok": True}


@app.post("/api/sync-feishu")
def api_sync_feishu():
    sync_feishu_cache()
    return {"ok": True, "synced_at": datetime.now().isoformat(timespec="seconds")}


# ---- Segments ----
class SegmentCreateBody(BaseModel):
    name: str
    description: str = ""


class SegmentTargetItem(BaseModel):
    id: str
    source: str = "local"
    username: str = ""


class SegmentTargetsBody(BaseModel):
    targets: List[SegmentTargetItem] = Field(default_factory=list)


class SegmentRunBody(BaseModel):
    account_ids: List[str] = Field(default_factory=list)
    wait_between: bool = True
    client_group: str = ""


@app.get("/api/segments")
def api_segments():
    items = get_segments()
    out = []
    for x in items:
        y = dict(x)
        y["count"] = get_segment_target_count(x["id"])
        out.append(y)
    return out


@app.post("/api/segments")
def api_create_segment(body: SegmentCreateBody):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="包名不能为空")
    sid = create_segment(body.name, body.description)
    return {"ok": True, "id": sid}


@app.get("/api/segments/{segment_id}")
def api_get_segment(segment_id: str):
    seg = get_segment(segment_id)
    if not seg:
        raise HTTPException(status_code=404, detail="人群包不存在")
    seg["count"] = get_segment_target_count(segment_id)
    return seg


@app.delete("/api/segments/{segment_id}")
def api_delete_segment(segment_id: str):
    if not get_segment(segment_id):
        raise HTTPException(status_code=404, detail="人群包不存在")
    delete_segment(segment_id)
    return {"ok": True}


@app.get("/api/segments/{segment_id}/targets")
def api_get_segment_targets(
    segment_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    if not get_segment(segment_id):
        raise HTTPException(status_code=404, detail="人群包不存在")
    rows = get_segment_targets(segment_id, page=page, page_size=page_size)
    total = get_segment_target_count(segment_id)

    local_ids = [r["target_id"] for r in rows if str(r.get("target_id", "")).startswith("local_")]
    local_map = {x["id"]: x for x in get_local_targets_by_ids(local_ids)}

    feishu_map: Dict[str, dict] = {}
    if _is_feishu_ready():
        try:
            token = get_token()
            all_feishu = get_all_targets(token)
            feishu_map = {x["record_id"]: x for x in all_feishu}
        except Exception:
            feishu_map = {}

    enriched = []
    for r in rows:
        x = dict(r)
        target_id = str(x.get("target_id", ""))
        src = str(x.get("target_source", "local"))
        base = local_map.get(target_id, {}) if src == "local" else feishu_map.get(target_id, {})
        x["target"] = {
            "twitter_username": base.get("twitter_username", x.get("twitter_username", "")),
            "type": base.get("type", ""),
            "priority": base.get("priority", ""),
            "status": base.get("status", ""),
            "kol_tier": base.get("kol_tier", ""),
            "track": base.get("track", ""),
            "source": base.get("source", ""),
        }
        enriched.append(x)

    return {"items": enriched, "total": total, "page": page, "page_size": page_size}


@app.post("/api/segments/{segment_id}/targets")
def api_add_segment_targets(segment_id: str, body: SegmentTargetsBody):
    if not get_segment(segment_id):
        raise HTTPException(status_code=404, detail="人群包不存在")
    data = [x.model_dump() for x in body.targets]
    inserted = add_targets_to_segment(segment_id, data)
    return {"ok": True, "inserted": inserted}


@app.delete("/api/segments/{segment_id}/targets/{target_id}")
def api_remove_segment_target(segment_id: str, target_id: str):
    if not get_segment(segment_id):
        raise HTTPException(status_code=404, detail="人群包不存在")
    remove_target_from_segment(segment_id, target_id)
    return {"ok": True}


@app.post("/api/segments/{segment_id}/run")
def api_run_segment(segment_id: str, body: SegmentRunBody):
    if not get_segment(segment_id):
        raise HTTPException(status_code=404, detail="人群包不存在")
    if not body.account_ids:
        raise HTTPException(status_code=400, detail="请至少选择一个账号")
    thread = threading.Thread(
        target=lambda: run_batch_for_segment(
            segment_id=segment_id,
            account_ids=body.account_ids,
            wait_between=body.wait_between,
            client_group=body.client_group.strip(),
        ),
        daemon=True,
    )
    thread.start()
    return {"ok": True, "message": "人群包分发已启动"}


# ---- Conversations ----
@app.get("/api/conversations")
def api_conversations(
    has_reply: Optional[bool] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    segment_id: Optional[str] = Query(None),
    client_group: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    return list_conversations(
        has_reply=has_reply,
        status=status,
        search=search,
        segment_id=segment_id,
        client_group=client_group,
        project_id=project_id,
        limit=limit,
    )


@app.get("/api/conversations/by-segment")
def api_conversations_by_segment():
    return get_conversation_counts_by_segment()


@app.get("/api/conversations/by-client-group")
def api_conversations_by_client_group():
    return get_conversation_counts_by_client_group()


@app.get("/api/conversations/{conversation_id}/messages")
def api_conversation_messages(
    conversation_id: str,
    limit: int = Query(100, ge=1, le=500),
):
    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "ok": True,
        "conversation": conv,
        "messages": list_message_events(conversation_id, limit=limit, ascending=True),
    }


class ConversationStatusBody(BaseModel):
    note: str = ""


@app.post("/api/conversations/{conversation_id}/takeover")
def api_takeover_conversation(conversation_id: str, body: ConversationStatusBody = None):
    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    update_conversation(
        conversation_id,
        {
            "status": "manual_takeover",
            "last_reply_preview": (body.note.strip()[:500] if body else "") or conv.get("last_reply_preview", ""),
        },
    )
    if str(conv.get("project_target_id") or "").strip():
        set_project_target_status(
            str(conv.get("project_target_id") or ""),
            "人工接管",
            note=(body.note.strip()[:500] if body else "") or "",
        )
    else:
        _set_target_status(str(conv.get("target_id") or ""), str(conv.get("target_source") or "local"), "人工接管")
    if str(conv.get("project_id") or "").strip():
        refresh_project_stats(str(conv.get("project_id") or ""))
    return {"ok": True}


@app.post("/api/conversations/{conversation_id}/complete")
def api_complete_conversation(conversation_id: str, body: ConversationStatusBody = None):
    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    update_conversation(
        conversation_id,
        {
            "status": "completed",
            "last_reply_preview": (body.note.strip()[:500] if body else "") or conv.get("last_reply_preview", ""),
        },
    )
    if str(conv.get("project_target_id") or "").strip():
        set_project_target_status(
            str(conv.get("project_target_id") or ""),
            "完成",
            note=(body.note.strip()[:500] if body else "") or "",
        )
    else:
        _set_target_status(str(conv.get("target_id") or ""), str(conv.get("target_source") or "local"), "完成")
    if str(conv.get("project_id") or "").strip():
        refresh_project_stats(str(conv.get("project_id") or ""))
    return {"ok": True}


@app.post("/api/conversations/{conversation_id}/resume-auto")
def api_resume_conversation(conversation_id: str):
    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    next_status = "replied" if int(conv.get("has_reply", 0) or 0) == 1 else "contacted"
    update_conversation(conversation_id, {"status": next_status})
    target_status = "已回复" if next_status == "replied" else "已发送"
    if str(conv.get("project_target_id") or "").strip():
        set_project_target_status(str(conv.get("project_target_id") or ""), target_status)
        if str(conv.get("project_id") or "").strip():
            refresh_project_stats(str(conv.get("project_id") or ""))
    else:
        _set_target_status(str(conv.get("target_id") or ""), str(conv.get("target_source") or "local"), target_status)
    return {"ok": True}


# ---- Templates ----
@app.get("/api/templates")
def api_get_templates():
    db_templates = [_serialize_template(item) for item in get_templates()]
    return {"templates": db_templates, "defaults": DEFAULT_TEMPLATES}


class TemplateCreate(BaseModel):
    content: str
    description: str = ""
    active: bool = True
    template_type: str = TEMPLATE_TYPE_STEP_1


class TemplateUpdate(BaseModel):
    content: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None
    template_type: Optional[str] = None


@app.post("/api/templates")
def api_create_template(body: TemplateCreate):
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")
    import uuid

    tid = "tpl_" + uuid.uuid4().hex[:8]
    upsert_template(
        tid,
        body.content.strip(),
        body.description,
        int(body.active),
        _normalize_template_type(body.template_type),
    )
    return {"ok": True, "id": tid}


@app.put("/api/templates/{template_id}")
def api_update_template(template_id: str, body: TemplateUpdate):
    existing = next((t for t in get_templates() if t["id"] == template_id), None)
    if not existing:
        raise HTTPException(status_code=404, detail="模板不存在")
    content = body.content.strip() if body.content is not None else existing["content"]
    description = body.description if body.description is not None else existing.get("description", "")
    active = int(body.active) if body.active is not None else existing.get("active", 1)
    template_type = _normalize_template_type(body.template_type if body.template_type is not None else existing.get("template_type", TEMPLATE_TYPE_STEP_1))
    upsert_template(template_id, content, description, active, template_type)
    return {"ok": True}


@app.delete("/api/templates/{template_id}")
def api_delete_template(template_id: str):
    delete_template(template_id)
    return {"ok": True}


@app.get("/api/templates/preview")
def api_preview_template(project: str = "ExampleProject", template_type: str = TEMPLATE_TYPE_STEP_1, handle: str = ""):
    return {"preview": generate(project, template_type=_normalize_template_type(template_type), handle=handle)}


# ---- Runtime Config ----
@app.get("/api/config")
def api_get_config():
    db_cfg = get_runtime_config()
    normal_interval = int(
        db_cfg.get(
            "reply_check_normal_interval_min",
            db_cfg.get("reply_check_interval_min", settings.reply_check_normal_interval_min),
        )
    )
    return {
        "daily_dm_limit": int(db_cfg.get("daily_dm_limit", settings.daily_dm_limit)),
        "daily_dm_limit_min": int(db_cfg.get("daily_dm_limit_min", settings.daily_dm_limit_min)),
        "daily_dm_limit_max": int(db_cfg.get("daily_dm_limit_max", settings.daily_dm_limit_max)),
        "min_interval_sec": int(db_cfg.get("min_interval_sec", settings.min_interval_sec)),
        "max_interval_sec": int(db_cfg.get("max_interval_sec", settings.max_interval_sec)),
        "sync_interval_min": int(db_cfg.get("sync_interval_min", settings.sync_interval_min)),
        "reply_check_interval_min": normal_interval,
        "reply_check_normal_interval_min": normal_interval,
        "reply_check_start_hour": int(db_cfg.get("reply_check_start_hour", settings.reply_check_start_hour)),
        "reply_check_end_hour": int(db_cfg.get("reply_check_end_hour", settings.reply_check_end_hour)),
        "reply_check_full_interval_min": int(
            db_cfg.get("reply_check_full_interval_min", settings.reply_check_full_interval_min)
        ),
        "reply_check_full_start_hour": int(
            db_cfg.get("reply_check_full_start_hour", settings.reply_check_full_start_hour)
        ),
        "reply_check_full_end_hour": int(
            db_cfg.get("reply_check_full_end_hour", settings.reply_check_full_end_hour)
        ),
        "max_retry_accounts_per_target": int(
            db_cfg.get("max_retry_accounts_per_target", settings.max_retry_accounts_per_target)
        ),
        "followup_days": int(db_cfg.get("followup_days", settings.followup_days)),
        "cooldown_hours": int(db_cfg.get("cooldown_hours", settings.cooldown_hours)),
        "business_hours_start": int(db_cfg.get("business_hours_start", settings.business_hours_start)),
        "business_hours_end": int(db_cfg.get("business_hours_end", settings.business_hours_end)),
        "circuit_breaker_window_min": int(
            db_cfg.get("circuit_breaker_window_min", settings.circuit_breaker_window_min)
        ),
        "circuit_breaker_threshold": int(
            db_cfg.get("circuit_breaker_threshold", settings.circuit_breaker_threshold)
        ),
        "feishu_notify_webhook": str(db_cfg.get("feishu_notify_webhook", settings.feishu_notify_webhook)),
    }


class ConfigUpdate(BaseModel):
    daily_dm_limit: Optional[int] = None
    daily_dm_limit_min: Optional[int] = None
    daily_dm_limit_max: Optional[int] = None
    min_interval_sec: Optional[int] = None
    max_interval_sec: Optional[int] = None
    sync_interval_min: Optional[int] = None
    reply_check_interval_min: Optional[int] = None
    reply_check_normal_interval_min: Optional[int] = None
    reply_check_start_hour: Optional[int] = None
    reply_check_end_hour: Optional[int] = None
    reply_check_full_interval_min: Optional[int] = None
    reply_check_full_start_hour: Optional[int] = None
    reply_check_full_end_hour: Optional[int] = None
    max_retry_accounts_per_target: Optional[int] = None
    followup_days: Optional[int] = None
    cooldown_hours: Optional[int] = None
    business_hours_start: Optional[int] = None
    business_hours_end: Optional[int] = None
    circuit_breaker_window_min: Optional[int] = None
    circuit_breaker_threshold: Optional[int] = None
    feishu_notify_webhook: Optional[str] = None


@app.post("/api/config")
def api_set_config(body: ConfigUpdate):
    updates = body.model_dump(exclude_none=True)
    if "daily_dm_limit" in updates and "daily_dm_limit_min" not in updates and "daily_dm_limit_max" not in updates:
        updates["daily_dm_limit_min"] = updates["daily_dm_limit"]
        updates["daily_dm_limit_max"] = updates["daily_dm_limit"]
    if "reply_check_interval_min" in updates and "reply_check_normal_interval_min" not in updates:
        updates["reply_check_normal_interval_min"] = updates["reply_check_interval_min"]
    if "reply_check_normal_interval_min" in updates and "reply_check_interval_min" not in updates:
        updates["reply_check_interval_min"] = updates["reply_check_normal_interval_min"]
    if "daily_dm_limit_min" in updates and "daily_dm_limit_max" in updates:
        if int(updates["daily_dm_limit_min"]) > int(updates["daily_dm_limit_max"]):
            raise HTTPException(status_code=400, detail="每日上限最小值不能大于最大值")
    for key in (
        "reply_check_start_hour",
        "reply_check_end_hour",
        "reply_check_full_start_hour",
        "reply_check_full_end_hour",
        "business_hours_start",
        "business_hours_end",
    ):
        if key in updates:
            val = int(updates[key])
            if (key.endswith("end_hour") or key == "business_hours_end") and val == 24:
                updates[key] = 24
                continue
            if val < 0 or val > 23:
                raise HTTPException(status_code=400, detail=f"{key} 仅支持 0-23")
    for key, val in updates.items():
        set_runtime_config(key, str(val))
        setattr(settings, key, val)
    if {
        "reply_check_interval_min",
        "reply_check_normal_interval_min",
        "reply_check_start_hour",
        "reply_check_end_hour",
        "reply_check_full_interval_min",
        "reply_check_full_start_hour",
        "reply_check_full_end_hour",
    } & set(updates.keys()):
        ensure_reply_monitor_job()
    return {"ok": True}


# ---- Logs & Stats ----
@app.get("/api/logs")
def api_logs(limit: int = 300):
    return get_logs(limit=limit)


class LogsClearBody(BaseModel):
    statuses: List[str] = Field(default_factory=list)
    older_than_days: Optional[int] = None


@app.post("/api/logs/clear")
def api_clear_logs(body: LogsClearBody):
    deleted = clear_logs(statuses=body.statuses, older_than_days=body.older_than_days)
    return {"ok": True, "deleted": deleted}


class ArtifactsCleanupBody(BaseModel):
    older_than_days: int = 7


@app.get("/api/maintenance/export/database")
def api_export_database():
    file_path, filename = _export_db_snapshot()
    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=filename,
        background=BackgroundTask(_cleanup_file, file_path),
    )


@app.get("/api/maintenance/export/logs")
def api_export_logs(
    format: str = Query("csv", pattern="^(csv|json)$"),
    days: Optional[int] = Query(None, ge=1, le=3650),
):
    file_path, filename, media_type = _export_logs_file(format, days)
    return FileResponse(
        file_path,
        media_type=media_type,
        filename=filename,
        background=BackgroundTask(_cleanup_file, file_path),
    )


@app.post("/api/maintenance/cleanup/artifacts")
def api_cleanup_artifacts(body: ArtifactsCleanupBody):
    root = _resolve_screenshot_dir()
    if not root.exists():
        return {"ok": True, "deleted": 0, "bytes": 0}

    cutoff = datetime.now().timestamp() - max(1, int(body.older_than_days or 7)) * 86400
    deleted = 0
    reclaimed = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except Exception:
            continue
        if stat.st_mtime >= cutoff:
            continue
        try:
            reclaimed += int(stat.st_size or 0)
            path.unlink()
            deleted += 1
        except Exception:
            continue
    return {"ok": True, "deleted": deleted, "bytes": reclaimed}


@app.get("/api/logs/stream")
async def api_logs_stream():
    async def event_gen():
        last_id = 0
        while True:
            logs = get_logs(limit=80)
            fresh = [x for x in logs if int(x.get("id", 0)) > last_id]
            for log in reversed(fresh):
                last_id = max(last_id, int(log.get("id", 0)))
                yield f"data: {json.dumps(log, ensure_ascii=False)}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.get("/api/stats")
def api_stats():
    stats = get_today_stats()
    logs = get_logs(limit=1000)
    conversation_counts = get_conversation_counts()
    recent_replies = list_conversations(has_reply=True, limit=8)
    pending_replies = list_conversations(status="replied", limit=8)
    pending_targets = len(_load_all_targets(status="待发送"))

    by_account = {}
    for log in logs:
        if log.get("status") == "sent" and log.get("account"):
            account = log["account"]
            by_account[account] = by_account.get(account, 0) + 1

    return {
        "today": stats,
        "by_account": by_account,
        "conversations": conversation_counts,
        "recent_replies": recent_replies,
        "pending_replies": pending_replies,
        "funnel": {
            "pending": pending_targets,
            "contacted": conversation_counts.get("contacted", 0),
            "replied": conversation_counts.get("replied", 0),
            "manual_takeover": conversation_counts.get("manual_takeover", 0),
            "completed": conversation_counts.get("completed", 0),
        },
    }


# ============ 项目管理 API ============

class CreateProjectRequest(BaseModel):
    name: str
    client_group: str = ""
    description: str = ""
    segment_id: str = ""
    template_id: str = ""
    followup_template_id: str = ""
    sequence_step_1_template_id: str = ""
    sequence_step_2_template_id: str = ""
    sequence_step_3_template_id: str = ""
    sequence_step_2_delay_days: int = DEFAULT_SEQUENCE_STEP_2_DELAY_DAYS
    sequence_step_3_delay_days: int = DEFAULT_SEQUENCE_STEP_3_DELAY_DAYS
    sequence_step_2_enabled: bool = True
    sequence_step_3_enabled: bool = True
    account_ids: List[str] = Field(default_factory=list)
    warming_enabled: bool = False
    followup_enabled: bool = True


@app.get("/api/projects")
def api_list_projects(status: Optional[str] = Query(None)):
    projects = list_projects(status)
    items = [_serialize_project(p) for p in projects]
    return {"ok": True, "items": items, "projects": items}


@app.post("/api/projects")
def api_create_project(req: CreateProjectRequest):
    project = create_project(
        name=req.name,
        client_group=req.client_group,
        description=req.description,
        segment_id=req.segment_id,
        template_id=req.template_id,
        followup_template_id=req.followup_template_id,
        sequence_step_1_template_id=req.sequence_step_1_template_id,
        sequence_step_2_template_id=req.sequence_step_2_template_id,
        sequence_step_3_template_id=req.sequence_step_3_template_id,
        sequence_step_2_delay_days=req.sequence_step_2_delay_days,
        sequence_step_3_delay_days=req.sequence_step_3_delay_days,
        sequence_step_2_enabled=req.sequence_step_2_enabled,
        sequence_step_3_enabled=req.sequence_step_3_enabled,
        account_ids=req.account_ids,
        warming_enabled=req.warming_enabled,
        followup_enabled=req.followup_enabled,
    )
    refresh_project_stats(project.id)
    created = get_project(project.id) or project
    return {"ok": True, "project": _serialize_project(created)}


@app.get("/api/projects/{project_id}")
def api_get_project(project_id: str):
    detail = get_project_detail(project_id)
    if not detail:
        raise HTTPException(status_code=404, detail="项目不存在")

    project = detail["project"]
    project_obj = project if hasattr(project, "id") else None
    if not project_obj:
        raise HTTPException(status_code=404, detail="项目不存在")

    account_links = detail.get("accounts") or []
    all_accounts = _load_all_accounts()
    account_map = {str(acc.get("record_id") or ""): acc for acc in all_accounts}
    accounts = []
    for link in account_links:
        merged = dict(link)
        merged.update(account_map.get(str(link.get("account_id") or ""), {}))
        merged["account_id"] = str(link.get("account_id") or "")
        accounts.append(merged)

    targets = detail.get("targets") or []
    return {
        "ok": True,
        "project": _serialize_project(project_obj),
        "accounts": accounts,
        "targets": targets,
        "stats": {
            "progress": round((project_obj.sent_count + project_obj.replied_count + project_obj.completed_count) / project_obj.total_targets * 100, 1) if project_obj.total_targets > 0 else 0,
            "reply_rate": round(project_obj.replied_count / project_obj.sent_count * 100, 1) if project_obj.sent_count > 0 else 0,
            "pending_count": project_obj.pending_count,
            "sent_count": project_obj.sent_count,
            "replied_count": project_obj.replied_count,
            "manual_takeover_count": project_obj.manual_takeover_count,
            "completed_count": project_obj.completed_count,
        }
    }


@app.post("/api/projects/{project_id}/start")
def api_start_project(project_id: str):
    """启动项目发送"""
    result = start_project_sending(project_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@app.post("/api/projects/{project_id}/pause")
def api_pause_project(project_id: str):
    project = pause_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"ok": True, "message": "项目已暂停", "status": project.status}


@app.post("/api/projects/{project_id}/resume")
def api_resume_project(project_id: str):
    result = start_project_sending(project_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "项目恢复失败")
    return result


@app.post("/api/projects/{project_id}/targets")
def api_sync_project_targets(project_id: str):
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    inserted = sync_project_targets_from_segment(project_id)
    refresh_project_stats(project_id)
    return {"ok": True, "inserted": inserted, "message": "项目目标已同步"}


class ProjectAccountsBody(BaseModel):
    account_ids: List[str] = Field(default_factory=list)


@app.post("/api/projects/{project_id}/accounts")
def api_update_project_accounts(project_id: str, body: ProjectAccountsBody):
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    count = upsert_project_accounts(project_id, body.account_ids)
    refresh_project_stats(project_id)
    return {"ok": True, "count": count, "message": "项目账号已更新"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.backend_host, port=settings.backend_port, reload=False)
