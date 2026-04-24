from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from config import settings

_cache: Dict[str, dict] = {}


def analyze_reply(reply_text: str) -> dict:
    if not reply_text or not reply_text.strip():
        return _empty_result()

    key = reply_text.strip()
    if key in _cache:
        return _cache[key]

    result = _empty_result()
    api_key = settings.openai_api_key or ""
    if api_key:
        try:
            result = _call_openai(key)
        except Exception:
            pass

    if not result.get("summary"):
        result = _regex_fallback(key)

    _cache[key] = result
    return result


def _empty_result() -> dict:
    return {
        "email": "",
        "telegram": "",
        "pricing": "",
        "intent": "unknown",
        "summary": "",
    }


def _call_openai(reply_text: str) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        return _empty_result()

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model=settings.openai_model or "gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "你是一个信息提取助手。用户会给你一段 Twitter DM 的回复文本。"
                    "请从中提取以下信息，返回 JSON 格式：\n"
                    '- "email": 邮箱地址，没有则为空字符串\n'
                    '- "telegram": Telegram 用户名（含@），没有则为空字符串\n'
                    '- "pricing": 报价/价格信息，没有则为空字符串\n'
                    '- "intent": 意向判断，取值 "interested" / "not_interested" / "pending"\n'
                    '- "summary": 一句话摘要\n'
                    "只返回 JSON，不要加任何其他内容。"
                ),
            },
            {"role": "user", "content": reply_text},
        ],
        max_tokens=256,
        temperature=0,
    )
    text = (resp.choices[0].message.content or "").strip()
    try:
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        return json.loads(text)
    except json.JSONDecodeError:
        return _empty_result()


def _regex_fallback(reply_text: str) -> dict:
    result = _empty_result()
    result["summary"] = reply_text[:100]

    email_re = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    m = email_re.search(reply_text)
    if m:
        result["email"] = m.group(0)

    tg_re = re.compile(r"(?:@|t\.me/)([a-zA-Z0-9_]{5,32})")
    m = tg_re.search(reply_text)
    if m:
        result["telegram"] = "@" + m.group(1)

    price_re = re.compile(r"\$?\d{1,6}(?:[.,]\d{1,2})?\s*(?:USDT?|ETH|BTC|SOL|BNB|美元|刀|U)", re.IGNORECASE)
    m = price_re.search(reply_text)
    if m:
        result["pricing"] = m.group(0)

    lower = reply_text.lower()
    if any(w in lower for w in ["yes", "sure", "ok", "好的", "可以", "感兴趣", "合作", "没问题"]):
        result["intent"] = "interested"
    elif any(w in lower for w in ["no", "不", "don't", "别", "不需要", "没兴趣"]):
        result["intent"] = "not_interested"
    else:
        result["intent"] = "pending"

    return result


def analyze_replies_batch(items: List[Dict[str, str]]) -> List[dict]:
    return [analyze_reply(item.get("reply_text", "")) for item in items]
