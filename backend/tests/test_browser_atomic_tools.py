"""Unit tests for browser_atomic community tools."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch


class _FakeLocator:
    def __init__(self, text: str = ""):
        self._text = text

    @property
    def first(self):
        return self

    async def click(self, timeout: int | None = None):
        return None

    async def fill(self, value: str, timeout: int | None = None):
        self._text = value

    async def inner_text(self, timeout: int | None = None):
        return self._text

    def locator(self, _selector: str):
        return _FakeLocator(self._text)


class _FakeItems:
    def __init__(self, rows: list[dict[str, str]]):
        self._rows = rows

    async def count(self):
        return len(self._rows)

    def nth(self, idx: int):
        row = self._rows[idx]
        return _FakeRow(row)


class _FakeRow:
    def __init__(self, row: dict[str, str]):
        self._row = row

    def locator(self, selector: str):
        return _FakeLocator(self._row.get(selector, ""))


class _FakePage:
    def __init__(self):
        self.url = "https://example.com"
        self._title = "Example"
        self._rows = []
        self._html = "<html><body><h1>Hello</h1></body></html>"
        self._interactive = [
            {"tag": "input", "id": "q", "class_name": "search-input", "text": "", "selector": "#q", "visible": True, "href": "", "name": "q", "type": "text", "rect": {"x": 10, "y": 20, "width": 120, "height": 32}},
            {"tag": "button", "id": "", "class_name": "btn", "text": "搜索", "selector": "button.btn", "visible": True, "href": "", "name": "", "type": "button", "rect": {"x": 150, "y": 20, "width": 60, "height": 32}},
        ]
        self._links = [
            {"tag": "a", "text": "热搜榜", "href": "/hot", "visible": True},
            {"tag": "a", "text": "隐藏链接", "href": "/hidden", "visible": False},
        ]
        self._layout = [
            {"tag": "input", "selector": "#q", "text": "", "visible": True, "rect": {"x": 10, "y": 20, "width": 120, "height": 32}},
            {"tag": "button", "selector": "button.btn", "text": "搜索", "visible": True, "rect": {"x": 150, "y": 20, "width": 60, "height": 32}},
        ]

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int | None = None):
        self.url = url

    def locator(self, selector: str):
        if selector == ".item":
            return _FakeItems(self._rows)
        return _FakeLocator("hello world")

    async def wait_for_selector(self, selector: str, timeout: int | None = None):
        return None

    async def wait_for_load_state(self, state: str, timeout: int | None = None):
        return None

    async def wait_for_timeout(self, ms: int):
        return None

    async def title(self):
        return self._title

    async def bring_to_front(self):
        return None

    async def screenshot(self, path: str, full_page: bool = True):
        return None

    async def content(self):
        return self._html

    async def evaluate(self, _script: str, args=None):
        if args and "selector" in args and args["selector"] == ".item":
            return self._rows
        if args and "selector" in args and args["selector"] in {"a", "a,button,input,textarea,select,[role=\"button\"]"}:
            if args["selector"] == "a":
                return self._links
            return self._layout
        if args and "selector" in args:
            return self._links if args["selector"] == "a" else self._layout
        # interactive elements call has no args
        return self._interactive


class _FakeContext:
    def __init__(self, page: _FakePage):
        self.pages = [page]

    async def close(self):
        return None


class _FakeSession:
    def __init__(self, page: _FakePage):
        self.session_id = "sess1"
        self.page = page
        self.context = _FakeContext(page)
        self.browser = None
        self.playwright = None
        self.cdp_url = "http://127.0.0.1:9222"
        self.headless = False
        self.conversation_id = "conv-1"
        self.task_id = "task-1"
        self.origin = "https://example.com"
        self.reuse_policy = "conversation_origin_tab"
        self.created_at = 10.0
        self.lock = asyncio.Lock()
        self.updated_at = 0.0


class TestBrowserAtomicTools:
    def test_goto_session_not_found(self):
        from deerflow.community.browser_atomic.tools import browser_goto_tool

        out = asyncio.run(browser_goto_tool.ainvoke({"session_id": "none", "url": "https://x.com"}))
        data = json.loads(out)
        assert data["ok"] is False
        assert data["code"] == "SESSION_NOT_FOUND"

    def test_extract_list_invalid_json(self):
        from deerflow.community.browser_atomic.tools import browser_extract_list_tool

        page = _FakePage()
        session = _FakeSession(page)
        with patch("deerflow.community.browser_atomic.tools._get_session", return_value=session):
            out = asyncio.run(
                browser_extract_list_tool.ainvoke(
                    {
                        "session_id": "sess1",
                        "item_selector": ".item",
                        "field_selectors_json": "{bad json",
                        "limit": 5,
                    }
                )
            )
        data = json.loads(out)
        assert data["ok"] is False
        assert data["code"] == "INVALID_FIELDS_JSON"

    def test_extract_list_success(self):
        from deerflow.community.browser_atomic.tools import browser_extract_list_tool

        page = _FakePage()
        page._rows = [
            {".title": "Topic A", ".hot": "100"},
            {".title": "Topic B", ".hot": "200"},
        ]
        session = _FakeSession(page)
        with patch("deerflow.community.browser_atomic.tools._get_session", return_value=session):
            out = asyncio.run(
                browser_extract_list_tool.ainvoke(
                    {
                        "session_id": "sess1",
                        "item_selector": ".item",
                        "field_selectors_json": json.dumps({"title": ".title", "hot": ".hot"}),
                        "limit": 10,
                    }
                )
            )
        data = json.loads(out)
        assert data["ok"] is True
        assert data["count"] == 2
        assert data["items"][0]["title"] == "Topic A"

    def test_get_url_success(self):
        from deerflow.community.browser_atomic.tools import browser_get_url_tool

        page = _FakePage()
        session = _FakeSession(page)
        with patch("deerflow.community.browser_atomic.tools._get_session", return_value=session):
            out = asyncio.run(browser_get_url_tool.ainvoke({"session_id": "sess1"}))
        data = json.loads(out)
        assert data["ok"] is True
        assert data["current_url"] == "https://example.com"
        assert data["title"] == "Example"

    def test_check_status_summary_success(self):
        from deerflow.community.browser_atomic.tools import browser_check_status_tool

        with patch("deerflow.community.browser_atomic.tools._SESSIONS", {}):
            out = asyncio.run(browser_check_status_tool.ainvoke({"check_cdp": False}))
        data = json.loads(out)
        assert data["ok"] is True
        assert data["active_sessions"] == 0
        assert data["session"] is None

    def test_check_status_session_not_found(self):
        from deerflow.community.browser_atomic.tools import browser_check_status_tool

        with patch("deerflow.community.browser_atomic.tools._SESSIONS", {}):
            out = asyncio.run(browser_check_status_tool.ainvoke({"session_id": "missing", "check_cdp": False}))
        data = json.loads(out)
        assert data["ok"] is False
        assert data["code"] == "SESSION_NOT_FOUND"

    def test_check_status_with_session(self):
        from deerflow.community.browser_atomic.tools import browser_check_status_tool

        page = _FakePage()
        session = _FakeSession(page)
        with patch("deerflow.community.browser_atomic.tools._SESSIONS", {"sess1": session}):
            out = asyncio.run(browser_check_status_tool.ainvoke({"session_id": "sess1", "check_cdp": False}))
        data = json.loads(out)
        assert data["ok"] is True
        assert data["active_sessions"] == 1
        assert data["session"]["session_id"] == "sess1"
        assert data["session"]["current_url"] == "https://example.com"

    def test_get_page_source_truncated(self):
        from deerflow.community.browser_atomic.tools import browser_get_page_source_tool

        page = _FakePage()
        page._html = "x" * 100
        session = _FakeSession(page)
        with patch("deerflow.community.browser_atomic.tools._get_session", return_value=session):
            out = asyncio.run(browser_get_page_source_tool.ainvoke({"session_id": "sess1", "max_chars": 20}))
        data = json.loads(out)
        assert data["ok"] is True
        assert data["returned_chars"] == 20
        assert data["truncated"] is True

    def test_get_interactive_elements(self):
        from deerflow.community.browser_atomic.tools import browser_get_interactive_elements_tool

        page = _FakePage()
        session = _FakeSession(page)
        with patch("deerflow.community.browser_atomic.tools._get_session", return_value=session):
            out = asyncio.run(
                browser_get_interactive_elements_tool.ainvoke({"session_id": "sess1", "limit": 10, "include_invisible": False})
            )
        data = json.loads(out)
        assert data["ok"] is True
        assert data["count"] == 2
        assert data["elements"][0]["selector"] == "#q"

    def test_extract_links(self):
        from deerflow.community.browser_atomic.tools import browser_extract_links_tool

        page = _FakePage()
        session = _FakeSession(page)
        with patch("deerflow.community.browser_atomic.tools._get_session", return_value=session):
            out = asyncio.run(
                browser_extract_links_tool.ainvoke({"session_id": "sess1", "selector": "a", "limit": 10, "include_invisible": False})
            )
        data = json.loads(out)
        assert data["ok"] is True
        assert data["count"] == 1
        assert data["links"][0]["href"] == "https://example.com/hot"

    def test_layout_snapshot_invalid_selectors(self):
        from deerflow.community.browser_atomic.tools import browser_get_layout_snapshot_tool

        page = _FakePage()
        session = _FakeSession(page)
        with patch("deerflow.community.browser_atomic.tools._get_session", return_value=session):
            out = asyncio.run(
                browser_get_layout_snapshot_tool.ainvoke({"session_id": "sess1", "selectors_json": "{bad json"})
            )
        data = json.loads(out)
        assert data["ok"] is False
        assert data["code"] == "INVALID_SELECTORS_JSON"

    def test_layout_snapshot_success(self):
        from deerflow.community.browser_atomic.tools import browser_get_layout_snapshot_tool

        page = _FakePage()
        session = _FakeSession(page)
        with patch("deerflow.community.browser_atomic.tools._get_session", return_value=session):
            out = asyncio.run(
                browser_get_layout_snapshot_tool.ainvoke(
                    {"session_id": "sess1", "selectors_json": json.dumps(["a", "button"]), "limit": 10, "only_visible": True}
                )
            )
        data = json.loads(out)
        assert data["ok"] is True
        assert data["count"] == 2

    def test_pick_reusable_session_by_origin(self):
        from deerflow.community.browser_atomic.tools import _pick_reusable_session

        sessions = [
            SimpleNamespace(session_id="a", conversation_id="c1", origin="https://a.com", updated_at=1.0),
            SimpleNamespace(session_id="b", conversation_id="c1", origin="https://b.com", updated_at=2.0),
        ]
        picked = _pick_reusable_session(
            sessions=sessions,
            conversation_id="c1",
            reuse_policy="conversation_origin_tab",
            requested_origin="https://b.com",
        )
        assert picked is not None
        assert picked.session_id == "b"

    def test_pick_reusable_session_single_tab(self):
        from deerflow.community.browser_atomic.tools import _pick_reusable_session

        sessions = [
            SimpleNamespace(session_id="old", conversation_id="c1", origin="https://a.com", updated_at=1.0),
            SimpleNamespace(session_id="new", conversation_id="c1", origin="https://x.com", updated_at=9.0),
        ]
        picked = _pick_reusable_session(
            sessions=sessions,
            conversation_id="c1",
            reuse_policy="conversation_single_tab",
            requested_origin=None,
        )
        assert picked is not None
        assert picked.session_id == "new"
