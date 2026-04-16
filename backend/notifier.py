from __future__ import annotations

from typing import Iterable

import requests

from config import settings


def _send_feishu_text(webhook: str, text: str) -> bool:
    target = str(webhook or "").strip()
    if not target:
        return False
    resp = requests.post(
        target,
        timeout=15,
        json={
            "msg_type": "text",
            "content": {"text": str(text or "").strip() or "-"},
        },
    )
    resp.raise_for_status()
    return True


def send_feishu_reply_notification(
    client_group: str,
    account_name: str,
    target_username: str,
    reply_messages: Iterable[str],
    box: str = "inbox",
) -> bool:
    webhook = str(settings.feishu_notify_webhook or "").strip()
    if not webhook:
        return False

    messages = []
    for raw in reply_messages or []:
        text = str(raw or "").strip()
        if not text:
            continue
        if len(text) > 180:
            text = text[:177] + "..."
        messages.append(text)
    if not messages:
        messages = ["-"]

    if len(messages) == 1:
        content_block = f"内容: {messages[0]}"
    else:
        joined = "\n".join(f"{idx}. {text}" for idx, text in enumerate(messages[:5], start=1))
        if len(messages) > 5:
            joined += f"\n... 共 {len(messages)} 条新消息"
        content_block = f"内容({len(messages)}条):\n{joined}"

    text = (
        f"检测到新的 X 回复\n"
        f"归属: {client_group or '-'}\n"
        f"账号: {account_name or '-'}\n"
        f"目标: @{target_username or '-'}\n"
        f"位置: {box}\n"
        f"{content_block}"
    )
    return _send_feishu_text(webhook, text)


def send_feishu_test_message(webhook: str) -> bool:
    return _send_feishu_text(
        webhook,
        "Twitter DM System 测试消息\n"
        "类型: 飞书机器人连通性测试\n"
        "结果: webhook 已成功接收请求",
    )


def send_feishu_alert_notification(alert_type: str, message: str) -> bool:
    """发送系统警报通知（熔断等）"""
    webhook = str(settings.feishu_notify_webhook or "").strip()
    if not webhook:
        return False

    text = (
        f"【Twitter DM System 系统警报】\n"
        f"类型: {alert_type}\n"
        f"{message}"
    )
    return _send_feishu_text(webhook, text)
