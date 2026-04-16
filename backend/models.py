from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class AccountStatus(str, Enum):
    active = "正常"
    error = "异常"


class TargetStatus(str, Enum):
    pending = "待发送"
    sent = "已发送"
    replied = "已回复"
    skipped = "跳过"
    no_dm = "不可DM"


class TargetType(str, Enum):
    kol = "KOL"
    project = "项目方"


class Priority(str, Enum):
    high = "高"
    medium = "中"
    low = "低"


class Account(BaseModel):
    record_id: str
    profile_id: str
    twitter_username: str
    status: AccountStatus = AccountStatus.active
    today_sent: int = 0
    total_sent: int = 0
    bound_ip: str = ""
    last_action_time: Optional[datetime] = None


class Target(BaseModel):
    record_id: str
    twitter_username: str
    type: str = ""
    project_name: str = ""
    priority: Priority = Priority.medium
    status: TargetStatus = TargetStatus.pending
    sent_by: str = ""
    sent_time: Optional[datetime] = None
    fail_reason: str = ""
    note: str = ""


class Template(BaseModel):
    id: str
    content: str
    description: str = ""


class DMResult(BaseModel):
    account_id: str
    twitter_account: str
    target: str
    status: str
    message_preview: str = ""
    timestamp: datetime
    note: str = ""


class SystemStatus(BaseModel):
    running: bool
    paused: bool
    active_accounts: int
    today_total_sent: int
    pending_targets: int
    next_run_time: Optional[str] = None
    last_sync_time: Optional[str] = None
