from __future__ import annotations

import re
from typing import Dict

from config import settings

_cache: Dict[str, str] = {}

_FALLBACK_CN_RE = re.compile(r"[\u4e00-\u9fff]+")
_STRIP_RE = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]")


def extract_nickname(display_name: str) -> str:
    if not display_name or not display_name.strip():
        return ""

    key = display_name.strip()
    if key in _cache:
        return _cache[key]

    nickname = ""
    api_key = settings.openai_api_key or ""
    if api_key:
        try:
            nickname = _call_openai(key)
        except Exception:
            nickname = ""

    if not nickname:
        nickname = _fallback(key)

    _cache[key] = nickname
    return nickname


def _call_openai(display_name: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        return ""

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model=settings.openai_model or "gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "你是一个昵称提取助手。用户会给你一个 Twitter 显示名（可能包含中文、英文、数字、emoji等）。"
                    "你需要从中提取一个 2-4 个字的自然、友好的中文昵称或英文名。"
                    "只返回昵称本身，不要加任何标点、解释或多余内容。\n"
                    "示例：\n"
                    "- 早睡大赛MVP → 早睡\n"
                    "- Crypto Alice 🌙 → Alice\n"
                    "- 王小明同学 → 小明\n"
                    "- DeFi探索者David → David\n"
                    "- 月光下的猫 → 月光\n"
                ),
            },
            {"role": "user", "content": display_name},
        ],
        max_tokens=16,
        temperature=0,
    )
    text = (resp.choices[0].message.content or "").strip()
    if len(text) > 10:
        text = text[:10]
    return text


def _fallback(display_name: str) -> str:
    cn_parts = _FALLBACK_CN_RE.findall(display_name)
    if cn_parts:
        combined = "".join(cn_parts)
        return combined[:min(3, len(combined))]

    stripped = _STRIP_RE.findall(display_name)
    if stripped:
        return "".join(stripped)[:min(4, len(stripped))]

    return display_name[:3]
