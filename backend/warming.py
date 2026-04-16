"""
发前预热系统 (Warming)

PRD 要求:
- 发DM前先关注+互动，降低进入 Message Requests 的概率
- T-24h ~ T-6h: 关注目标账号
- T-6h ~ T-1h: 在目标最近推文下点赞
- 使用独立任务队列，可追踪状态

技术方案:
- 创建 warming_tasks 表存储预热任务
- 定时执行预热任务
- 预热完成后才允许发送DM
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from playwright.sync_api import Page, sync_playwright

from adspower import start_browser, stop_browser
from config import settings
from database import add_log, get_conn
from playwright_agent import _check_risk_signals, _goto_with_retry, _snapshot, _wait_logged_in


class WarmingTask:
    """预热任务"""
    def __init__(self, task_id: str, target_id: str, target_username: str,
                 task_type: str, status: str = "pending", scheduled_at: Optional[str] = None):
        self.id = task_id
        self.target_id = target_id
        self.target_username = target_username
        self.task_type = task_type  # follow, like
        self.status = status
        self.scheduled_at = scheduled_at or datetime.now().isoformat(timespec="seconds")
        self.executed_at: Optional[str] = None
        self.screenshot_path: str = ""
        self.error_message: str = ""


def init_warming_table():
    """初始化预热任务表"""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS warming_tasks (
                id TEXT PRIMARY KEY,
                target_id TEXT NOT NULL,
                target_source TEXT DEFAULT 'local',
                target_username TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                task_type TEXT DEFAULT 'follow',
                scheduled_at TEXT NOT NULL,
                executed_at TEXT DEFAULT '',
                screenshot_path TEXT DEFAULT '',
                error_message TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_warming_status ON warming_tasks(status)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_warming_scheduled ON warming_tasks(scheduled_at)
        """)


def schedule_warming_for_target(target: Dict[str, Any], hours_before: int = 12) -> Optional[str]:
    """
    为目标创建预热任务
    返回: 任务ID 或 None
    """
    target_id = target.get("record_id") or target.get("id", "")
    target_source = target.get("_source", "local")
    username = target.get("twitter_username", "")

    if not target_id or not username:
        return None

    now = datetime.now()
    scheduled_time = now + timedelta(hours=hours_before)

    # 创建关注任务
    follow_task_id = f"warm_follow_{target_id}_{int(now.timestamp())}"

    with get_conn() as conn:
        # 检查是否已有待执行的预热任务
        existing = conn.execute(
            """SELECT id FROM warming_tasks 
               WHERE target_id = ? AND status = 'pending' AND task_type = 'follow'""",
            (target_id,)
        ).fetchone()

        if existing:
            return None  # 已有预热任务

        conn.execute(
            """
            INSERT INTO warming_tasks 
            (id, target_id, target_source, target_username, status, task_type, scheduled_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'pending', 'follow', ?, ?, ?)
            """,
            (follow_task_id, target_id, target_source, username,
             scheduled_time.isoformat(timespec="seconds"),
             now.isoformat(timespec="seconds"),
             now.isoformat(timespec="seconds"))
        )

    add_log("INFO", "system", username, "warming_scheduled",
            f"预热任务已创建，计划执行时间: {scheduled_time.strftime('%Y-%m-%d %H:%M')}")

    return follow_task_id


def schedule_warming_for_targets(targets: List[Dict[str, Any]], hours_before: int = 12) -> int:
    """批量创建预热任务"""
    count = 0
    for target in targets:
        if schedule_warming_for_target(target, hours_before):
            count += 1
    return count


def _do_follow(page: Page, username: str) -> Dict[str, Any]:
    """执行关注操作"""
    result = {"success": False, "error": "", "screenshot": ""}

    try:
        # 访问目标主页
        page.goto(f"https://x.com/{username}", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)

        # 查找关注按钮
        follow_selectors = [
            '[data-testid="FollowButton"]',
            'button:has-text("Follow")',
            'button:has-text("关注")',
        ]

        follow_btn = None
        for sel in follow_selectors:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                follow_btn = loc
                break

        if not follow_btn:
            # 可能已经关注了
            unfollow_selectors = [
                '[data-testid="unfollowButton"]',
                'button:has-text("Following")',
                'button:has-text("正在关注")',
            ]
            for sel in unfollow_selectors:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    result["success"] = True
                    result["note"] = "already_following"
                    return result

            result["error"] = "关注按钮未找到"
            return result

        # 点击关注
        follow_btn.click(timeout=5000)
        page.wait_for_timeout(1500)

        result["success"] = True

    except Exception as e:
        result["error"] = str(e)

    return result


def _do_like(page: Page, username: str) -> Dict[str, Any]:
    """执行点赞操作（点赞最近一条推文）"""
    result = {"success": False, "error": "", "screenshot": ""}

    try:
        # 已经在目标主页，查找推文点赞按钮
        like_selectors = [
            '[data-testid="like"]',
            '[data-testid="unlike"]',  # 已点赞
        ]

        like_btn = None
        for sel in like_selectors:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                like_btn = loc
                break

        if not like_btn:
            result["error"] = "点赞按钮未找到"
            return result

        # 检查是否已经点赞
        if page.locator('[data-testid="unlike"]').count() > 0:
            result["success"] = True
            result["note"] = "already_liked"
            return result

        # 点击点赞
        like_btn.click(timeout=5000)
        page.wait_for_timeout(1000)

        result["success"] = True

    except Exception as e:
        result["error"] = str(e)

    return result


def execute_warming_task(task: WarmingTask, account: Dict[str, Any]) -> bool:
    """
    执行单个预热任务
    返回: 是否成功
    """
    profile_id = account.get("profile_id", "")
    username = task.target_username

    if not profile_id:
        return False

    acc_name = account.get("twitter_username", "") or profile_id
    now = datetime.now().isoformat(timespec="seconds")

    add_log("INFO", acc_name, username, "warming_start",
            f"开始预热任务: {task.task_type}")

    try:
        ws_url, _ = start_browser(profile_id)

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(ws_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()

            # 检查登录状态
            _goto_with_retry(page, "https://x.com/home", attempts=2, timeout=20000)
            page.wait_for_timeout(1000)

            if not _wait_logged_in(page, timeout_ms=6000):
                raise RuntimeError("未登录")

            if _check_risk_signals(page):
                raise RuntimeError("风控信号检测")

            # 执行对应操作
            if task.task_type == "follow":
                result = _do_follow(page, username)
            elif task.task_type == "like":
                result = _do_like(page, username)
            else:
                result = {"success": False, "error": "未知任务类型"}

            # 截图
            screenshot_path = f"{settings.screenshot_dir}/warming_{task.task_type}_{username}_{int(datetime.now().timestamp())}.png"
            try:
                page.screenshot(path=screenshot_path)
                task.screenshot_path = screenshot_path
            except Exception:
                pass

            browser.close()

            # 更新任务状态
            if result.get("success"):
                task.status = "completed"
                add_log("SUCCESS", acc_name, username, "warming_completed",
                        f"预热完成: {task.task_type}", meta=result)

                # 如果关注成功，创建点赞任务（延后 2-6 小时）
                if task.task_type == "follow" and result.get("note") != "already_following":
                    like_scheduled = (datetime.now() + timedelta(hours=random.randint(2, 6)))
                    like_task_id = f"warm_like_{task.target_id}_{int(datetime.now().timestamp())}"

                    with get_conn() as conn:
                        conn.execute(
                            """
                            INSERT INTO warming_tasks 
                            (id, target_id, target_source, target_username, status, task_type, scheduled_at, created_at, updated_at)
                            SELECT ?, target_id, target_source, target_username, 'pending', 'like', ?, ?, ?
                            FROM warming_tasks WHERE id = ?
                            """,
                            (like_task_id, like_scheduled.isoformat(timespec="seconds"),
                             now, now, task.id)
                        )

                    add_log("INFO", acc_name, username, "warming_like_scheduled",
                            f"点赞任务已创建，计划: {like_scheduled.strftime('%Y-%m-%d %H:%M')}")

            else:
                task.status = "failed"
                task.error_message = result.get("error", "未知错误")
                add_log("WARN", acc_name, username, "warming_failed",
                        f"预热失败: {result.get('error')}", meta=result)

    except Exception as e:
        task.status = "failed"
        task.error_message = str(e)
        add_log("ERROR", acc_name, username, "warming_error", str(e))

    finally:
        try:
            stop_browser(profile_id)
        except Exception:
            pass

        # 更新数据库
        task.executed_at = now
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE warming_tasks 
                SET status = ?, executed_at = ?, screenshot_path = ?, error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (task.status, task.executed_at, task.screenshot_path, task.error_message, now, task.id)
            )

    return task.status == "completed"


def run_warming_batch(limit: int = 20) -> int:
    """
    执行一批到期的预热任务
    返回: 成功执行的任务数
    """
    now = datetime.now().isoformat(timespec="seconds")

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM warming_tasks 
            WHERE status = 'pending' AND scheduled_at <= ?
            ORDER BY scheduled_at ASC
            LIMIT ?
            """,
            (now, limit)
        ).fetchall()

    if not rows:
        return 0

    tasks = [WarmingTask(
        task_id=r["id"],
        target_id=r["target_id"],
        target_username=r["target_username"],
        task_type=r["task_type"],
        status=r["status"],
        scheduled_at=r["scheduled_at"]
    ) for r in rows]

    # 获取可用账号
    from database import get_local_accounts
    from feishu import get_token, get_all_accounts

    try:
        token = get_token()
        feishu_accounts = get_all_accounts(token)
    except Exception:
        feishu_accounts = []
        token = None

    local_accounts = get_local_accounts()
    all_accounts = feishu_accounts + local_accounts
    available = [a for a in all_accounts if a.get("status") == "正常"]

    if not available:
        add_log("WARN", "system", "", "warming_skip", "无可用账号执行预热")
        return 0

    # 轮询分配任务
    success_count = 0
    for i, task in enumerate(tasks):
        account = available[i % len(available)]
        if execute_warming_task(task, account):
            success_count += 1

    add_log("INFO", "system", "", "warming_batch",
            f"预热批次完成: {success_count}/{len(tasks)}")

    return success_count


def is_target_warmed(target_id: str) -> bool:
    """检查目标是否已完成预热（关注和点赞）"""
    with get_conn() as conn:
        # 检查是否有已完成的关注任务
        follow = conn.execute(
            """SELECT status FROM warming_tasks 
               WHERE target_id = ? AND task_type = 'follow' AND status = 'completed'""",
            (target_id,)
        ).fetchone()

        if not follow:
            return False

        # 检查是否有已完成的点赞任务，或点赞任务不存在（有些目标不需要点赞）
        like = conn.execute(
            """SELECT status FROM warming_tasks 
               WHERE target_id = ? AND task_type = 'like'""",
            (target_id,)
        ).fetchone()

        # 如果有点赞任务，必须完成；如果没有，只关注即可
        if like and like["status"] != "completed":
            return False

        return True


def get_warming_status(target_id: str) -> Dict[str, Any]:
    """获取目标的预热状态"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT task_type, status, scheduled_at, executed_at, error_message 
               FROM warming_tasks WHERE target_id = ? ORDER BY created_at DESC""",
            (target_id,)
        ).fetchall()

    return {
        "target_id": target_id,
        "tasks": [dict(r) for r in rows],
        "is_warmed": is_target_warmed(target_id)
    }


def schedule_warming_jobs(scheduler):
    """注册预热任务到调度器"""
    from apscheduler.triggers.interval import IntervalTrigger

    # 每 30 分钟检查一次待执行的预热任务
    scheduler.add_job(
        run_warming_batch,
        IntervalTrigger(minutes=30),
        id="warming_batch",
        replace_existing=True,
        args=[15],  # 每次最多15条
    )

    add_log("INFO", "system", "", "warming_jobs_scheduled", "预热任务已注册")


# 初始化
init_warming_table()
