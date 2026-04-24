from __future__ import annotations

import random
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler

from adspower import start_browser, stop_browser
from config import settings
from database import (
    _resolve_next_sequence_state,
    add_log,
    get_followup_candidates,
    get_reply_pending_notifications,
    get_conversation_counts,
    list_conversations,
    mark_conversation_checked,
    mark_conversation_notified,
    mark_conversation_reply,
    get_account_runtime_map,
    get_local_accounts,
    get_local_pending_targets,
    get_local_targets_by_ids,
    list_message_events,
    record_message_events,
    get_segment,
    get_segment_target_count,
    get_segment_targets,
    reset_account_runtime_daily,
    reset_local_account_daily_stats,
    upsert_conversation_for_send,
    upsert_account_runtime,
    update_conversation,
    update_local_account,
    update_local_target,
)
from feishu import get_all_accounts, get_all_targets, get_pending_targets, get_token, now_ms, reset_daily_counts, update_account, update_target
from message_gen import TEMPLATE_TYPE_STEP_1, TEMPLATE_TYPE_STEP_2, TEMPLATE_TYPE_STEP_3, generate
from nickname_gen import extract_nickname
from reply_analyzer import analyze_reply
from notifier import send_feishu_reply_notification
from playwright_agent import send_dm
from reply_checker import check_account_replies
from circuit_breaker import circuit_breaker, record_account_failure, is_circuit_tripped, reset_circuit_breaker, get_circuit_status
from warming import (
    schedule_warming_for_targets,
    run_warming_batch,
    is_target_warmed,
    get_warming_status,
    schedule_warming_jobs,
)

scheduler = BackgroundScheduler(timezone=settings.timezone)

_running = False
_paused = False
_batch_lock = threading.Lock()
_reply_check_lock = threading.Lock()
_followup_state_lock = threading.Lock()
_followup_run_state = {
    "run_id": 0,
    "running": False,
    "trigger": "",
    "started_at": "",
    "finished_at": "",
    "summary": {},
}

_status = {
    "running": False,
    "paused": False,
    "pause_reason": "",
    "active_accounts": 0,
    "today_total_sent": 0,
    "pending_targets": 0,
    "next_run_time": None,
    "last_sync_time": None,
}

NON_RETRY_TARGET_STATUSES = {"target_not_found", "cannot_dm", "blocked_verification"}
RETRYABLE_STATUSES = {"error", "sent_attempt"}
HEALTH_SLOW_THRESHOLD = 40
HEALTH_STOP_THRESHOLD = 20


def _project_sequence_settings(project_obj: Optional[Any]) -> dict:
    return {
        "step_1_template_id": "",
        "step_2_template_id": "",
        "step_3_template_id": "",
        "step_2_enabled": True,
        "step_3_enabled": True,
        "step_2_delay_days": 3,
        "step_3_delay_days": 5,
    }


def _sequence_template_type(step: int) -> str:
    mapping = {
        1: TEMPLATE_TYPE_STEP_1,
        2: TEMPLATE_TYPE_STEP_2,
        3: TEMPLATE_TYPE_STEP_3,
    }
    return mapping.get(int(step or 1), TEMPLATE_TYPE_STEP_1)


def get_status() -> dict:
    s = _status.copy()
    # 合并熔断器状态
    cb_status = get_circuit_status()
    s["circuit_breaker_tripped"] = cb_status["tripped"]
    s["circuit_breaker_tripped_at"] = cb_status["tripped_at"]
    s["circuit_breaker_recent_failures"] = cb_status["failure_count"]
    s["circuit_breaker_reason"] = f"{cb_status['window_minutes']} 分钟内 {cb_status['failure_count']}/{cb_status['threshold']} 个账号异常"
    s["circuit_breaker_last_reset_by"] = ""
    try:
        jobs = [j for j in scheduler.get_jobs() if j.id.startswith("batch_")]
        jobs = sorted(jobs, key=lambda x: x.next_run_time or datetime.max)
        if jobs and jobs[0].next_run_time:
            s["next_run_time"] = jobs[0].next_run_time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return s


def get_followup_run_status() -> dict:
    with _followup_state_lock:
        summary = dict(_followup_run_state.get("summary") or {})
        return {
            "run_id": int(_followup_run_state.get("run_id", 0) or 0),
            "running": bool(_followup_run_state.get("running")),
            "trigger": str(_followup_run_state.get("trigger") or ""),
            "started_at": str(_followup_run_state.get("started_at") or ""),
            "finished_at": str(_followup_run_state.get("finished_at") or ""),
            "summary": summary,
        }


def _begin_followup_run(trigger: str) -> int:
    with _followup_state_lock:
        run_id = int(_followup_run_state.get("run_id", 0) or 0) + 1
        _followup_run_state.update(
            {
                "run_id": run_id,
                "running": True,
                "trigger": trigger,
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "finished_at": "",
                "summary": {},
            }
        )
        return run_id


def _finish_followup_run(run_id: int, summary: dict) -> None:
    with _followup_state_lock:
        if int(_followup_run_state.get("run_id", 0) or 0) != int(run_id):
            return
        _followup_run_state["running"] = False
        _followup_run_state["finished_at"] = datetime.now().isoformat(timespec="seconds")
        _followup_run_state["summary"] = dict(summary or {})


def _account_key(account: dict) -> str:
    return str(account.get("record_id") or account.get("id") or account.get("profile_id") or "").strip()


def _account_name(account: dict) -> str:
    return account.get("twitter_username", "") or str(account.get("profile_id", ""))


def _account_health(account: dict) -> int:
    try:
        return max(0, min(100, int(account.get("health_score", 100) or 100)))
    except Exception:
        return 100


def _account_daily_limit(account: dict) -> int:
    try:
        current = int(account.get("daily_limit_today", 0) or 0)
    except Exception:
        current = 0
    if current > 0:
        return current
    fallback = max(int(settings.daily_dm_limit_max or settings.daily_dm_limit or 1), 1)
    return fallback


def _parse_dt(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def _in_cooldown(account: dict) -> bool:
    until = _parse_dt(account.get("cooldown_until"))
    return bool(until and until > datetime.now())


def _is_business_hour(now: Optional[datetime] = None) -> bool:
    current = now or datetime.now()
    start = max(0, min(23, int(settings.business_hours_start)))
    end = max(1, min(24, int(settings.business_hours_end)))
    if start == end:
        return True
    if start < end:
        return start <= current.hour < end
    return current.hour >= start or current.hour < end


def _hour_in_window(hour: int, start: int, end: int) -> bool:
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _is_reply_check_window(include_replied: bool, now: Optional[datetime] = None) -> bool:
    current = now or datetime.now()
    if include_replied:
        start = max(0, min(23, int(getattr(settings, "reply_check_full_start_hour", 10) or 10)))
        end = int(getattr(settings, "reply_check_full_end_hour", 2) or 2)
    else:
        start = max(0, min(23, int(getattr(settings, "reply_check_start_hour", 10) or 10)))
        end = int(getattr(settings, "reply_check_end_hour", 2) or 2)
    end = 24 if end == 24 else max(0, min(23, end))
    return _hour_in_window(current.hour, start, end)


def _random_daily_limit() -> int:
    low = max(1, int(settings.daily_dm_limit_min or settings.daily_dm_limit or 1))
    high = max(low, int(settings.daily_dm_limit_max or low))
    return random.randint(low, high)


def get_circuit_breaker_status() -> dict:
    return get_circuit_status()


def reset_circuit_breaker(reset_by: str = "manual") -> dict:
    result = circuit_breaker.reset(reset_by)
    if result:
        global _paused
        if _paused and _status.get("pause_reason") != "manual":
            _paused = False
            _status["paused"] = False
            _status["pause_reason"] = ""
    return get_circuit_status()


def _ensure_runtime_defaults(account: dict) -> None:
    account.setdefault("health_score", 100)
    account.setdefault("cooldown_until", "")
    account.setdefault("daily_limit_today", 0)
    account.setdefault("last_action_time", "")
    try:
        current = int(account.get("daily_limit_today", 0) or 0)
    except Exception:
        current = 0
    if current <= 0:
        account["daily_limit_today"] = _random_daily_limit()


def _persist_runtime_fields(account: dict, fields: Dict[str, Any]) -> None:
    record_id = str(account.get("record_id") or account.get("id", ""))
    if record_id.startswith("local_"):
        update_local_account(record_id, fields)
        return
    upsert_account_runtime(_account_key(account), fields)


def _apply_account_health(
    token: Optional[str],
    account: dict,
    delta: int,
    cooldown_hours: Optional[int] = None,
    force_abnormal: bool = False,
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    next_score = max(0, min(100, _account_health(account) + delta))
    next_status = account.get("status", "正常")
    cooldown_until = account.get("cooldown_until", "")

    if cooldown_hours:
        cooldown_until = (datetime.now() + timedelta(hours=max(1, int(cooldown_hours)))).isoformat(timespec="seconds")
    if force_abnormal or next_score < HEALTH_STOP_THRESHOLD:
        next_status = "异常"
        if not cooldown_until:
            cooldown_until = (datetime.now() + timedelta(hours=max(1, int(settings.cooldown_hours or 12)))).isoformat(timespec="seconds")

    account["health_score"] = next_score
    account["cooldown_until"] = cooldown_until
    account["last_action_time"] = now
    account["status"] = next_status

    runtime_fields = {
        "health_score": next_score,
        "cooldown_until": cooldown_until,
        "last_action_time": now,
        "status": next_status,
    }
    _persist_runtime_fields(account, runtime_fields)

    record_id = str(account.get("record_id") or account.get("id", ""))
    if not record_id.startswith("local_") and token and next_status == "异常":
        try:
            update_account(token, record_id, {"状态": "异常", "最后操作时间": now_ms()})
        except Exception:
            pass


def _ensure_daily_limit(account: dict) -> None:
    try:
        current = int(account.get("daily_limit_today", 0) or 0)
    except Exception:
        current = 0
    if current > 0:
        account["daily_limit_today"] = current
        return
    daily_limit = _random_daily_limit()
    account["daily_limit_today"] = daily_limit
    _persist_runtime_fields(account, {"daily_limit_today": daily_limit})


def start():
    global _running, _paused
    if is_circuit_tripped():
        raise RuntimeError("当前处于熔断状态，请先人工解除")
    _running = True
    _paused = False
    _status["running"] = True
    _status["paused"] = False
    _status["pause_reason"] = ""

    scheduler.add_job(daily_reset, "cron", hour=9, minute=0, id="daily_reset", replace_existing=True)

    for hour in [10, 14, 19]:
        scheduler.add_job(
            run_batch,
            "cron",
            hour=hour,
            minute=random.randint(0, 20),
            id=f"batch_{hour}",
            replace_existing=True,
        )

    scheduler.add_job(
        sync_feishu_cache,
        "interval",
        minutes=settings.sync_interval_min,
        id="feishu_sync",
        replace_existing=True,
    )
    ensure_reply_monitor_job()

    scheduler.add_job(
        auto_followup,
        "interval",
        hours=6,
        id="auto_followup",
        replace_existing=True,
    )

    # 添加预热任务调度
    schedule_warming_jobs(scheduler)

    if not scheduler.running:
        scheduler.start()


def pause():
    global _paused
    _paused = True
    _status["paused"] = True
    _status["pause_reason"] = "manual"


def resume():
    global _paused
    if is_circuit_tripped():
        raise RuntimeError("当前处于熔断状态，请先人工解除")
    _paused = False
    _status["paused"] = False
    _status["pause_reason"] = ""


def stop():
    global _running, _paused
    _running = False
    _paused = False
    _status["running"] = False
    _status["paused"] = False
    _status["pause_reason"] = ""

    for job_id in [
        "daily_reset",
        "batch_10",
        "batch_14",
        "batch_19",
        "feishu_sync",
        "auto_followup",
        "reply_check",
        "reply_check_normal",
        "reply_check_full",
    ]:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass


def ensure_reply_monitor_job() -> None:
    normal_interval = max(
        5,
        int(
            getattr(
                settings,
                "reply_check_normal_interval_min",
                getattr(settings, "reply_check_interval_min", 120),
            )
            or 120
        ),
    )
    full_interval = max(5, int(getattr(settings, "reply_check_full_interval_min", 360) or 360))
    for job_id in ("reply_check", "reply_check_normal", "reply_check_full"):
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass
    scheduler.add_job(
        _scheduled_normal_reply_check,
        "interval",
        minutes=normal_interval,
        id="reply_check_normal",
        replace_existing=True,
    )
    scheduler.add_job(
        _scheduled_full_reply_check,
        "interval",
        minutes=full_interval,
        id="reply_check_full",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()


def _scheduled_normal_reply_check() -> None:
    check_replies(force=False, include_replied=False)


def _scheduled_full_reply_check() -> None:
    check_replies(force=False, include_replied=True)


def daily_reset():
    local_accounts = _normalize_local_accounts(get_local_accounts())
    local_limits = {str(a.get("record_id")): _random_daily_limit() for a in local_accounts}
    reset_local_account_daily_stats(local_limits)

    try:
        token = get_token()
        accounts = get_all_accounts(token)
        reset_daily_counts(token, accounts)
        runtime_limits = {
            str(a.get("record_id") or a.get("profile_id") or ""): _random_daily_limit()
            for a in accounts
            if str(a.get("record_id") or a.get("profile_id") or "").strip()
        }
        reset_account_runtime_daily(runtime_limits)
        add_log("INFO", "system", "", "reset", "今日发送计数与随机上限已重置")
    except Exception as e:
        add_log("WARN", "system", "", "reset_skip", f"飞书不可用，仅重置本地账号: {e}")


def sync_feishu_cache():
    _status["last_sync_time"] = datetime.now().strftime("%H:%M:%S")


def _available_accounts(accounts: List[dict]) -> List[dict]:
    return [
        a
        for a in accounts
        if a.get("status") == "正常"
        and a.get("profile_id")
        and not _in_cooldown(a)
        and _account_health(a) >= HEALTH_STOP_THRESHOLD
        and int(a.get("today_sent", 0) or 0) < _account_daily_limit(a)
    ]


def _normalize_local_accounts(accounts: List[dict]) -> List[dict]:
    out: List[dict] = []
    for a in accounts:
        x = dict(a)
        x.setdefault("record_id", x.get("id", ""))
        x.setdefault("_source", "local")
        _ensure_daily_limit(x)
        out.append(x)
    return out


def _normalize_local_targets(targets: List[dict]) -> List[dict]:
    out: List[dict] = []
    for t in targets:
        x = dict(t)
        x.setdefault("record_id", x.get("id", ""))
        x.setdefault("_source", "local")
        out.append(x)
    return out


def _fetch_all_accounts() -> tuple[Optional[str], List[dict]]:
    token: Optional[str] = None
    feishu_accounts: List[dict] = []
    try:
        token = get_token()
        feishu_accounts = get_all_accounts(token)
        runtime_map = get_account_runtime_map(
            [str(a.get("record_id") or a.get("profile_id") or "") for a in feishu_accounts]
        )
        for a in feishu_accounts:
            a.setdefault("_source", "feishu")
            runtime = runtime_map.get(str(a.get("record_id") or a.get("profile_id") or ""), {})
            if runtime:
                a["health_score"] = runtime.get("health_score", a.get("health_score", 100))
                a["cooldown_until"] = runtime.get("cooldown_until", a.get("cooldown_until", ""))
                a["daily_limit_today"] = runtime.get("daily_limit_today", a.get("daily_limit_today", 0))
                a["last_action_time"] = runtime.get("last_action_time", a.get("last_action_time", ""))
            _ensure_daily_limit(a)
    except Exception as e:
        add_log("WARN", "system", "", "feishu_skip", f"飞书不可用，仅使用本地账号: {e}")

    local_accounts = _normalize_local_accounts(get_local_accounts())
    return token, feishu_accounts + local_accounts


def _fetch_pending_targets(token: Optional[str]) -> List[dict]:
    feishu_targets: List[dict] = []
    if token:
        try:
            feishu_targets = get_pending_targets(token)
            for t in feishu_targets:
                t.setdefault("_source", "feishu")
        except Exception as e:
            add_log("WARN", "system", "", "feishu_skip", f"飞书待发送读取失败，仅使用本地目标: {e}")
    local_targets = _normalize_local_targets(get_local_pending_targets())
    return feishu_targets + local_targets


def _tracked_conversations_by_account(include_replied: bool = False) -> Dict[str, List[dict]]:
    items = list_conversations(has_reply=None if include_replied else False, limit=1000)
    grouped: Dict[str, List[dict]] = {}
    for item in items:
        if str(item.get("status") or "") in {"completed", "manual_takeover"}:
            continue
        key = str(item.get("account_key") or "").strip()
        if not key:
            continue
        grouped.setdefault(key, []).append(item)
    for key, convs in grouped.items():
        ordered = sorted(
            convs,
            key=lambda item: (
                str(item.get("client_group") or ""),
                str(item.get("segment_name") or ""),
                str(item.get("project_name") or ""),
                str(item.get("last_checked_at") or ""),
                str(item.get("target_username") or ""),
            ),
        )
        for idx, item in enumerate(ordered):
            item["reply_check_strategy"] = "search_first" if idx % 2 else "list_first"
            item["reply_check_group"] = " / ".join(
                x
                for x in [
                    str(item.get("client_group") or "").strip(),
                    str(item.get("segment_name") or "").strip(),
                    str(item.get("project_name") or "").strip(),
                ]
                if x
            )
        grouped[key] = ordered
    return grouped


def _notify_pending_replies() -> None:
    for item in get_reply_pending_notifications(limit=100):
        try:
            messages = [
                str(x.get("content") or "").strip()
                for x in list_message_events(
                    str(item.get("id") or ""),
                    direction="inbound",
                    only_unnotified=True,
                    limit=20,
                )
                if str(x.get("content") or "").strip()
            ]
            if not messages:
                fallback = str(item.get("last_reply_preview") or "").strip()
                messages = [fallback] if fallback else []
            sent = send_feishu_reply_notification(
                client_group=str(item.get("client_group") or ""),
                account_name=str(item.get("account_username") or item.get("account_profile_id") or ""),
                target_username=str(item.get("target_username") or ""),
                reply_messages=messages,
                box=str(item.get("last_box") or "inbox"),
            )
            if sent:
                mark_conversation_notified(str(item.get("id")))
        except Exception as exc:
            add_log(
                "WARN",
                "system",
                str(item.get("target_username") or ""),
                "notify_failed",
                str(exc),
            )


def _mark_target_done(token: Optional[str], target: dict, new_status: str, sent_by: str, fail_reason: str = "") -> None:
    record_id = target.get("record_id") or target.get("id", "")
    if str(record_id).startswith("local_"):
        update_local_target(
            str(record_id),
            {
                "status": new_status,
                "sent_by": sent_by,
                "sent_time": datetime.now().isoformat(timespec="seconds"),
                "fail_reason": fail_reason,
            },
        )
    else:
        if not token:
            add_log("WARN", "system", str(record_id), "feishu_skip", "飞书不可用，无法回写飞书状态")
        else:
            update_target(
                token,
                str(record_id),
                {
                    "状态": new_status,
                    "发送账号": sent_by,
                    "发送时间": now_ms(),
                    "失败原因": fail_reason,
                },
            )


def _mark_target_replied(token: Optional[str], target_id: str, target_source: str, reply_preview: str) -> None:
    preview = str(reply_preview or "")[:500]
    if str(target_source or "local") == "local" and str(target_id).startswith("local_"):
        update_local_target(
            str(target_id),
            {
                "status": "已回复",
                "reply_content": preview,
            },
        )
        return

    if not token:
        add_log("WARN", "system", str(target_id), "feishu_skip", "飞书不可用，无法回写回复状态")
        return

    update_target(
        token,
        str(target_id),
        {
            "状态": "已回复",
            "回复内容": preview,
        },
    )


def _set_target_status_only(token: Optional[str], target_id: str, target_source: str, status: str) -> None:
    if str(target_source or "local") == "local" and str(target_id).startswith("local_"):
        update_local_target(str(target_id), {"status": status})
        return
    if not token:
        add_log("WARN", "system", str(target_id), "feishu_skip", f"飞书不可用，无法回写状态 {status}")
        return
    update_target(token, str(target_id), {"状态": status})


def _update_account_counts(token: Optional[str], account: dict, inc: int = 1) -> None:
    record_id = account.get("record_id") or account.get("id", "")
    now = datetime.now().isoformat(timespec="seconds")
    next_health = min(100, _account_health(account) + max(0, inc))
    daily_limit = _account_daily_limit(account)
    if str(record_id).startswith("local_"):
        update_local_account(
            str(record_id),
            {
                "today_sent": account.get("today_sent", 0) + inc,
                "total_sent": account.get("total_sent", 0) + inc,
                "health_score": next_health,
                "daily_limit_today": daily_limit,
                "last_action_time": now,
            },
        )
    elif token:
        try:
            update_account(
                token,
                str(record_id),
                {
                    "今日已发": account.get("today_sent", 0) + inc,
                    "累计发送": account.get("total_sent", 0) + inc,
                    "最后操作时间": now_ms(),
                },
            )
        except Exception:
            pass
        upsert_account_runtime(
            _account_key(account),
            {
                "health_score": next_health,
                "daily_limit_today": daily_limit,
                "last_action_time": now,
            },
        )

    account["today_sent"] = account.get("today_sent", 0) + inc
    account["total_sent"] = account.get("total_sent", 0) + inc
    account["health_score"] = next_health
    account["daily_limit_today"] = daily_limit
    account["last_action_time"] = now


def _set_account_abnormal(token: Optional[str], account: dict) -> None:
    record_id = account.get("record_id") or account.get("id", "")
    if str(record_id).startswith("local_"):
        update_local_account(str(record_id), {"status": "异常"})
    elif token:
        try:
            update_account(token, str(record_id), {"状态": "异常"})
        except Exception:
            pass


def _resolve_segment_targets(segment_id: str, token: Optional[str]) -> List[dict]:
    total = get_segment_target_count(segment_id)
    if total <= 0:
        return []

    # paginate read to avoid huge memory spikes
    page = 1
    page_size = 200
    rows: List[dict] = []
    while len(rows) < total:
        batch = get_segment_targets(segment_id, page=page, page_size=page_size)
        if not batch:
            break
        rows.extend(batch)
        page += 1

    local_ids = [r["target_id"] for r in rows if str(r.get("target_id", "")).startswith("local_")]
    local_map = {x["id"]: x for x in get_local_targets_by_ids(local_ids)}

    feishu_map: Dict[str, dict] = {}
    if token:
        try:
            all_feishu = get_all_targets(token)
            feishu_map = {x["record_id"]: x for x in all_feishu}
        except Exception as e:
            add_log("WARN", "system", "", "feishu_skip", f"读取飞书目标失败: {e}")

    out: List[dict] = []
    for row in rows:
        target_id = str(row.get("target_id", ""))
        if target_id.startswith("local_"):
            t = local_map.get(target_id)
            if not t or t.get("status") != "待发送":
                continue
            x = dict(t)
            x["record_id"] = x.get("id", target_id)
            x["_source"] = "local"
            out.append(x)
            continue

        t = feishu_map.get(target_id)
        if not t or t.get("status") != "待发送":
            continue
        x = dict(t)
        x["record_id"] = x.get("record_id", target_id)
        x["_source"] = "feishu"
        out.append(x)

    return out


def _select_accounts(all_accounts: List[dict], account_ids: List[str]) -> List[dict]:
    wanted = {str(x).strip() for x in account_ids if str(x).strip()}
    if not wanted:
        return []
    out: List[dict] = []
    for acc in all_accounts:
        record_id = str(acc.get("record_id") or acc.get("id") or "")
        profile_id = str(acc.get("profile_id") or "")
        if record_id in wanted or profile_id in wanted:
            out.append(acc)
    return out


def _resolve_followup_targets(candidates: List[dict], token: Optional[str]) -> Dict[str, dict]:
    local_ids = [str(x.get("target_id") or "") for x in candidates if str(x.get("target_source") or "local") == "local"]
    local_map = {x["id"]: x for x in get_local_targets_by_ids(local_ids)}

    feishu_map: Dict[str, dict] = {}
    if token:
        try:
            all_feishu = get_all_targets(token)
            feishu_map = {x["record_id"]: x for x in all_feishu}
        except Exception as exc:
            add_log("WARN", "system", "", "feishu_skip", f"自动跟进读取飞书目标失败: {exc}")

    resolved: Dict[str, dict] = {}
    for item in candidates:
        target_id = str(item.get("target_id") or "")
        source = str(item.get("target_source") or "local")
        if not target_id:
            continue
        if source == "local":
            target = local_map.get(target_id)
            if target:
                x = dict(target)
                x["record_id"] = x.get("id", target_id)
                x["_source"] = "local"
                resolved[target_id] = x
        else:
            target = feishu_map.get(target_id)
            if target:
                x = dict(target)
                x["record_id"] = x.get("record_id", target_id)
                x["_source"] = "feishu"
                resolved[target_id] = x
    return resolved


def preview_followups() -> dict:
    token, accounts = _fetch_all_accounts()
    account_map = {_account_key(x): x for x in accounts}
    candidates = get_followup_candidates(settings.followup_days, limit=50)
    target_map = _resolve_followup_targets(candidates, token)
    available_map = {_account_key(x): x for x in _available_accounts(accounts)}

    ready_count = 0
    skipped_missing = 0
    skipped_account = 0

    for conv in candidates:
        target = target_map.get(str(conv.get("target_id") or ""))
        account = account_map.get(str(conv.get("account_key") or ""))
        if not target or not account:
            skipped_missing += 1
            continue
        if _account_key(account) not in available_map:
            skipped_account += 1
            continue
        step = int(conv.get("next_sequence_step") or 0)
        if step not in {2, 3}:
            continue
        ready_count += 1

    return {
        "total_candidates": len(candidates),
        "ready_count": ready_count,
        "skipped_missing": skipped_missing,
        "skipped_account": skipped_account,
        "followup_days": int(settings.followup_days or 0),
        "message": "暂无满足条件的后续触达对象" if ready_count <= 0 else f"预计执行 {ready_count} 条后续触达",
    }


def _run_targets(
    targets: List[dict],
    accounts: List[dict],
    token: Optional[str],
    wait_between: bool = True,
    respect_switch: bool = True,
    batch_name: str = "batch",
    segment_id: str = "",
    segment_name: str = "",
    client_group: str = "",
    project_id: str = "",
) -> None:
    available = _available_accounts(accounts)
    _status["pending_targets"] = len(targets)
    _status["active_accounts"] = len(available)

    if is_circuit_tripped():
        add_log("WARN", "system", "", "circuit_open", f"{batch_name}: 熔断中，跳过本轮发送")
        return
    if not _is_business_hour():
        add_log("INFO", "system", "", "outside_business_hours", f"{batch_name}: 当前不在发送时段，跳过")
        return
    if not available:
        add_log("WARN", "system", "", "skip", f"{batch_name}: 无可用账号，本轮跳过")
        return
    if not targets:
        add_log("INFO", "system", "", "skip", f"{batch_name}: 无待发送目标，本轮跳过")
        return

    for target in targets:
        if respect_switch and (not _running or _paused):
            break

        username = target.get("twitter_username", "")
        project = target.get("project_name") or "your project"
        display_name = str(target.get("display_name") or "").strip()
        nickname = str(target.get("nickname") or "").strip()
        if not nickname and display_name:
            nickname = extract_nickname(display_name)
            record_id = str(target.get("record_id") or target.get("id", ""))
            if record_id.startswith("local_"):
                update_local_target(record_id, {"nickname": nickname})
        sequence_cfg = {
            "step_1_template_id": str(target.get("sequence_step_1_template_id") or target.get("template_id") or ""),
            "step_2_enabled": bool(target.get("sequence_step_2_enabled", target.get("followup_enabled", True))),
            "step_3_enabled": bool(target.get("sequence_step_3_enabled", target.get("followup_enabled", True))),
            "step_2_delay_days": max(1, int(target.get("sequence_step_2_delay_days") or 3)),
            "step_3_delay_days": max(1, int(target.get("sequence_step_3_delay_days") or 5)),
        }
        next_step, next_followup_at = _resolve_next_sequence_state(
            1,
            sequence_step_2_enabled=sequence_cfg["step_2_enabled"],
            sequence_step_3_enabled=sequence_cfg["step_3_enabled"],
            sequence_step_2_delay_days=sequence_cfg["step_2_delay_days"],
            sequence_step_3_delay_days=sequence_cfg["step_3_delay_days"],
        )

        attempts = 0
        completed = False
        last_error = ""
        last_used_account: Optional[dict] = None

        candidates = sorted(
            _available_accounts(available),
            key=lambda x: (x.get("today_sent", 0), -_account_health(x)),
        )
        for account in candidates:
            if attempts >= settings.max_retry_accounts_per_target:
                break

            attempts += 1
            acc_name = account.get("twitter_username", "") or str(account.get("profile_id", ""))
            profile_id = str(account.get("profile_id", ""))
            if not profile_id:
                continue

            message = generate(
                project,
                template_type=TEMPLATE_TYPE_STEP_1,
                handle=username,
                template_id=sequence_cfg["step_1_template_id"],
                nickname=nickname,
            )
            add_log("INFO", acc_name, username, "starting", f"{batch_name} 开始发送尝试#{attempts} -> @{username}")

            try:
                ws_url, _debug_port = start_browser(profile_id)
                result = send_dm(
                    ws_url=ws_url,
                    target_username=username,
                    message=message,
                    account_id=profile_id,
                    twitter_account=acc_name,
                    screenshot_dir=settings.screenshot_dir,
                )
                status = str(result.get("status", "error"))
                note = str(result.get("note", ""))
                last_used_account = account

                if status == "sent":
                    _mark_target_done(token, target, "已发送", sent_by=acc_name)
                    _update_account_counts(token, account, inc=1)
                    conversation_id = upsert_conversation_for_send(
                        target, account, message_preview=message,
                        sequence_step=1,
                        next_sequence_step=next_step,
                        next_followup_at=next_followup_at,
                        segment_id=segment_id, segment_name=segment_name,
                        client_group=client_group or str(target.get("client_group") or ""),
                        project_name=project,
                    )
                    _status["today_total_sent"] += 1
                    add_log("SUCCESS", acc_name, username, "sent", "发送成功", meta=result)
                    completed = True
                    break

                if status == "captcha":
                    _apply_account_health(
                        token,
                        account,
                        delta=-30,
                        cooldown_hours=settings.cooldown_hours,
                        force_abnormal=True,
                    )
                    add_log("WARN", acc_name, username, "captcha", "检测到风控信号，账号标记异常", meta=result)
                    record_account_failure(_account_key(account), f"captcha: {note or 'captcha'}")
                    last_error = note or "captcha"
                    continue

                if status in NON_RETRY_TARGET_STATUSES:
                    _mark_target_done(token, target, "不可DM", sent_by=acc_name, fail_reason=note or status)
                    add_log("INFO", acc_name, username, status, note or status, meta=result)
                    completed = True
                    break

                if status in RETRYABLE_STATUSES:
                    _apply_account_health(token, account, delta=-10)
                    add_log("WARN", acc_name, username, status, note or status, meta=result)
                    if status == "error":
                        record_account_failure(_account_key(account), f"{status}: {note or status}")
                    last_error = note or status
                    continue

                _apply_account_health(token, account, delta=-10)
                add_log("WARN", acc_name, username, status, note or "unknown_status", meta=result)
                if status == "error":
                    record_account_failure(_account_key(account), f"{status}: {note or status}")
                last_error = note or status

            except Exception as e:
                last_error = str(e)
                _apply_account_health(token, account, delta=-10)
                record_account_failure(_account_key(account), f"error: {last_error}")
                add_log("ERROR", acc_name, username, "error", last_error)

            finally:
                try:
                    stop_browser(profile_id)
                except Exception:
                    pass

        if not completed:
            _mark_target_done(
                token,
                target,
                "跳过",
                sent_by="",
                fail_reason=last_error or "multi_account_attempt_failed",
            )
            add_log("WARN", "system", username, "skipped", f"{batch_name} 多账号尝试失败: {last_error}")

        if wait_between and (not respect_switch or (_running and not _paused)):
            wait = random.randint(settings.min_interval_sec, settings.max_interval_sec)
            if last_used_account and _account_health(last_used_account) < HEALTH_SLOW_THRESHOLD:
                wait = int(wait * 1.5)
            add_log("INFO", "system", "", "waiting", f"等待 {wait // 60} 分钟后继续")
            time.sleep(wait)
        _status["pending_targets"] = max(0, _status.get("pending_targets", 0) - 1)


def auto_followup(wait_between: bool = True, trigger: str = "scheduled") -> dict:
    run_id = _begin_followup_run(trigger)
    summary = {
        "trigger": trigger,
        "total_candidates": 0,
        "ready_count": 0,
        "sent": 0,
        "skipped": 0,
        "closed": 0,
        "captcha": 0,
        "errors": 0,
        "message": "",
    }
    if not _running or _paused:
        summary["message"] = "系统未启动或已暂停"
        _finish_followup_run(run_id, summary)
        return summary
    if is_circuit_tripped():
        add_log("WARN", "system", "", "followup_skip", "熔断中，跳过自动跟进")
        summary["message"] = "熔断中，跳过自动跟进"
        _finish_followup_run(run_id, summary)
        return summary
    if not _is_business_hour():
        add_log("INFO", "system", "", "followup_skip", "当前不在营业时段，跳过自动跟进")
        summary["message"] = "当前不在发送时段"
        _finish_followup_run(run_id, summary)
        return summary
    if not _batch_lock.acquire(blocking=False):
        add_log("INFO", "system", "", "followup_skip", "发送任务繁忙，跳过自动跟进")
        summary["message"] = "发送任务繁忙，暂未执行"
        _finish_followup_run(run_id, summary)
        return summary

    try:
        token, accounts = _fetch_all_accounts()
        account_map = {_account_key(x): x for x in accounts}
        candidates = get_followup_candidates(settings.followup_days, limit=50)
        summary["total_candidates"] = len(candidates)
        if not candidates:
            add_log("INFO", "system", "", "followup_skip", "暂无满足条件的自动跟进目标")
            summary["message"] = "暂无满足条件的自动跟进目标"
            return summary

        target_map = _resolve_followup_targets(candidates, token)
        for conv in candidates:
            if not _running or _paused or is_circuit_tripped():
                break

            conv_id = str(conv.get("id") or "")
            target_id = str(conv.get("target_id") or "")
            target = target_map.get(target_id)
            account = account_map.get(str(conv.get("account_key") or ""))
            if not target or not account:
                add_log("WARN", "system", str(conv.get("target_username") or ""), "followup_skip", "跟进目标或账号不存在")
                summary["skipped"] += 1
                continue
            if account not in _available_accounts([account]):
                add_log("WARN", _account_name(account), str(conv.get("target_username") or ""), "followup_skip", "账号当前不可用于自动跟进")
                summary["skipped"] += 1
                continue

            username = str(conv.get("target_username") or target.get("twitter_username") or "")
            project = target.get("project_name") or "your project"
            acc_name = _account_name(account)
            profile_id = str(account.get("profile_id") or "")
            if not profile_id:
                continue

            step = int(conv.get("next_sequence_step") or 0)
            if step not in {2, 3}:
                summary["skipped"] += 1
                continue
            template_type = _sequence_template_type(step)
            template_id = ""
            next_step, next_followup_at = _resolve_next_sequence_state(
                step,
                sequence_step_2_enabled=True,
                sequence_step_3_enabled=True,
                sequence_step_2_delay_days=3,
                sequence_step_3_delay_days=5,
            )
            message = generate(project, template_type=template_type, handle=username, template_id=template_id)
            summary["ready_count"] += 1
            add_log("INFO", acc_name, username, "followup_starting", f"执行第 {step} 步触达")

            try:
                ws_url, _debug_port = start_browser(profile_id)
                result = send_dm(
                    ws_url=ws_url,
                    target_username=username,
                    message=message,
                    account_id=profile_id,
                    twitter_account=acc_name,
                    screenshot_dir=settings.screenshot_dir,
                )
                status = str(result.get("status", "error"))
                note = str(result.get("note", "") or "")

                if status == "sent":
                    _mark_target_done(token, target, "已发送", sent_by=acc_name)
                    _update_account_counts(token, account, inc=1)
                    conversation_id = upsert_conversation_for_send(
                        target, account, message_preview=message,
                        sequence_step=step,
                        next_sequence_step=next_step,
                        next_followup_at=next_followup_at,
                        segment_id=str(target.get("segment_id") or ""),
                        segment_name=str(target.get("segment_name") or ""),
                        project_name=project,
                    )
                    add_log("SUCCESS", acc_name, username, "followup_sent", f"第 {step} 步触达发送成功", meta=result)
                    summary["sent"] += 1
                elif status == "captcha":
                    _apply_account_health(
                        token,
                        account,
                        delta=-30,
                        cooldown_hours=settings.cooldown_hours,
                        force_abnormal=True,
                    )
                    record_account_failure(_account_key(account), f"followup_captcha: {note or 'followup_captcha'}")
                    add_log("WARN", acc_name, username, "followup_captcha", note or "followup_captcha", meta=result)
                    summary["captcha"] += 1
                elif status in NON_RETRY_TARGET_STATUSES:
                    _mark_target_done(token, target, "不可DM", sent_by=acc_name, fail_reason=note or status)
                    update_conversation(conv_id, {"status": "completed"})
                    add_log("INFO", acc_name, username, "followup_closed", note or status, meta=result)
                    summary["closed"] += 1
                else:
                    _apply_account_health(token, account, delta=-10)
                    if status == "error":
                        record_account_failure(_account_key(account), f"followup_{status}: {note or status}")
                    add_log("WARN", acc_name, username, "followup_error", note or status, meta=result)
                    summary["errors"] += 1
            except Exception as exc:
                _apply_account_health(token, account, delta=-10)
                record_account_failure(_account_key(account), f"followup_error: {str(exc)}")
                add_log("ERROR", acc_name, username, "followup_error", str(exc))
                summary["errors"] += 1
            finally:
                try:
                    stop_browser(profile_id)
                except Exception:
                    pass

            if wait_between and _running and not _paused:
                wait = random.randint(settings.min_interval_sec, settings.max_interval_sec)
                if _account_health(account) < HEALTH_SLOW_THRESHOLD:
                    wait = int(wait * 1.5)
                add_log("INFO", "system", "", "followup_waiting", f"自动跟进等待 {wait // 60} 分钟后继续")
                time.sleep(wait)
        summary["message"] = f"后续触达完成：发送 {summary['sent']}，跳过 {summary['skipped']}，关闭 {summary['closed']}，异常 {summary['errors']}"
        add_log("INFO", "system", "", "followup_summary", summary["message"], meta=summary)
        return summary
    finally:
        _batch_lock.release()
        _finish_followup_run(run_id, summary)


def check_replies(force: bool = False, include_replied: bool = False) -> None:
    tracked_map = _tracked_conversations_by_account(include_replied=include_replied)
    if not tracked_map:
        if force:
            add_log(
                "INFO",
                "system",
                "",
                "reply_skip",
                "暂无可同步会话" if include_replied else "暂无待检查会话",
            )
        return
    if not force and not _is_reply_check_window(include_replied):
        add_log(
            "INFO",
            "system",
            "",
            "reply_skip",
            f"{'全部同步' if include_replied else '普通同步'}当前不在执行时段，跳过",
        )
        return
    if _batch_lock.locked():
        add_log("INFO", "system", "", "reply_skip", "发送任务进行中，跳过本轮回复检测")
        return
    if not _reply_check_lock.acquire(blocking=False):
        add_log("INFO", "system", "", "reply_skip", "回复检测已在执行中")
        return

    try:
        total_tracked = sum(len(items) for items in tracked_map.values())
        add_log(
            "INFO",
            "system",
            "",
            "reply_check_start",
            f"{'开始全部同步' if include_replied else '开始普通同步'}，共 {len(tracked_map)} 个账号，{total_tracked} 个会话",
        )
        token, all_accounts = _fetch_all_accounts()
        matched_accounts = [
            account
            for account in all_accounts
            if _account_key(account) in tracked_map and str(account.get("profile_id") or "").strip()
        ]
        if not matched_accounts:
            return

        for account in matched_accounts:
            profile_id = str(account.get("profile_id") or "").strip()
            convs = tracked_map.get(_account_key(account), [])
            if not profile_id or not convs:
                continue
            conv_map = {str(x.get("id") or ""): x for x in convs}

            account_name = _account_name(account)
            group_labels = sorted(
                {
                    str(item.get("reply_check_group") or "").strip()
                    for item in convs
                    if str(item.get("reply_check_group") or "").strip()
                }
            )
            group_note = "；".join(group_labels[:3]) if group_labels else "未分组"
            add_log(
                "INFO",
                account_name,
                "",
                "reply_account_start",
                f"开始检查 {len(convs)} 个会话，归属 {group_note}",
            )
            try:
                ws_url, _debug_port = start_browser(profile_id)
                result = check_account_replies(
                    ws_url=ws_url,
                    account_id=profile_id,
                    twitter_account=account_name,
                    tracked_conversations=convs,
                    screenshot_dir=settings.screenshot_dir,
                )
                status = str(result.get("status", "ok"))
                note = str(result.get("note", "") or "")

                if status == "captcha":
                    _apply_account_health(
                        token,
                        account,
                        delta=-30,
                        cooldown_hours=settings.cooldown_hours,
                        force_abnormal=True,
                    )
                    record_account_failure(_account_key(account), f"reply_checker_captcha: {note or 'reply_checker_captcha'}")
                    add_log("WARN", account_name, "", "reply_captcha", note or "reply_checker_captcha", meta=result)
                    continue

                if status == "error":
                    _apply_account_health(token, account, delta=-10)
                    record_account_failure(_account_key(account), f"reply_checker_error: {note or 'reply_checker_error'}")
                    add_log("WARN", account_name, "", "reply_error", note or "reply_checker_error", meta=result)
                    continue

                if note:
                    add_log("INFO", account_name, "", "reply_scan_summary", note, meta={"checked": result.get("checked", 0)})

                for trace_item in result.get("trace_logs", []) or []:
                    trace = str(trace_item.get("trace") or "").strip()
                    target_username = str(trace_item.get("target_username") or "")
                    if not trace:
                        continue
                    add_log(
                        "INFO",
                        account_name,
                        target_username,
                        "reply_trace",
                        trace,
                        meta=trace_item,
                    )

                parsed_items = result.get("conversations", []) or []
                parsed_ids = set()
                found_ids = set()
                for item in parsed_items:
                    conversation_id = str(item.get("conversation_id") or "")
                    if not conversation_id:
                        continue
                    parsed_ids.add(conversation_id)
                    target_id = str(item.get("target_id") or "")
                    target_source = str(item.get("target_source") or "local")
                    target_username = str(item.get("target_username") or "")
                    box = str(item.get("box") or "inbox")
                    existing_conv = conv_map.get(conversation_id, {})
                    inserted = record_message_events(
                        conversation_id,
                        item.get("messages") or [],
                        last_box=box,
                    )
                    new_inbound = [x for x in inserted if str(x.get("direction") or "") == "inbound"]
                    if not new_inbound:
                        mark_conversation_checked(conversation_id, last_box=box)
                        continue
                    found_ids.add(conversation_id)
                    latest = new_inbound[-1]
                    preview = str(latest.get("content") or item.get("reply_preview") or "")
                    mark_conversation_reply(conversation_id, preview, last_box=box)
                    # AI reply analysis
                    try:
                        all_reply_texts = [
                            str(x.get("content") or "").strip()
                            for x in item.get("messages") or []
                            if str(x.get("direction") or "") == "inbound" and str(x.get("content") or "").strip()
                        ]
                        reply_text_for_analysis = "\n".join(all_reply_texts) if all_reply_texts else preview
                        analysis = analyze_reply(reply_text_for_analysis)
                        if analysis and analysis.get("summary"):
                            import json as _json
                            update_conversation(conversation_id, {
                                "reply_analysis": _json.dumps(analysis, ensure_ascii=False),
                                "extracted_email": str(analysis.get("email", "")),
                                "extracted_telegram": str(analysis.get("telegram", "")),
                                "extracted_pricing": str(analysis.get("pricing", "")),
                            })
                    except Exception:
                        pass
                    current_status = str(existing_conv.get("status", "") or "")
                    if current_status == "manual_takeover":
                        _set_target_status_only(token, target_id, target_source, "人工接管")
                    elif current_status == "completed":
                        _set_target_status_only(token, target_id, target_source, "完成")
                    else:
                        _mark_target_replied(token, target_id, target_source, preview)
                    add_log(
                        "SUCCESS",
                        account_name,
                        target_username,
                        "reply_detected",
                        f"{len(new_inbound)} 条新回复: {preview[:160]}",
                        meta={**item, "new_inbound_count": len(new_inbound)},
                    )

                for conv in convs:
                    conv_id = str(conv.get("id") or "")
                    if conv_id and conv_id not in parsed_ids:
                        mark_conversation_checked(conv_id)

                if found_ids:
                    _notify_pending_replies()

            except Exception as exc:
                _apply_account_health(token, account, delta=-10)
                record_account_failure(_account_key(account), f"reply_checker_error: {str(exc)}")
                add_log("WARN", account_name, "", "reply_error", str(exc))
            finally:
                try:
                    stop_browser(profile_id)
                except Exception:
                    pass
    finally:
        _reply_check_lock.release()


def run_batch(wait_between: bool = True, use_warming: bool = True):
    if not _running or _paused:
        return

    if not _batch_lock.acquire(blocking=False):
        add_log("WARN", "system", "", "busy", "run_batch skipped: another batch is running")
        return

    try:
        token, accounts = _fetch_all_accounts()
        targets = _fetch_pending_targets(token)

        # 如果启用预热，筛选已预热的目标并为未预热的目标创建预热任务
        if use_warming:
            warmed_targets = []
            unwarmed_targets = []

            for target in targets:
                target_id = target.get("record_id") or target.get("id", "")
                if is_target_warmed(target_id):
                    warmed_targets.append(target)
                else:
                    unwarmed_targets.append(target)

            # 为未预热的高价值目标创建预热任务
            if unwarmed_targets:
                # 筛选高价值目标（高优先级或KOL）
                high_value = [
                    t for t in unwarmed_targets
                    if t.get("priority") == "高" or t.get("kol_tier") in ["头部", "腰部"]
                ]

                if high_value:
                    scheduled_count = schedule_warming_for_targets(high_value, hours_before=6)
                    add_log("INFO", "system", "", "warming_scheduled",
                            f"为 {scheduled_count} 个高价值目标创建预热任务，6小时后发送")

                # 其他目标直接发送（不预热）
                warmed_targets.extend([
                    t for t in unwarmed_targets
                    if t not in high_value
                ])

            targets = warmed_targets

        _run_targets(targets, accounts, token, wait_between=wait_between, respect_switch=True, batch_name="batch")
    except Exception as e:
        add_log("ERROR", "system", "", "error", f"run_batch_failed: {e}")
    finally:
        _batch_lock.release()


def run_batch_for_segment(segment_id: str, account_ids: List[str], wait_between: bool = True, client_group: str = ""):
    if not _batch_lock.acquire(blocking=False):
        add_log("WARN", "system", "", "busy", "segment_run skipped: another batch is running")
        return

    try:
        seg_info = get_segment(segment_id) or {}
        seg_name = str(seg_info.get("name") or segment_id)

        token, all_accounts = _fetch_all_accounts()
        selected_accounts = _select_accounts(all_accounts, account_ids)
        targets = _resolve_segment_targets(segment_id, token)

        if not selected_accounts:
            add_log("WARN", "system", segment_id, "skip", "人群包分发失败：未选到可用账号")
            return
        if not targets:
            add_log("INFO", "system", segment_id, "skip", "人群包内暂无待发送目标")
            return

        _run_targets(
            targets=targets,
            accounts=selected_accounts,
            token=token,
            wait_between=wait_between,
            respect_switch=False,
            batch_name=f"segment:{seg_name}",
            segment_id=segment_id,
            segment_name=seg_name,
            client_group=client_group,
        )
    except Exception as e:
        add_log("ERROR", "system", segment_id, "error", f"run_batch_for_segment_failed: {e}")
    finally:
        _batch_lock.release()
