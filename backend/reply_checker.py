from __future__ import annotations

import time
from typing import Dict, List, Optional

from playwright.sync_api import Page, sync_playwright

from playwright_agent import _check_risk_signals, _goto_with_retry, _snapshot, _wait_logged_in


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def _clean_message_text(value: str) -> str:
    lines = [x.strip() for x in str(value or "").splitlines()]
    cleaned = []
    for line in lines:
        if not line:
            continue
        if len(line) <= 8 and ":" in line:
            left, _, right = line.partition(":")
            if left.isdigit() and right.isdigit():
                continue
        cleaned.append(line)
    return _normalize_text("\n".join(cleaned))


def _row_preview(row) -> str:
    try:
        text = " ".join(row.all_inner_texts())
    except Exception:
        try:
            text = row.inner_text(timeout=1000)
        except Exception:
            text = ""
    return _normalize_text(text)


def _matches_username(text: str, username: str) -> bool:
    lower_text = text.lower()
    handle = str(username or "").replace("@", "").strip().lower()
    if not handle:
        return False
    return f"@{handle}" in lower_text or handle in lower_text


def _preview_changed(previous_preview: str, current_preview: str) -> bool:
    prev = _normalize_text(previous_preview).lower()
    curr = _normalize_text(current_preview).lower()
    if not prev or not curr:
        return False
    token = prev[: min(len(prev), 24)]
    if token and token in curr:
        return False
    return True


def _should_open_from_preview(item: Dict[str, str], current_preview: str) -> bool:
    should_open = (
        str(item.get("status") or "") == "contacted"
        or str(item.get("last_message_direction") or "") == "outbound"
        or not item.get("last_checked_at")
        or _preview_changed(str(item.get("last_message_preview") or ""), current_preview)
    )
    if not should_open and "you:" in current_preview.lower() and item.get("last_message_preview"):
        should_open = current_preview != str(item.get("last_message_preview") or "")
    return should_open


def _append_trace(result: Dict[str, object], username: str, steps: List[str], found: bool = False, box: str = "") -> str:
    trace = " -> ".join([str(step).strip() for step in steps if str(step).strip()]) or "-"
    result.setdefault("trace_logs", []).append(
        {
            "target_username": str(username or "").replace("@", "").strip(),
            "trace": trace,
            "found": bool(found),
            "box": str(box or ""),
        }
    )
    return trace


def _append_conversation_payload(
    result: Dict[str, object],
    item: Dict[str, str],
    messages: List[Dict[str, str]],
    box: str,
    steps: List[str],
    preview_fallback: str = "",
) -> None:
    inbound_messages = [x for x in messages if x.get("direction") == "inbound"]
    latest_preview = inbound_messages[-1]["content"] if inbound_messages else str(preview_fallback or "")[:500]
    trace = _append_trace(
        result,
        item["target_username"],
        steps + [f"抓取 {len(messages)} 条消息", f"发现 {len(inbound_messages)} 条入站"],
        found=bool(inbound_messages),
        box=box,
    )
    result["conversations"].append(
        {
            "conversation_id": item["id"],
            "target_id": item["target_id"],
            "target_source": item["target_source"],
            "target_username": item["target_username"],
            "reply_preview": latest_preview[:500],
            "box": box,
            "messages": messages,
            "trace": trace,
        }
    )


def _collect_rows(page: Page, tracked_usernames: List[str], limit: int = 80) -> Dict[str, Dict[str, str]]:
    matched: Dict[str, Dict[str, str]] = {}
    rows = page.locator('[data-testid^="dm-conversation-item-"]')
    count = rows.count()
    if count <= 0:
        rows = page.locator('a[href^="/messages/"]')
        count = rows.count()
    count = min(rows.count(), limit)
    for idx in range(count):
        row = rows.nth(idx)
        row_testid = ""
        try:
            row_testid = str(row.get_attribute("data-testid") or "")
        except Exception:
            pass
        preview = _row_preview(row)
        if not preview:
            continue
        for username in tracked_usernames:
            key = str(username or "").replace("@", "").strip().lower()
            if key in matched:
                continue
            if _matches_username(preview, key):
                matched[key] = {
                    "preview": preview,
                    "row_testid": row_testid,
                }
    return matched


def _open_requests(page: Page) -> bool:
    selectors = [
        'a[href="/messages/requests"]',
        'a[href*="/messages/requests"]',
        '[role="tab"]:has-text("Requests")',
        '[role="link"]:has-text("Requests")',
        '[role="button"]:has-text("Requests")',
        '[role="tab"]:has-text("Message requests")',
        '[role="link"]:has-text("Message requests")',
        '[role="button"]:has-text("Message requests")',
        '[role="tab"]:has-text("请求")',
        '[role="link"]:has-text("请求")',
        '[role="button"]:has-text("请求")',
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.click(timeout=5000)
                page.wait_for_timeout(1200)
                return True
        except Exception:
            continue
    return False


def _wait_inbox_ready(page: Page, timeout_ms: int = 8000) -> None:
    deadline = time.time() + max(timeout_ms, 1000) / 1000.0
    while time.time() < deadline:
        try:
            if page.locator('[data-testid^="dm-conversation-item-"]').count() > 0:
                return
            if page.locator('[data-testid="dm-inbox-panel"]').count() > 0:
                page.wait_for_timeout(300)
                if page.locator('[data-testid^="dm-conversation-item-"]').count() > 0:
                    return
            if page.locator('text=New chat').count() > 0 or page.locator('text=Start Conversation').count() > 0:
                return
        except Exception:
            pass
        page.wait_for_timeout(350)


def _open_conversation(page: Page, row_testid: str, username: str) -> bool:
    loc = None
    if row_testid:
        loc = page.locator(f'[data-testid="{row_testid}"]')
        if loc.count() <= 0:
            loc = None
    if loc is None:
        rows = page.locator('[data-testid^="dm-conversation-item-"]')
        for idx in range(min(rows.count(), 80)):
            row = rows.nth(idx)
            preview = _row_preview(row)
            if _matches_username(preview, username):
                loc = row
                break
    if loc is None:
        return False
    try:
        loc.first.click(timeout=5000)
        page.wait_for_timeout(1000)
        panel = page.locator('[data-testid="dm-conversation-panel"]')
        if panel.count() > 0:
            panel.first.wait_for(timeout=5000)
        page.wait_for_timeout(600)
        return True
    except Exception:
        return False


def _open_conversation_via_search(page: Page, username: str) -> bool:
    search_bar_selectors = [
        '[data-testid="dm-search-bar"]',
        '[data-testid="dm-search-bar"] input',
        'input[placeholder*="Search" i]',
        'input[placeholder*="搜索"]',
        '[role="searchbox"]',
    ]
    search_box = None
    for sel in search_bar_selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                search_box = loc.first
                break
        except Exception:
            continue

    if search_box is None:
        return False

    try:
        search_box.click(timeout=5000)
        page.wait_for_timeout(300)
        for sel in [
            '[data-testid="dm-search-bar"] input',
            'input[placeholder*="Search" i]',
            'input[placeholder*="搜索"]',
            '[role="searchbox"]',
        ]:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    search_box = loc.first
                    break
            except Exception:
                continue
        try:
            search_box.fill("")
        except Exception:
            pass
        search_box.type(str(username or "").replace("@", "").strip(), delay=45)
        page.wait_for_timeout(1800)
    except Exception:
        return False

    target_selectors = [
        f'text=@{str(username or "").replace("@", "").strip()}',
        f'text={str(username or "").replace("@", "").strip()}',
        f'[role="button"]:has-text("@{str(username or "").replace("@", "").strip()}")',
        f'[role="option"]:has-text("{str(username or "").replace("@", "").strip()}")',
    ]
    for sel in target_selectors:
        try:
            loc = page.locator(sel)
            if loc.count() <= 0:
                continue
            loc.first.click(timeout=5000)
            page.wait_for_timeout(1200)
            panel = page.locator('[data-testid="dm-conversation-panel"]')
            if panel.count() > 0:
                panel.first.wait_for(timeout=5000)
            page.wait_for_timeout(600)
            return True
        except Exception:
            continue
    return False


def _extract_conversation_messages(page: Page, box: str) -> List[Dict[str, str]]:
    try:
        payload = page.evaluate(
            """
            (currentBox) => {
              const list = document.querySelector('[data-testid="dm-message-list"]');
              if (!list) return [];
              const items = Array.from(list.querySelectorAll('[data-testid^="message-"]'))
                .filter((el) => {
                  const key = el.getAttribute('data-testid') || '';
                  return key.startsWith('message-') && !key.startsWith('message-text-');
                })
                .map((el) => {
                  const key = el.getAttribute('data-testid') || '';
                  const textEl = el.querySelector('[data-testid^="message-text-"]');
                  const rawText = (textEl ? textEl.innerText : el.innerText || '').trim();
                  const className = String(el.className || '');
                  let direction = 'inbound';
                  if (className.includes('justify-end')) {
                    direction = 'outbound';
                  } else if (className.includes('justify-start')) {
                    direction = 'inbound';
                  } else {
                    const rect = el.getBoundingClientRect();
                    const listRect = list.getBoundingClientRect();
                    direction = rect.left > listRect.left + listRect.width * 0.35 ? 'outbound' : 'inbound';
                  }
                  return {
                    message_key: key,
                    content: rawText,
                    direction,
                    box: currentBox || 'inbox',
                  };
                });
              return items;
            }
            """,
            box,
        )
    except Exception:
        return []

    events: List[Dict[str, str]] = []
    for item in payload or []:
        content = _clean_message_text(str(item.get("content") or ""))
        if not content:
            continue
        events.append(
            {
                "message_key": str(item.get("message_key") or ""),
                "content": content[:2000],
                "direction": "inbound" if str(item.get("direction") or "") == "inbound" else "outbound",
                "box": str(item.get("box") or box or "inbox"),
            }
        )
    return events


def check_account_replies(
    ws_url: str,
    account_id: str,
    twitter_account: str,
    tracked_conversations: List[dict],
    screenshot_dir: str,
) -> Dict[str, object]:
    result: Dict[str, object] = {
        "account_id": account_id,
        "twitter_account": twitter_account,
        "status": "ok",
        "checked": len(tracked_conversations),
        "conversations": [],
        "trace_logs": [],
        "note": "",
        "screenshot": "",
    }

    playwright = sync_playwright().start()
    page = None

    try:
        browser = None
        last_connect_err: Optional[Exception] = None
        for idx in range(1, 4):
            try:
                browser = playwright.chromium.connect_over_cdp(ws_url)
                break
            except Exception as exc:
                last_connect_err = exc
                if idx < 3:
                    time.sleep(0.8 * idx)
        if browser is None:
            raise last_connect_err or RuntimeError("connect_over_cdp_failed")

        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()

        _goto_with_retry(page, "https://x.com/messages", attempts=3, timeout=30000)
        page.wait_for_timeout(1400)

        if not _wait_logged_in(page, timeout_ms=8000):
            result["status"] = "error"
            result["note"] = "not_logged_in"
            result["screenshot"] = _snapshot(page, screenshot_dir, f"reply_not_logged_in_{account_id}")
            return result

        if _check_risk_signals(page):
            result["status"] = "captcha"
            result["note"] = "risk_signal_detected_in_messages"
            result["screenshot"] = _snapshot(page, screenshot_dir, f"reply_captcha_{account_id}")
            return result

        _wait_inbox_ready(page, timeout_ms=8000)

        tracked = [
            {
                "id": str(item.get("id") or ""),
                "target_id": str(item.get("target_id") or ""),
                "target_source": str(item.get("target_source") or "local"),
                "target_username": str(item.get("target_username") or "").replace("@", "").strip(),
                "last_message_preview": str(item.get("last_message_preview") or ""),
                "last_checked_at": str(item.get("last_checked_at") or ""),
                "last_message_direction": str(item.get("last_message_direction") or "outbound"),
                "status": str(item.get("status") or "contacted"),
                "reply_check_strategy": str(item.get("reply_check_strategy") or "list_first"),
                "reply_check_group": str(item.get("reply_check_group") or ""),
            }
            for item in tracked_conversations
            if str(item.get("target_username") or "").strip()
        ]
        usernames = [item["target_username"].lower() for item in tracked]
        inbox_rows = _collect_rows(page, usernames)
        search_fallback_hits = 0
        requests_hits = 0

        for item in tracked:
            if item.get("reply_check_strategy") != "search_first":
                continue
            steps = ["归属优先", item.get("reply_check_group") or "未分组", "搜索优先"]
            if not _open_conversation_via_search(page, item["target_username"]):
                _append_trace(result, item["target_username"], steps + ["搜索未命中"], found=False, box="inbox")
                continue
            messages = _extract_conversation_messages(page, "inbox")
            if not messages:
                _append_trace(result, item["target_username"], steps + ["命中成功", "会话为空"], found=False, box="inbox")
                continue
            search_fallback_hits += 1
            _append_conversation_payload(
                result,
                item,
                messages,
                "inbox",
                steps + ["命中成功"],
                preview_fallback=str(item.get("last_message_preview") or ""),
            )

        for item in tracked:
            if item["target_username"].lower() in {
                str(parsed.get("target_username") or "").lower() for parsed in result["conversations"]
            }:
                continue
            matched = inbox_rows.get(item["target_username"].lower())
            if not matched:
                continue
            current = str(matched.get("preview") or "")
            steps = ["归属优先", item.get("reply_check_group") or "未分组", "列表命中"]
            should_open = _should_open_from_preview(item, current)
            if not should_open:
                _append_trace(result, item["target_username"], steps + ["预览无变化，跳过"], found=False, box="inbox")
                continue
            if _open_conversation(page, str(matched.get("row_testid") or ""), item["target_username"]):
                steps.append("列表打开成功")
            else:
                steps.append("列表打开失败")
                steps.append("走搜索兜底")
                if not _open_conversation_via_search(page, item["target_username"]):
                    _append_trace(result, item["target_username"], steps + ["兜底失败"], found=False, box="inbox")
                    continue
                search_fallback_hits += 1
                steps.append("命中成功")
            messages = _extract_conversation_messages(page, "inbox")
            if not messages:
                _append_trace(result, item["target_username"], steps + ["会话为空"], found=False, box="inbox")
                continue
            _append_conversation_payload(result, item, messages, "inbox", steps, preview_fallback=current)

        remaining_targets = {
            str(item.get("target_username") or "").lower(): item for item in tracked if str(item.get("target_username") or "")
        }
        for parsed in result["conversations"]:
            remaining_targets.pop(str(parsed.get("target_username") or "").lower(), None)

        for item in remaining_targets.values():
            steps = ["归属优先", item.get("reply_check_group") or "未分组", "列表未命中", "走搜索兜底"]
            if not _open_conversation_via_search(page, item["target_username"]):
                _append_trace(result, item["target_username"], steps + ["兜底失败"], found=False, box="inbox")
                continue
            search_fallback_hits += 1
            messages = _extract_conversation_messages(page, "inbox")
            if not messages:
                _append_trace(result, item["target_username"], steps + ["命中成功", "会话为空"], found=False, box="inbox")
                continue
            _append_conversation_payload(
                result,
                item,
                messages,
                "inbox",
                steps + ["命中成功"],
                preview_fallback=str(item.get("last_message_preview") or ""),
            )

        parsed_usernames = {str(item.get("target_username") or "").lower() for item in result["conversations"]}
        remaining = [item for item in tracked if item["target_username"].lower() not in parsed_usernames]
        if remaining:
            if _open_requests(page):
                request_rows = _collect_rows(page, [item["target_username"] for item in remaining])
                for item in remaining:
                    matched = request_rows.get(item["target_username"].lower())
                    steps = ["归属优先", item.get("reply_check_group") or "未分组", "列表未命中", "搜索兜底失败", "打开 Requests"]
                    if not matched:
                        _append_trace(result, item["target_username"], steps + ["Requests 列表未命中"], found=False, box="requests")
                        continue
                    current = str(matched.get("preview") or "")
                    steps.append("Requests 列表命中")
                    should_open = _should_open_from_preview(item, current)
                    if not should_open:
                        _append_trace(result, item["target_username"], steps + ["预览无变化，跳过"], found=False, box="requests")
                        continue
                    if not _open_conversation(page, str(matched.get("row_testid") or ""), item["target_username"]):
                        _append_trace(result, item["target_username"], steps + ["Requests 打开失败"], found=False, box="requests")
                        continue
                    messages = _extract_conversation_messages(page, "requests")
                    if not messages:
                        _append_trace(result, item["target_username"], steps + ["Requests 打开成功", "会话为空"], found=False, box="requests")
                        continue
                    requests_hits += 1
                    _append_conversation_payload(
                        result,
                        item,
                        messages,
                        "requests",
                        steps + ["Requests 打开成功"],
                        preview_fallback=current,
                    )
            else:
                for item in remaining:
                    _append_trace(
                        result,
                        item["target_username"],
                        ["列表未命中", "搜索兜底失败", "Requests 入口未找到"],
                        found=False,
                        box="requests",
                    )

        result["note"] = (
            f"checked={len(tracked)} opened={len(result['conversations'])} "
            f"search_fallback={search_fallback_hits} requests={requests_hits}"
        )
        if result["conversations"]:
            result["screenshot"] = _snapshot(page, screenshot_dir, f"reply_found_{account_id}")

    except Exception as exc:
        result["status"] = "error"
        result["note"] = str(exc)
        try:
            if page is not None:
                result["screenshot"] = _snapshot(page, screenshot_dir, f"reply_error_{account_id}")
        except Exception:
            pass
    finally:
        try:
            playwright.stop()
        except Exception:
            pass

    return result
