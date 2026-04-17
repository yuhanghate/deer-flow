"""Deterministic Playwright/CDP atomic browser tools.

These tools provide low-level browser operations without built-in planning.
They are intended to be orchestrated by DeerFlow's lead agent.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

from langchain.tools import tool

from deerflow.config import get_app_config


@dataclass(slots=True)
class BrowserAtomicSession:
    session_id: str
    playwright: Any
    browser: Any
    context: Any
    page: Any
    cdp_url: str | None
    headless: bool
    conversation_id: str = ""
    task_id: str = ""
    origin: str | None = None
    reuse_policy: str = "task_isolated"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_SESSIONS: dict[str, BrowserAtomicSession] = {}
_SESSIONS_LOCK = asyncio.Lock()


def _json_ok(**kwargs: Any) -> str:
    return json.dumps({"ok": True, **kwargs}, ensure_ascii=False)


def _json_err(code: str, message: str, **kwargs: Any) -> str:
    return json.dumps({"ok": False, "code": code, "message": message, **kwargs}, ensure_ascii=False)


def _open_cfg() -> dict[str, Any]:
    cfg = get_app_config().get_tool_config("browser_open_session")
    return dict(getattr(cfg, "model_extra", {}) or {}) if cfg else {}


def _clip_text(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0:
        return "", bool(text)
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _origin_from_url(url: str) -> str | None:
    raw = url.strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _normalize_reuse_policy(policy: str) -> str:
    normalized = policy.strip().lower()
    allowed = {"task_isolated", "conversation_single_tab", "conversation_origin_tab"}
    return normalized if normalized in allowed else "task_isolated"


def _pick_reusable_session(
    sessions: list[BrowserAtomicSession],
    conversation_id: str,
    reuse_policy: str,
    requested_origin: str | None,
) -> BrowserAtomicSession | None:
    if not conversation_id:
        return None

    ordered = sorted(sessions, key=lambda s: s.updated_at, reverse=True)
    for session in ordered:
        if session.conversation_id != conversation_id:
            continue
        if reuse_policy == "conversation_single_tab":
            return session
        if reuse_policy == "conversation_origin_tab":
            if requested_origin and session.origin == requested_origin:
                return session
    return None


async def _get_session(session_id: str) -> BrowserAtomicSession | None:
    async with _SESSIONS_LOCK:
        return _SESSIONS.get(session_id)


async def _put_session(session: BrowserAtomicSession) -> None:
    async with _SESSIONS_LOCK:
        _SESSIONS[session.session_id] = session


async def _pop_session(session_id: str) -> BrowserAtomicSession | None:
    async with _SESSIONS_LOCK:
        return _SESSIONS.pop(session_id, None)


async def _find_reusable_session(
    conversation_id: str,
    reuse_policy: str,
    requested_origin: str | None,
) -> BrowserAtomicSession | None:
    async with _SESSIONS_LOCK:
        sessions = list(_SESSIONS.values())
    return _pick_reusable_session(sessions, conversation_id, reuse_policy, requested_origin)


def _normalize_cdp_probe_url(raw_cdp_url: str) -> str:
    parsed = urlparse(raw_cdp_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid cdp_url: {raw_cdp_url}")

    if parsed.scheme == "ws":
        probe_scheme = "http"
    elif parsed.scheme == "wss":
        probe_scheme = "https"
    elif parsed.scheme in {"http", "https"}:
        probe_scheme = parsed.scheme
    else:
        raise ValueError(f"Unsupported cdp_url scheme: {parsed.scheme}")

    return f"{probe_scheme}://{parsed.netloc}/json/version"


async def _probe_cdp_status(cdp_url: str, timeout_ms: int = 3000) -> dict[str, Any]:
    probe_url = _normalize_cdp_probe_url(cdp_url)
    timeout_sec = max(0.1, timeout_ms / 1000)

    try:
        import httpx
    except Exception as exc:
        return {
            "reachable": False,
            "probe_url": probe_url,
            "error": f"httpx unavailable: {exc}",
        }

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            response = await client.get(probe_url)
        if response.status_code != 200:
            return {
                "reachable": False,
                "probe_url": probe_url,
                "status_code": response.status_code,
                "error": response.text[:300],
            }
        payload = response.json()
        return {
            "reachable": True,
            "probe_url": probe_url,
            "status_code": response.status_code,
            "browser": payload.get("Browser"),
            "protocol_version": payload.get("Protocol-Version"),
            "websocket_debugger_url": payload.get("webSocketDebuggerUrl"),
        }
    except Exception as exc:
        return {
            "reachable": False,
            "probe_url": probe_url,
            "error": str(exc),
        }


@tool("browser_open_session", parse_docstring=True)
async def browser_open_session_tool(
    start_url: str = "",
    cdp_url: str = "",
    headless: bool = True,
    conversation_id: str = "",
    task_id: str = "",
    reuse_policy: str = "task_isolated",
    force_new: bool = False,
    open_in_new_tab: bool = False,
) -> str:
    """Open a browser session and return a session_id.

    Args:
        start_url: Optional URL to navigate immediately after session opens.
        cdp_url: Optional CDP endpoint (e.g. http://127.0.0.1:9222).
        headless: Whether to launch a new local browser in headless mode when cdp_url is empty.
        conversation_id: Optional conversation/thread identifier for scoped reuse.
        task_id: Optional task identifier for traceability.
        reuse_policy: task_isolated | conversation_single_tab | conversation_origin_tab.
        force_new: Force opening a new isolated session even if reuse policy matches.
        open_in_new_tab: When reusing, open a new tab in existing context.
    """
    cfg = _open_cfg()
    normalized_start_url = start_url.strip()
    resolved_cdp_url = (cdp_url or str(cfg.get("cdp_url", "") or "")).strip() or None
    resolved_headless = bool(cfg.get("headless", headless))
    timeout_ms = int(cfg.get("timeout_ms", 15000))
    resolved_conversation_id = conversation_id.strip()
    resolved_task_id = task_id.strip()
    policy_from_cfg = str(cfg.get("reuse_policy", reuse_policy) or reuse_policy)
    resolved_reuse_policy = _normalize_reuse_policy(policy_from_cfg)
    resolved_force_new = bool(force_new)
    resolved_open_in_new_tab = bool(open_in_new_tab)
    requested_origin = _origin_from_url(normalized_start_url)

    if not resolved_force_new and resolved_reuse_policy != "task_isolated":
        reusable = await _find_reusable_session(resolved_conversation_id, resolved_reuse_policy, requested_origin)
        if reusable is not None:
            async with reusable.lock:
                if resolved_open_in_new_tab and reusable.context is not None:
                    reusable.page = await reusable.context.new_page()
                if normalized_start_url:
                    await reusable.page.goto(normalized_start_url, wait_until="domcontentloaded", timeout=timeout_ms)
                reusable.conversation_id = resolved_conversation_id or reusable.conversation_id
                reusable.task_id = resolved_task_id or reusable.task_id
                reusable.origin = requested_origin or reusable.origin
                reusable.reuse_policy = resolved_reuse_policy
                reusable.updated_at = time.time()
                return _json_ok(
                    session_id=reusable.session_id,
                    reused=True,
                    reuse_policy=resolved_reuse_policy,
                    start_url=normalized_start_url or None,
                    current_url=reusable.page.url,
                    cdp_url=reusable.cdp_url,
                    headless=reusable.headless,
                    conversation_id=reusable.conversation_id or None,
                    task_id=reusable.task_id or None,
                    origin=reusable.origin,
                    tab_count=len(reusable.context.pages) if reusable.context is not None else None,
                )

    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        return _json_err("MISSING_DEPENDENCY", "Playwright is required. Install with `cd backend && uv sync`.", error=str(exc))

    pw = await async_playwright().start()
    try:
        if resolved_cdp_url:
            browser = await pw.chromium.connect_over_cdp(resolved_cdp_url)
            if browser.contexts:
                context = browser.contexts[0]
            else:
                context = await browser.new_context()
            page = context.pages[0] if context.pages else await context.new_page()
        else:
            browser = await pw.chromium.launch(headless=resolved_headless)
            context = await browser.new_context()
            page = await context.new_page()

        session = BrowserAtomicSession(
            session_id=uuid.uuid4().hex[:12],
            playwright=pw,
            browser=browser,
            context=context,
            page=page,
            cdp_url=resolved_cdp_url,
            headless=resolved_headless,
            conversation_id=resolved_conversation_id,
            task_id=resolved_task_id,
            origin=requested_origin,
            reuse_policy=resolved_reuse_policy,
        )
        await _put_session(session)

        if normalized_start_url:
            await page.goto(normalized_start_url, wait_until="domcontentloaded", timeout=timeout_ms)
            session.updated_at = time.time()

        return _json_ok(
            session_id=session.session_id,
            reused=False,
            reuse_policy=resolved_reuse_policy,
            start_url=normalized_start_url or None,
            current_url=page.url,
            cdp_url=resolved_cdp_url,
            headless=resolved_headless,
            conversation_id=resolved_conversation_id or None,
            task_id=resolved_task_id or None,
            origin=requested_origin,
            tab_count=len(context.pages) if context is not None else None,
        )
    except Exception as exc:
        try:
            await pw.stop()
        except Exception:
            pass
        return _json_err("OPEN_SESSION_FAILED", str(exc), cdp_url=resolved_cdp_url)


@tool("browser_goto", parse_docstring=True)
async def browser_goto_tool(session_id: str, url: str) -> str:
    """Navigate an existing session page to a URL.

    Args:
        session_id: Session identifier from browser_open_session.
        url: Target URL.
    """
    session = await _get_session(session_id)
    if session is None:
        return _json_err("SESSION_NOT_FOUND", f"Session not found: {session_id}", session_id=session_id)

    cfg = _open_cfg()
    timeout_ms = int(cfg.get("timeout_ms", 15000))
    async with session.lock:
        await session.page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        session.origin = _origin_from_url(url) or session.origin
        session.updated_at = time.time()
        return _json_ok(session_id=session_id, current_url=session.page.url)


@tool("browser_click", parse_docstring=True)
async def browser_click_tool(session_id: str, selector: str) -> str:
    """Click an element in the active page.

    Args:
        session_id: Session identifier.
        selector: CSS selector to click.
    """
    session = await _get_session(session_id)
    if session is None:
        return _json_err("SESSION_NOT_FOUND", f"Session not found: {session_id}", session_id=session_id)
    cfg = _open_cfg()
    timeout_ms = int(cfg.get("timeout_ms", 15000))
    async with session.lock:
        await session.page.locator(selector).first.click(timeout=timeout_ms)
        session.updated_at = time.time()
        return _json_ok(session_id=session_id, clicked=selector, current_url=session.page.url)


@tool("browser_type", parse_docstring=True)
async def browser_type_tool(session_id: str, selector: str, text: str, clear_first: bool = True) -> str:
    """Type text into an input element.

    Args:
        session_id: Session identifier.
        selector: CSS selector for input/textarea.
        text: Text to type.
        clear_first: Whether to clear existing value first.
    """
    session = await _get_session(session_id)
    if session is None:
        return _json_err("SESSION_NOT_FOUND", f"Session not found: {session_id}", session_id=session_id)
    cfg = _open_cfg()
    timeout_ms = int(cfg.get("timeout_ms", 15000))
    async with session.lock:
        locator = session.page.locator(selector).first
        if clear_first:
            await locator.fill("", timeout=timeout_ms)
        await locator.fill(text, timeout=timeout_ms)
        session.updated_at = time.time()
        return _json_ok(session_id=session_id, typed_selector=selector, text_length=len(text))


@tool("browser_wait", parse_docstring=True)
async def browser_wait_tool(session_id: str, milliseconds: int = 0, selector: str = "", load_state: str = "") -> str:
    """Wait for time, selector, or page load-state.

    Args:
        session_id: Session identifier.
        milliseconds: Wait duration in milliseconds when selector/load_state are empty.
        selector: Optional selector to wait for visibility.
        load_state: Optional load state: load | domcontentloaded | networkidle.
    """
    session = await _get_session(session_id)
    if session is None:
        return _json_err("SESSION_NOT_FOUND", f"Session not found: {session_id}", session_id=session_id)
    cfg = _open_cfg()
    timeout_ms = int(cfg.get("timeout_ms", 15000))
    async with session.lock:
        if selector.strip():
            await session.page.wait_for_selector(selector.strip(), timeout=timeout_ms)
            waited = f"selector:{selector.strip()}"
        elif load_state.strip():
            await session.page.wait_for_load_state(load_state.strip(), timeout=timeout_ms)
            waited = f"load_state:{load_state.strip()}"
        else:
            ms = max(0, int(milliseconds))
            await session.page.wait_for_timeout(ms)
            waited = f"ms:{ms}"
        session.updated_at = time.time()
        return _json_ok(session_id=session_id, waited=waited)


@tool("browser_extract_text", parse_docstring=True)
async def browser_extract_text_tool(session_id: str, selector: str) -> str:
    """Extract normalized inner text from an element.

    Args:
        session_id: Session identifier.
        selector: CSS selector.
    """
    session = await _get_session(session_id)
    if session is None:
        return _json_err("SESSION_NOT_FOUND", f"Session not found: {session_id}", session_id=session_id)
    cfg = _open_cfg()
    timeout_ms = int(cfg.get("timeout_ms", 15000))
    async with session.lock:
        text = await session.page.locator(selector).first.inner_text(timeout=timeout_ms)
        normalized = " ".join(text.split())
        session.updated_at = time.time()
        return _json_ok(session_id=session_id, selector=selector, text=normalized)


@tool("browser_extract_list", parse_docstring=True)
async def browser_extract_list_tool(session_id: str, item_selector: str, field_selectors_json: str, limit: int = 20) -> str:
    """Extract structured list data from repeated items.

    Args:
        session_id: Session identifier.
        item_selector: CSS selector for each list item container.
        field_selectors_json: JSON object mapping field name -> CSS selector relative to item.
        limit: Maximum items to extract (1-100).
    """
    session = await _get_session(session_id)
    if session is None:
        return _json_err("SESSION_NOT_FOUND", f"Session not found: {session_id}", session_id=session_id)

    try:
        field_selectors = json.loads(field_selectors_json)
        if not isinstance(field_selectors, dict) or not field_selectors:
            return _json_err("INVALID_FIELDS", "field_selectors_json must be a non-empty JSON object.")
    except Exception as exc:
        return _json_err("INVALID_FIELDS_JSON", f"Failed to parse field_selectors_json: {exc}")

    capped_limit = max(1, min(int(limit), 100))
    async with session.lock:
        items = session.page.locator(item_selector)
        count = min(await items.count(), capped_limit)
        rows: list[dict[str, str]] = []

        for idx in range(count):
            row_locator = items.nth(idx)
            row: dict[str, str] = {}
            for field, field_selector in field_selectors.items():
                try:
                    raw = await row_locator.locator(str(field_selector)).first.inner_text(timeout=800)
                    row[field] = " ".join(raw.split())
                except Exception:
                    row[field] = ""
            rows.append(row)

        session.updated_at = time.time()
        return _json_ok(session_id=session_id, count=len(rows), items=rows)


@tool("browser_get_url", parse_docstring=True)
async def browser_get_url_tool(session_id: str) -> str:
    """Get the current URL and title of active page.

    Args:
        session_id: Session identifier.
    """
    session = await _get_session(session_id)
    if session is None:
        return _json_err("SESSION_NOT_FOUND", f"Session not found: {session_id}", session_id=session_id)
    async with session.lock:
        title = await session.page.title()
        return _json_ok(session_id=session_id, current_url=session.page.url, title=title)


@tool("browser_get_page_source", parse_docstring=True)
async def browser_get_page_source_tool(session_id: str, max_chars: int = 200000) -> str:
    """Return current page HTML source (with optional truncation).

    Args:
        session_id: Session identifier.
        max_chars: Maximum HTML characters to return (0-500000).
    """
    session = await _get_session(session_id)
    if session is None:
        return _json_err("SESSION_NOT_FOUND", f"Session not found: {session_id}", session_id=session_id)

    capped = max(0, min(int(max_chars), 500000))
    async with session.lock:
        html = await session.page.content()
        clipped, truncated = _clip_text(html, capped)
        session.updated_at = time.time()
        return _json_ok(
            session_id=session_id,
            current_url=session.page.url,
            max_chars=capped,
            html=clipped,
            total_chars=len(html),
            returned_chars=len(clipped),
            truncated=truncated,
        )


@tool("browser_get_interactive_elements", parse_docstring=True)
async def browser_get_interactive_elements_tool(session_id: str, limit: int = 80, include_invisible: bool = False) -> str:
    """List interactive elements on current page.

    Args:
        session_id: Session identifier.
        limit: Maximum elements to return (1-300).
        include_invisible: Whether to include hidden/offscreen elements.
    """
    session = await _get_session(session_id)
    if session is None:
        return _json_err("SESSION_NOT_FOUND", f"Session not found: {session_id}", session_id=session_id)

    capped_limit = max(1, min(int(limit), 300))
    async with session.lock:
        rows = await session.page.evaluate(
            """
            () => {
              const selector = 'a,button,input,textarea,select,[role="button"],[onclick],[tabindex]';
              const nodes = Array.from(document.querySelectorAll(selector));
              return nodes.map((el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                const visible = Boolean(
                  rect.width > 0 &&
                  rect.height > 0 &&
                  style.visibility !== 'hidden' &&
                  style.display !== 'none'
                );
                const text = String(
                  el.innerText ||
                  el.textContent ||
                  el.value ||
                  el.getAttribute('aria-label') ||
                  el.getAttribute('placeholder') ||
                  ''
                ).replace(/\\s+/g, ' ').trim().slice(0, 200);
                const className = String(el.className || '').trim().replace(/\\s+/g, '.');
                const selectorHint = el.id
                  ? `#${el.id}`
                  : className
                    ? `${el.tagName.toLowerCase()}.${className.split('.').slice(0, 2).join('.')}`
                    : el.tagName.toLowerCase();
                return {
                  tag: el.tagName.toLowerCase(),
                  id: el.id || '',
                  class_name: String(el.className || ''),
                  text,
                  selector: selectorHint,
                  visible,
                  href: el.getAttribute('href') || '',
                  name: el.getAttribute('name') || '',
                  type: el.getAttribute('type') || '',
                  rect: {
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                  },
                };
              });
            }
            """
        )
        elements = [row for row in rows if include_invisible or bool(row.get("visible"))]
        elements = elements[:capped_limit]
        session.updated_at = time.time()
        return _json_ok(
            session_id=session_id,
            current_url=session.page.url,
            count=len(elements),
            limit=capped_limit,
            include_invisible=include_invisible,
            elements=elements,
        )


@tool("browser_extract_links", parse_docstring=True)
async def browser_extract_links_tool(session_id: str, selector: str = "a", limit: int = 120, include_invisible: bool = False) -> str:
    """Extract candidate links with text and href for navigation.

    Args:
        session_id: Session identifier.
        selector: CSS selector used to collect link-like elements.
        limit: Maximum links to return (1-500).
        include_invisible: Whether to include hidden/offscreen links.
    """
    session = await _get_session(session_id)
    if session is None:
        return _json_err("SESSION_NOT_FOUND", f"Session not found: {session_id}", session_id=session_id)

    capped_limit = max(1, min(int(limit), 500))
    normalized_selector = selector.strip() or "a"

    async with session.lock:
        rows = await session.page.evaluate(
            """
            (args) => {
              const nodes = Array.from(document.querySelectorAll(args.selector));
              return nodes.map((el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                const visible = Boolean(
                  rect.width > 0 &&
                  rect.height > 0 &&
                  style.visibility !== 'hidden' &&
                  style.display !== 'none'
                );
                const href = el.getAttribute('href') || '';
                const text = String(
                  el.innerText ||
                  el.textContent ||
                  el.getAttribute('aria-label') ||
                  el.getAttribute('title') ||
                  ''
                ).replace(/\\s+/g, ' ').trim().slice(0, 300);
                return {
                  tag: el.tagName.toLowerCase(),
                  text,
                  href,
                  visible,
                };
              });
            }
            """,
            {"selector": normalized_selector},
        )
        links: list[dict[str, Any]] = []
        for row in rows:
            if not include_invisible and not bool(row.get("visible")):
                continue
            raw_href = str(row.get("href") or "").strip()
            absolute_href = urljoin(session.page.url, raw_href) if raw_href else ""
            links.append(
                {
                    "tag": row.get("tag", ""),
                    "text": row.get("text", ""),
                    "href": absolute_href,
                    "raw_href": raw_href,
                    "visible": bool(row.get("visible")),
                }
            )
            if len(links) >= capped_limit:
                break
        session.updated_at = time.time()
        return _json_ok(
            session_id=session_id,
            current_url=session.page.url,
            selector=normalized_selector,
            count=len(links),
            limit=capped_limit,
            include_invisible=include_invisible,
            links=links,
        )


@tool("browser_get_layout_snapshot", parse_docstring=True)
async def browser_get_layout_snapshot_tool(session_id: str, selectors_json: str = "", limit: int = 120, only_visible: bool = True) -> str:
    """Get layout geometry snapshot for selected elements.

    Args:
        session_id: Session identifier.
        selectors_json: Optional JSON array of CSS selectors.
        limit: Maximum elements to return (1-500).
        only_visible: Whether to include visible elements only.
    """
    session = await _get_session(session_id)
    if session is None:
        return _json_err("SESSION_NOT_FOUND", f"Session not found: {session_id}", session_id=session_id)

    if selectors_json.strip():
        try:
            parsed = json.loads(selectors_json)
            if not isinstance(parsed, list) or not parsed:
                return _json_err("INVALID_SELECTORS", "selectors_json must be a non-empty JSON array of selector strings.")
            selectors = [str(item).strip() for item in parsed if str(item).strip()]
            if not selectors:
                return _json_err("INVALID_SELECTORS", "selectors_json has no valid selector strings.")
        except Exception as exc:
            return _json_err("INVALID_SELECTORS_JSON", f"Failed to parse selectors_json: {exc}")
    else:
        selectors = ['a', 'button', 'input', 'textarea', 'select', '[role="button"]']

    capped_limit = max(1, min(int(limit), 500))
    joined_selector = ",".join(selectors)

    async with session.lock:
        rows = await session.page.evaluate(
            """
            (args) => {
              const nodes = Array.from(document.querySelectorAll(args.selector));
              return nodes.map((el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                const visible = Boolean(
                  rect.width > 0 &&
                  rect.height > 0 &&
                  style.visibility !== 'hidden' &&
                  style.display !== 'none'
                );
                const text = String(
                  el.innerText ||
                  el.textContent ||
                  el.getAttribute('aria-label') ||
                  el.getAttribute('placeholder') ||
                  ''
                ).replace(/\\s+/g, ' ').trim().slice(0, 120);
                const className = String(el.className || '').trim().replace(/\\s+/g, '.');
                const selectorHint = el.id
                  ? `#${el.id}`
                  : className
                    ? `${el.tagName.toLowerCase()}.${className.split('.').slice(0, 2).join('.')}`
                    : el.tagName.toLowerCase();
                return {
                  tag: el.tagName.toLowerCase(),
                  selector: selectorHint,
                  text,
                  visible,
                  rect: {
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                  },
                };
              });
            }
            """,
            {"selector": joined_selector},
        )

        snapshot = [row for row in rows if (not only_visible) or bool(row.get("visible"))]
        snapshot = snapshot[:capped_limit]
        session.updated_at = time.time()
        return _json_ok(
            session_id=session_id,
            current_url=session.page.url,
            selectors=selectors,
            count=len(snapshot),
            limit=capped_limit,
            only_visible=only_visible,
            elements=snapshot,
        )


@tool("browser_check_status", parse_docstring=True)
async def browser_check_status_tool(session_id: str = "", cdp_url: str = "", check_cdp: bool = True) -> str:
    """Check browser runtime/session status for MCP-style health probing.

    Args:
        session_id: Optional session ID to inspect. Empty means summary only.
        cdp_url: Optional CDP endpoint override for probe.
        check_cdp: Whether to probe CDP `/json/version` reachability.
    """
    cfg = _open_cfg()
    configured_cdp = str(cfg.get("cdp_url", "") or "").strip()
    active_cdp = (cdp_url or configured_cdp).strip()

    async with _SESSIONS_LOCK:
        total_sessions = len(_SESSIONS)
        target_session = _SESSIONS.get(session_id) if session_id else None
        sample_session_ids = list(_SESSIONS.keys())[:20]

    if session_id and target_session is None:
        result = {
            "ok": False,
            "code": "SESSION_NOT_FOUND",
            "message": f"Session not found: {session_id}",
            "session_id": session_id,
            "active_sessions": total_sessions,
            "sample_session_ids": sample_session_ids,
            "configured_cdp_url": configured_cdp or None,
        }
        if check_cdp and active_cdp:
            result["cdp_status"] = await _probe_cdp_status(active_cdp)
        return json.dumps(result, ensure_ascii=False)

    session_info: dict[str, Any] | None = None
    if target_session is not None:
        async with target_session.lock:
            title = ""
            current_url = ""
            try:
                title = await target_session.page.title()
                current_url = target_session.page.url
            except Exception:
                pass
            session_info = {
                "session_id": target_session.session_id,
                "current_url": current_url,
                "title": title,
                "tab_count": len(target_session.context.pages) if target_session.context is not None else 0,
                "cdp_url": target_session.cdp_url,
                "headless": target_session.headless,
                "conversation_id": target_session.conversation_id or None,
                "task_id": target_session.task_id or None,
                "origin": target_session.origin,
                "reuse_policy": target_session.reuse_policy,
                "created_at": target_session.created_at,
                "updated_at": target_session.updated_at,
                "age_seconds": round(max(0.0, time.time() - target_session.created_at), 2),
            }

    response: dict[str, Any] = {
        "ok": True,
        "code": "OK",
        "active_sessions": total_sessions,
        "sample_session_ids": sample_session_ids,
        "configured_cdp_url": configured_cdp or None,
        "session": session_info,
    }

    if check_cdp:
        if active_cdp:
            response["cdp_status"] = await _probe_cdp_status(active_cdp)
        else:
            response["cdp_status"] = {
                "reachable": False,
                "error": "No cdp_url configured or provided.",
            }

    return json.dumps(response, ensure_ascii=False)


@tool("browser_switch_tab", parse_docstring=True)
async def browser_switch_tab_tool(session_id: str, tab_index: int = 0) -> str:
    """Switch active page to another tab by index.

    Args:
        session_id: Session identifier.
        tab_index: Target tab index (0-based).
    """
    session = await _get_session(session_id)
    if session is None:
        return _json_err("SESSION_NOT_FOUND", f"Session not found: {session_id}", session_id=session_id)

    async with session.lock:
        pages = session.context.pages
        if not pages:
            return _json_err("NO_TABS", "No tabs found in current browser context.", session_id=session_id)
        if tab_index < 0 or tab_index >= len(pages):
            return _json_err("INVALID_TAB_INDEX", f"tab_index out of range: {tab_index}", tab_count=len(pages))
        session.page = pages[tab_index]
        await session.page.bring_to_front()
        session.origin = _origin_from_url(session.page.url) or session.origin
        session.updated_at = time.time()
        return _json_ok(session_id=session_id, tab_index=tab_index, current_url=session.page.url, tab_count=len(pages))


@tool("browser_screenshot", parse_docstring=True)
async def browser_screenshot_tool(session_id: str, path: str, full_page: bool = True) -> str:
    """Take a screenshot of the current page.

    Args:
        session_id: Session identifier.
        path: Output screenshot path.
        full_page: Whether to capture full page.
    """
    session = await _get_session(session_id)
    if session is None:
        return _json_err("SESSION_NOT_FOUND", f"Session not found: {session_id}", session_id=session_id)

    async with session.lock:
        await session.page.screenshot(path=path, full_page=full_page)
        session.updated_at = time.time()
        return _json_ok(session_id=session_id, screenshot_path=path, full_page=full_page)


@tool("browser_close_session", parse_docstring=True)
async def browser_close_session_tool(session_id: str) -> str:
    """Close browser session and release resources.

    Args:
        session_id: Session identifier.
    """
    session = await _pop_session(session_id)
    if session is None:
        return _json_err("SESSION_NOT_FOUND", f"Session not found: {session_id}", session_id=session_id)

    try:
        if session.context is not None:
            await session.context.close()
    except Exception:
        pass
    try:
        if session.browser is not None:
            await session.browser.close()
    except Exception:
        pass
    try:
        if session.playwright is not None:
            await session.playwright.stop()
    except Exception:
        pass

    return _json_ok(session_id=session_id, closed=True)
