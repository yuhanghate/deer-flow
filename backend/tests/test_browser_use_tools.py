"""Unit tests for browser-use community tool."""

import asyncio
import json
import os
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch


def _install_fake_browser_use_module() -> ModuleType:
    module = ModuleType("browser_use")

    class FakeChatBrowserUse:
        last_kwargs: dict = {}

        def __init__(self, **kwargs):
            FakeChatBrowserUse.last_kwargs = kwargs

    class FakeChatOpenAI:
        last_kwargs: dict = {}

        def __init__(self, **kwargs):
            FakeChatOpenAI.last_kwargs = kwargs

    class FakeBrowser:
        init_kwargs: dict = {}

        def __init__(self, **kwargs):
            FakeBrowser.init_kwargs = kwargs

        async def close(self):
            return None

    class FakeHistory:
        def urls(self):
            return ["https://example.com", "https://example.com/result"]

        def action_names(self):
            return ["go_to_url", "extract_content"]

        def final_result(self):
            return "done"

        def is_done(self):
            return True

        def is_successful(self):
            return True

        def number_of_steps(self):
            return 2

    class FakeAgent:
        last_task: str = ""
        last_max_steps: int = 0

        def __init__(self, task, llm, browser):
            FakeAgent.last_task = task
            self._llm = llm
            self._browser = browser

        async def run(self, max_steps: int = 30):
            FakeAgent.last_max_steps = max_steps
            return FakeHistory()

    module.Agent = FakeAgent
    module.Browser = FakeBrowser
    module.ChatBrowserUse = FakeChatBrowserUse
    module.ChatOpenAI = FakeChatOpenAI
    return module


class TestBrowserUseTaskTool:
    @patch("deerflow.community.browser_use.tools.get_app_config")
    def test_success(self, mock_get_app_config):
        cfg = MagicMock()
        cfg.model_extra = {"llm_provider": "browser_use", "headless": True}
        mock_get_app_config.return_value.get_tool_config.return_value = cfg

        fake_module = _install_fake_browser_use_module()
        with patch.dict(sys.modules, {"browser_use": fake_module}):
            from deerflow.community.browser_use.tools import browser_use_task_tool

            result = asyncio.run(
                browser_use_task_tool.ainvoke(
                    {
                        "task": "Find patent summary",
                        "start_url": "https://example.com",
                        "max_steps": 5,
                    }
                )
            )

        data = json.loads(result)
        assert data["ok"] is True
        assert data["code"] == "OK"
        assert data["is_successful"] is True
        assert "Start from this URL: https://example.com" in data["task"] or data["start_url"] == "https://example.com"

    @patch("deerflow.community.browser_use.tools.get_app_config")
    def test_openai_provider_accepts_custom_base_url_and_api_key(self, mock_get_app_config):
        cfg = MagicMock()
        cfg.model_extra = {
            "llm_provider": "openai",
            "llm_model": "gpt-4.1-mini",
            "llm_api_key": "$TEST_BROWSER_USE_KEY",
            "llm_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        }
        mock_get_app_config.return_value.get_tool_config.return_value = cfg

        fake_module = _install_fake_browser_use_module()
        with patch.dict(sys.modules, {"browser_use": fake_module}), patch.dict(os.environ, {"TEST_BROWSER_USE_KEY": "abc123"}, clear=False):
            from deerflow.community.browser_use.tools import browser_use_task_tool

            result = asyncio.run(
                browser_use_task_tool.ainvoke(
                    {
                        "task": "Open search page and summarize top result",
                        "start_url": "https://example.com",
                        "max_steps": 4,
                    }
                )
            )

        data = json.loads(result)
        assert data["ok"] is True
        assert fake_module.ChatOpenAI.last_kwargs["api_key"] == "abc123"
        assert fake_module.ChatOpenAI.last_kwargs["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert fake_module.ChatOpenAI.last_kwargs["model"] == "gpt-4.1-mini"

    @patch("deerflow.community.browser_use.tools.get_app_config")
    def test_invalid_llm_provider(self, mock_get_app_config):
        cfg = MagicMock()
        cfg.model_extra = {"llm_provider": "unsupported_vendor"}
        mock_get_app_config.return_value.get_tool_config.return_value = cfg

        fake_module = _install_fake_browser_use_module()
        with patch.dict(sys.modules, {"browser_use": fake_module}):
            from deerflow.community.browser_use.tools import browser_use_task_tool

            result = asyncio.run(
                browser_use_task_tool.ainvoke(
                    {
                        "task": "Any task",
                        "start_url": "",
                        "max_steps": 3,
                    }
                )
            )

        data = json.loads(result)
        assert data["ok"] is False
        assert data["code"] == "LLM_CONFIG_ERROR"

    @patch("deerflow.community.browser_use.tools.get_app_config")
    def test_missing_dependency(self, mock_get_app_config):
        cfg = MagicMock()
        cfg.model_extra = {"llm_provider": "browser_use"}
        mock_get_app_config.return_value.get_tool_config.return_value = cfg

        with patch.dict(sys.modules, {"browser_use": None}):
            from deerflow.community.browser_use.tools import browser_use_task_tool

            result = asyncio.run(
                browser_use_task_tool.ainvoke(
                    {
                        "task": "Any task",
                        "start_url": "",
                        "max_steps": 3,
                    }
                )
            )

        data = json.loads(result)
        assert data["ok"] is False
        assert data["code"] == "MISSING_DEPENDENCY"
