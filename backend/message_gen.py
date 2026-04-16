from __future__ import annotations

import random
from typing import Dict, List, Optional

from database import get_templates

TEMPLATE_TYPE_STEP_1 = "sequence_step_1"
TEMPLATE_TYPE_STEP_2 = "sequence_step_2"
TEMPLATE_TYPE_STEP_3 = "sequence_step_3"

TEMPLATE_TYPE_ALIASES = {
    "first_contact": TEMPLATE_TYPE_STEP_1,
    "followup": TEMPLATE_TYPE_STEP_2,
    TEMPLATE_TYPE_STEP_1: TEMPLATE_TYPE_STEP_1,
    TEMPLATE_TYPE_STEP_2: TEMPLATE_TYPE_STEP_2,
    TEMPLATE_TYPE_STEP_3: TEMPLATE_TYPE_STEP_3,
}

DEFAULT_TEMPLATE_LIBRARY: Dict[str, List[str]] = {
    TEMPLATE_TYPE_STEP_1: [
        "Hi {name}，看到你们在做 {project}，{hook}，有没有机会聊聊？",
        "Hey {name}，{hook}，对 {project} 很感兴趣，想跟你们对接一下",
        "{name} 你好，{hook}，关于 {project} 这边有些想法想沟通",
        "Hi {name}，{hook}，一直在关注 {project}，看有没有合作空间",
        "Hey {name}，{hook}，想了解下 {project} 这边的合作方式",
    ],
    TEMPLATE_TYPE_STEP_2: [
        "Hi {name}，补一条关于 {project} 的信息，{personalized_hook}，方便的时候可以看下。",
        "Hey {name}，上次给你留过言，这边再补充下 {project} 的合作方向，{personalized_hook}。",
        "{name} 你好，延续上次的话题，{project} 这边如果你有兴趣，我可以把合作思路发你。",
    ],
    TEMPLATE_TYPE_STEP_3: [
        "Hi {name}，最后补一条，如果你对 {project} 方向感兴趣，我这边可以配合进一步沟通。",
        "Hey {name}，再确认一次，关于 {project} 如需进一步信息，我随时可以补充。",
        "{name} 你好，这边做个收口，若 {project} 方向适合你，我们可以继续对接。",
    ],
}

DEFAULT_TEMPLATES = [item for bucket in DEFAULT_TEMPLATE_LIBRARY.values() for item in bucket]

HOOKS = [
    "最近深入研究了你们的产品",
    "在社区看到不少关于你们的讨论",
    "觉得你们做的方向很有意思",
    "关注你们有一段时间了",
    "朋友推荐了解了下你们",
    "刚看了你们最新的公告",
]

NAMES = ["", "bro", ""]


class _SafeFormatDict(dict):
    def __missing__(self, key):
        return ""


def _normalize_template_type(value: str) -> str:
    return TEMPLATE_TYPE_ALIASES.get(str(value or "").strip(), TEMPLATE_TYPE_STEP_1)


def _active_template_pool(template_type: str = TEMPLATE_TYPE_STEP_1) -> List[str]:
    wanted = _normalize_template_type(template_type)
    custom = []
    for t in get_templates():
        if int(t.get("active", 1)) != 1 or not t.get("content"):
            continue
        current_type = _normalize_template_type(str(t.get("template_type", TEMPLATE_TYPE_STEP_1)))
        if current_type == wanted:
            custom.append(str(t["content"]))
    if custom:
        return custom
    return DEFAULT_TEMPLATE_LIBRARY.get(wanted, DEFAULT_TEMPLATE_LIBRARY[TEMPLATE_TYPE_STEP_1])


def _template_content_by_id(template_id: str, template_type: str = TEMPLATE_TYPE_STEP_1) -> Optional[str]:
    wanted_id = str(template_id or "").strip()
    if not wanted_id:
        return None
    wanted_type = _normalize_template_type(template_type)
    for item in get_templates():
        if str(item.get("id") or "") != wanted_id:
            continue
        if int(item.get("active", 1) or 0) != 1:
            return None
        current_type = _normalize_template_type(str(item.get("template_type", TEMPLATE_TYPE_STEP_1)))
        if current_type != wanted_type:
            return None
        return str(item.get("content") or "").strip() or None
    return None


def generate(project: str, template_type: str = TEMPLATE_TYPE_STEP_1, handle: str = "", template_id: str = "") -> str:
    hook = random.choice(HOOKS)
    template = _template_content_by_id(template_id, template_type=template_type)
    if not template:
        template = random.choice(_active_template_pool(template_type=template_type))
    msg = template.format_map(
        _SafeFormatDict(
            name=random.choice(NAMES),
            project=(project or "your project"),
            hook=hook,
            personalized_hook=hook,
            handle=handle,
        )
    ).strip()
    return " ".join(msg.split())
