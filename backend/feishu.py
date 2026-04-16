from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from config import settings

BASE_URL = "https://open.feishu.cn/open-apis"
ACCOUNT_STATUS_NORMAL = "正常"
ACCOUNT_STATUS_ERROR = "异常"


class FeishuError(RuntimeError):
    pass


def _request(method: str, url: str, **kwargs) -> dict:
    resp = requests.request(method, url, timeout=30, **kwargs)
    resp.raise_for_status()
    data = resp.json()
    code = data.get("code", 0)
    if code not in (0, "0"):
        raise FeishuError(f"Feishu API error code={code}, msg={data.get('msg')}, url={url}")
    return data


def get_token() -> str:
    if not settings.feishu_app_id or not settings.feishu_app_secret:
        raise FeishuError("Feishu 未配置 app_id/app_secret")
    data = _request(
        "POST",
        f"{BASE_URL}/auth/v3/tenant_access_token/internal",
        json={"app_id": settings.feishu_app_id, "app_secret": settings.feishu_app_secret},
    )
    token = data.get("tenant_access_token", "")
    if not token:
        raise FeishuError("Feishu tenant_access_token missing")
    return token


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _list_records(token: str, table_id: str, page_size: int = 100, filter_expr: str = "", sort_json: str = "") -> list:
    url = f"{BASE_URL}/bitable/v1/apps/{settings.feishu_app_token}/tables/{table_id}/records"
    page_token = ""
    all_items: List[dict] = []

    while True:
        params: Dict[str, Any] = {"page_size": page_size}
        if filter_expr:
            params["filter"] = filter_expr
        if sort_json:
            params["sort"] = sort_json
        if page_token:
            params["page_token"] = page_token

        data = _request("GET", url, headers=_headers(token), params=params)
        payload = data.get("data", {})
        items = payload.get("items", [])
        all_items.extend(items)

        if not payload.get("has_more"):
            break
        page_token = payload.get("page_token", "")
        if not page_token:
            break

    return all_items


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        if not value:
            return ""
        first = value[0]
        if isinstance(first, dict):
            return str(first.get("text") or first.get("name") or first.get("value") or "")
        return str(first)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or value.get("value") or "")
    return str(value)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if isinstance(value, list) and value:
            value = value[0]
        return int(value)
    except Exception:
        return default


def _normalize_account_status(value: Any) -> str:
    return ACCOUNT_STATUS_NORMAL if _as_text(value).strip() == ACCOUNT_STATUS_NORMAL else ACCOUNT_STATUS_ERROR


def _parse_target(item: dict) -> dict:
    f = item.get("fields", {})
    return {
        "record_id": item.get("record_id", ""),
        "twitter_username": _as_text(f.get("Twitter用户名")).replace("@", "").strip(),
        "type": _as_text(f.get("类型")),
        "project_name": _as_text(f.get("项目名")),
        "priority": _as_text(f.get("优先级")) or "中",
        "status": _as_text(f.get("状态")) or "待发送",
        "sent_by": _as_text(f.get("发送账号")),
        "sent_time": f.get("发送时间"),
        "reply_content": _as_text(f.get("回复内容")),
        "fail_reason": _as_text(f.get("失败原因")),
        "note": _as_text(f.get("备注")),
        "language": _as_text(f.get("语言")),
        "source": _as_text(f.get("来源渠道")),
        "tags": _as_text(f.get("标签")),
        "followers": _as_int(f.get("粉丝数"), 0),
        "kol_tier": _as_text(f.get("KOL量级")),
        "content_type": _as_text(f.get("内容方向")),
        "track": _as_text(f.get("赛道偏好")),
        "cooperation": _as_text(f.get("合作意向")),
        "chain": _as_text(f.get("所属链")),
        "stage": _as_text(f.get("项目阶段")),
        "project_type": _as_text(f.get("项目类型")),
        "contact_role": _as_text(f.get("联系人角色")),
        "raw": item,
    }


def _parse_account(item: dict) -> dict:
    f = item.get("fields", {})
    return {
        "record_id": item.get("record_id", ""),
        "profile_id": _as_text(f.get("账号ID")),
        "twitter_username": _as_text(f.get("Twitter用户名")).replace("@", "").strip(),
        "status": _normalize_account_status(f.get("状态")),
        "today_sent": _as_int(f.get("今日已发"), 0),
        "total_sent": _as_int(f.get("累计发送"), 0),
        "bound_ip": _as_text(f.get("绑定IP")),
        "health_score": _as_int(f.get("健康分"), 100),
        "cooldown_until": _as_text(f.get("冷却到")),
        "daily_limit_today": _as_int(f.get("今日上限"), 0),
        "last_action_time": f.get("最后操作时间"),
        "raw": item,
    }


def get_pending_targets(token: str) -> list:
    items = _list_records(
        token,
        settings.feishu_table_targets,
        page_size=100,
        filter_expr='CurrentValue.[状态] = "待发送"',
        sort_json='[{"field_name":"优先级","desc":false}]',
    )
    return [t for t in (_parse_target(x) for x in items) if t["twitter_username"]]


def get_all_targets(token: str) -> list:
    items = _list_records(token, settings.feishu_table_targets, page_size=200)
    return [t for t in (_parse_target(x) for x in items) if t["twitter_username"]]


def get_all_accounts(token: str) -> list:
    items = _list_records(token, settings.feishu_table_accounts, page_size=100)
    return [a for a in (_parse_account(x) for x in items) if a["profile_id"]]


def update_target(token: str, record_id: str, fields: dict):
    url = f"{BASE_URL}/bitable/v1/apps/{settings.feishu_app_token}/tables/{settings.feishu_table_targets}/records/{record_id}"
    _request("PUT", url, headers=_headers(token), json={"fields": fields})


def update_account(token: str, record_id: str, fields: dict):
    url = f"{BASE_URL}/bitable/v1/apps/{settings.feishu_app_token}/tables/{settings.feishu_table_accounts}/records/{record_id}"
    _request("PUT", url, headers=_headers(token), json={"fields": fields})


def reset_daily_counts(token: str, accounts: list):
    for acc in accounts:
        update_account(token, acc["record_id"], {"今日已发": 0})


def now_ms() -> int:
    return int(datetime.now().timestamp() * 1000)
