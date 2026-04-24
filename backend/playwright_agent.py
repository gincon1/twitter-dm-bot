from __future__ import annotations

import random
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from playwright.sync_api import Page, sync_playwright


def _snapshot(page: Page, screenshot_dir: str, prefix: str) -> str:
    Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
    path = Path(screenshot_dir) / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    page.screenshot(path=str(path), full_page=True)
    return str(path)


def _first_existing(page: Page, selectors) -> Tuple[Optional[object], Optional[str]]:
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            return loc.first, sel
    return None, None


def _wait_first_existing(
    page: Page,
    selectors,
    timeout_ms: int = 15000,
    poll_ms: int = 400,
    require_visible: bool = False,
) -> Tuple[Optional[object], Optional[str]]:
    deadline = time.time() + max(timeout_ms, 1000) / 1000.0
    last_loc: Optional[object] = None
    last_sel: Optional[str] = None

    while time.time() < deadline:
        loc, sel = _first_existing(page, selectors)
        if loc is not None:
            last_loc, last_sel = loc, sel
            if not require_visible:
                return loc, sel
            try:
                if loc.is_visible():
                    return loc, sel
            except Exception:
                pass
        page.wait_for_timeout(poll_ms)

    if last_loc is not None:
        return last_loc, last_sel
    return None, None


def _check_risk_signals(page: Page) -> bool:
    risk_texts = [
        "Verify your identity",
        "Something went wrong",
        "sending DMs too fast",
        "confirm it's you",
        "验证码",
    ]
    for text in risk_texts:
        if page.get_by_text(text).count() > 0:
            return True
    return False


def _check_verified_block(page: Page) -> bool:
    txt = page.inner_text("body")[:9000]
    keys = [
        "Get verified to message",
        "验证身份后即可向",
        "Only verified users can send Direct Message requests",
        "Upgrade to Premiu",
    ]
    return any(k in txt for k in keys)


def _check_cannot_dm_to_target(page: Page) -> bool:
    txt = page.inner_text("body")[:9000]
    keys = [
        "You cannot send Direct Messages to",
        "您无法向",
    ]
    return any(k in txt for k in keys)


def _is_logged_in(page: Page) -> bool:
    selectors = [
        '[data-testid="AppTabBar_Home_Link"]',
        '[data-testid="AppTabBar_DirectMessage_Link"]',
        '[data-testid="SideNav_NewTweet_Button"]',
        'a[href="/home"]',
        'a[aria-label*="Home" i]',
        'a[aria-label*="主页"]',
    ]
    for sel in selectors:
        try:
            if page.locator(sel).count() > 0:
                return True
        except Exception:
            pass
    return False


def _wait_logged_in(page: Page, timeout_ms: int = 15000) -> bool:
    deadline = time.time() + max(timeout_ms, 1000) / 1000.0
    while time.time() < deadline:
        if _is_logged_in(page):
            return True
        page.wait_for_timeout(500)
    return _is_logged_in(page)


def _goto_with_retry(page: Page, url: str, attempts: int = 3, timeout: int = 45000) -> None:
    last_err: Optional[Exception] = None
    for i in range(1, attempts + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return
        except Exception as e:
            last_err = e
            if i < attempts:
                page.wait_for_timeout(700 * i)
    if last_err:
        raise last_err


def _handle_password_prompt(page: Page, password: str = "2580") -> bool:
    """Detect and handle Twitter secondary password verification prompt."""
    try:
        password_dialog_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[autocomplete="current-password"]',
            'input[placeholder*="password" i]',
            'input[placeholder*="密码"]',
        ]
        for sel in password_dialog_selectors:
            loc = page.locator(sel)
            if loc.count() > 0:
                pw_input = loc.first
                try:
                    if not pw_input.is_visible():
                        continue
                except Exception:
                    continue
                pw_input.click(timeout=5000)
                try:
                    pw_input.fill("")
                except Exception:
                    pass
                pw_input.type(password, delay=random.randint(40, 80))
                page.wait_for_timeout(500)
                page.keyboard.press("Enter")
                page.wait_for_timeout(3000)
                return True

        password_texts = [
            "Enter your password",
            "输入密码",
            "confirm your password",
            "Re-enter your password",
            "verify your password",
        ]
        for text in password_texts:
            if page.get_by_text(text).count() > 0:
                pw_inputs = page.locator('input[type="password"]')
                if pw_inputs.count() > 0:
                    pw_input = pw_inputs.first
                    pw_input.click(timeout=5000)
                    try:
                        pw_input.fill("")
                    except Exception:
                        pass
                    pw_input.type(password, delay=random.randint(40, 80))
                    page.wait_for_timeout(500)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(3000)
                    return True
    except Exception:
        pass
    return False


def send_dm(
    ws_url: str,
    target_username: str,
    message: str,
    account_id: str,
    twitter_account: str,
    screenshot_dir: str,
) -> Dict[str, object]:
    from config import settings

    result: Dict[str, object] = {
        "account_id": account_id,
        "twitter_account": twitter_account,
        "target": target_username,
        "status": "unknown",
        "message_preview": message[:30],
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "note": "",
        "screenshot": "",
    }

    playwright = sync_playwright().start()

    try:
        browser = None
        last_connect_err: Optional[Exception] = None
        for i in range(1, 4):
            try:
                browser = playwright.chromium.connect_over_cdp(ws_url)
                break
            except Exception as e:
                last_connect_err = e
                if i < 3:
                    time.sleep(0.8 * i)
        if browser is None:
            raise last_connect_err or RuntimeError("connect_over_cdp_failed")

        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()

        _goto_with_retry(page, "https://x.com/home", attempts=3, timeout=45000)
        page.wait_for_timeout(1800)

        # Check for password prompt after home page load
        _handle_password_prompt(page, settings.twitter_password)

        logged_in = _wait_logged_in(page, timeout_ms=15000)
        if not logged_in:
            result["status"] = "error"
            result["note"] = "not_logged_in"
            result["screenshot"] = _snapshot(page, screenshot_dir, f"not_logged_in_{target_username}")
            return result

        # Navigate to messages
        _goto_with_retry(page, "https://x.com/messages", attempts=3, timeout=45000)
        page.wait_for_timeout(2200)

        # Check for password prompt after navigating to messages
        _handle_password_prompt(page, settings.twitter_password)

        if _check_risk_signals(page):
            result["status"] = "captcha"
            result["note"] = "risk_signal_detected_in_messages"
            result["screenshot"] = _snapshot(page, screenshot_dir, f"captcha_{target_username}")
            return result

        new_chat_btn, new_chat_sel = _wait_first_existing(
            page,
            [
                '[data-testid="NewDM_Button"]',
                'button[aria-label*="New message" i]',
                'button[aria-label*="New chat" i]',
                'button:has-text("New chat")',
                '[role="button"]:has-text("New chat")',
                'button:has-text("新聊天")',
                '[role="button"]:has-text("新聊天")',
                'button:has-text("新建聊天")',
                '[role="button"]:has-text("新建聊天")',
            ],
            timeout_ms=15000,
            poll_ms=400,
            require_visible=True,
        )
        if new_chat_btn is None:
            result["status"] = "error"
            result["note"] = "new_chat_button_not_found"
            result["screenshot"] = _snapshot(page, screenshot_dir, f"new_chat_missing_{target_username}")
            return result

        new_chat_btn.click(timeout=15000)
        page.wait_for_timeout(1200)

        # Check for password prompt after clicking new chat
        _handle_password_prompt(page, settings.twitter_password)

        search_box = None
        search_sel = None

        dialog = page.locator('div[role="dialog"]')
        if dialog.count() > 0:
            d = dialog.last
            for sel in [
                'input[placeholder*="Search name or username" i]',
                'input[placeholder*="Search" i]',
                'input[placeholder*="搜索"]',
                'input[type="text"]',
                '[role="searchbox"]',
            ]:
                loc = d.locator(sel)
                if loc.count() > 0:
                    search_box = loc.first
                    search_sel = f"dialog:{sel}"
                    break

        if search_box is None:
            search_box, search_sel = _first_existing(
                page,
                [
                    'input[placeholder*="Search name or username" i]',
                    'input[placeholder*="Search" i]',
                    'input[placeholder*="搜索"]',
                    'div[role="dialog"] input[type="text"]',
                ],
            )

        if search_box is None:
            result["status"] = "error"
            result["note"] = "search_box_not_found"
            result["screenshot"] = _snapshot(page, screenshot_dir, f"search_missing_{target_username}")
            return result

        search_box.click(timeout=10000)
        try:
            search_box.fill("")
        except Exception:
            pass
        search_box.type(target_username.replace("@", ""), delay=50)
        page.wait_for_timeout(2800)

        target_row, target_row_sel = _first_existing(
            page,
            [
                f'text=@{target_username.replace("@", "")}',
                f'text={target_username.replace("@", "")}',
                f'[role="button"]:has-text("@{target_username.replace("@", "")}")',
                f'[role="option"]:has-text("{target_username.replace("@", "")}")',
            ],
        )

        if target_row is None:
            result["status"] = "target_not_found"
            result["note"] = "target_row_not_found_in_search"
            result["screenshot"] = _snapshot(page, screenshot_dir, f"target_not_found_{target_username}")
            return result

        target_row.click(timeout=15000)
        page.wait_for_timeout(2200)

        # Check for password prompt after selecting target
        _handle_password_prompt(page, settings.twitter_password)

        if _check_risk_signals(page):
            result["status"] = "captcha"
            result["note"] = "risk_signal_after_target_open"
            result["screenshot"] = _snapshot(page, screenshot_dir, f"captcha_after_open_{target_username}")
            return result

        if _check_verified_block(page):
            result["status"] = "blocked_verification"
            result["note"] = "x_verified_required"
            result["screenshot"] = _snapshot(page, screenshot_dir, f"verified_block_{target_username}")
            return result

        if _check_cannot_dm_to_target(page):
            result["status"] = "cannot_dm"
            result["note"] = "cannot_send_direct_message_to_target"
            result["screenshot"] = _snapshot(page, screenshot_dir, f"cannot_dm_{target_username}")
            return result

        composer, comp_sel = _first_existing(
            page,
            [
                'textarea[placeholder*="message" i]',
                'input[placeholder*="message" i]',
                '[data-testid="dmComposerTextInput"]',
                '[role="textbox"]',
                '[contenteditable="true"]',
            ],
        )
        if composer is None:
            result["status"] = "cannot_dm"
            result["note"] = "composer_not_found"
            result["screenshot"] = _snapshot(page, screenshot_dir, f"composer_missing_{target_username}")
            return result

        composer.click(timeout=10000)
        try:
            composer.fill("")
        except Exception:
            pass

        for char in message:
            composer.type(char, delay=random.randint(35, 90))
        time.sleep(random.uniform(1.2, 2.5))

        send_btn, send_sel = _first_existing(
            page,
            [
                '[data-testid="dmComposerSendButton"]',
                'button[aria-label*="Send" i]',
                'button[aria-label*="发送"]',
            ],
        )
        if send_btn is not None:
            send_btn.click(timeout=10000)
            send_used = send_sel
        else:
            page.keyboard.press("Enter")
            send_used = "keyboard:Enter"

        page.wait_for_timeout(3500)

        delivered = page.get_by_text(message).count() > 0
        result["status"] = "sent" if delivered else "sent_attempt"
        result["note"] = (
            f"new_chat={new_chat_sel}; search={search_sel}; target={target_row_sel}; "
            f"composer={comp_sel}; send={send_used}; delivered={delivered}"
        )
        result["screenshot"] = _snapshot(page, screenshot_dir, f"sent_{target_username}")

    except Exception as e:
        result["status"] = "error"
        result["note"] = str(e)
        try:
            result["screenshot"] = _snapshot(page, screenshot_dir, f"error_{target_username}")
        except Exception:
            pass
    finally:
        try:
            playwright.stop()
        except Exception:
            pass

    return result
