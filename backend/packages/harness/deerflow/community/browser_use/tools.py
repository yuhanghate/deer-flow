import json
import os
from typing import Any

from langchain.tools import tool

from deerflow.config import get_app_config


def _get_tool_extra(tool_name: str) -> dict[str, Any]:
    cfg = get_app_config().get_tool_config(tool_name)
    if cfg is None:
        return {}
    return dict(getattr(cfg, "model_extra", {}) or {})


def _compose_task(task: str, start_url: str | None) -> str:
    clean_task = task.strip()
    if not start_url:
        return clean_task
    return f"Start from this URL: {start_url}\n\nTask:\n{clean_task}"


def _resolve_optional_secret(value: str | None) -> str | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith("$"):
        return os.getenv(raw[1:], "")
    return raw


def _build_llm(provider: str, model: str | None, api_key: str | None, base_url: str | None):
    provider = provider.strip().lower()
    if provider in {"browser_use", "browser-use", "cloud"}:
        from browser_use import ChatBrowserUse

        kwargs: dict[str, Any] = {}
        if model:
            kwargs["model"] = model
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return ChatBrowserUse(**kwargs)
    if provider == "openai":
        from browser_use import ChatOpenAI

        kwargs = {"model": model} if model else {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return ChatOpenAI(**kwargs)
    if provider == "anthropic":
        from browser_use import ChatAnthropic

        kwargs = {"model": model} if model else {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return ChatAnthropic(**kwargs)
    if provider in {"google", "gemini"}:
        from browser_use import ChatGoogle

        kwargs = {"model": model} if model else {}
        if api_key:
            kwargs["api_key"] = api_key
        return ChatGoogle(**kwargs)
    raise ValueError(f"Unsupported browser_use llm_provider: {provider}")


@tool("browser_use_task", parse_docstring=True)
async def browser_use_task_tool(task: str, start_url: str = "", max_steps: int = 30) -> str:
    """Run a generic browser automation task using browser-use.

    Use this tool when you need exploratory interactions on arbitrary websites.
    For stable production flows on known sites, prefer dedicated tools with
    deterministic extraction logic.

    Args:
        task: Natural-language objective for the browser agent.
        start_url: Optional URL where the browser agent should start from.
        max_steps: Maximum browser-use action steps (1-100).
    """
    extra = _get_tool_extra("browser_use_task")
    llm_provider = str(extra.get("llm_provider", "browser_use"))
    llm_model = extra.get("llm_model")
    llm_api_key = _resolve_optional_secret(extra.get("llm_api_key"))
    llm_base_url = _resolve_optional_secret(extra.get("llm_base_url"))
    cdp_url = str(extra.get("cdp_url", "") or "").strip()
    use_cloud = bool(extra.get("use_cloud", False))
    headless = bool(extra.get("headless", True))

    bounded_steps = max(1, min(max_steps, 100))

    try:
        from browser_use import Agent, Browser
    except Exception as exc:
        return json.dumps(
            {
                "ok": False,
                "code": "MISSING_DEPENDENCY",
                "message": "browser-use is not available. Install dependencies with `cd backend && uv sync`.",
                "error": str(exc),
            },
            ensure_ascii=False,
        )

    try:
        llm = _build_llm(llm_provider, llm_model, llm_api_key, llm_base_url)
    except Exception as exc:
        return json.dumps(
            {
                "ok": False,
                "code": "LLM_CONFIG_ERROR",
                "message": str(exc),
            },
            ensure_ascii=False,
        )

    browser_kwargs: dict[str, Any] = {"headless": headless}
    if cdp_url:
        browser_kwargs["cdp_url"] = cdp_url
    elif use_cloud:
        browser_kwargs["use_cloud"] = True

    browser = None
    try:
        browser = Browser(**browser_kwargs)
        agent = Agent(
            task=_compose_task(task, start_url.strip() or None),
            llm=llm,
            browser=browser,
        )
        history = await agent.run(max_steps=bounded_steps)

        urls = history.urls() if hasattr(history, "urls") else []
        actions = history.action_names() if hasattr(history, "action_names") else []
        final_result = history.final_result() if hasattr(history, "final_result") else ""

        return json.dumps(
            {
                "ok": True,
                "code": "OK",
                "task": task,
                "start_url": start_url,
                "max_steps": bounded_steps,
                "is_done": history.is_done() if hasattr(history, "is_done") else None,
                "is_successful": history.is_successful() if hasattr(history, "is_successful") else None,
                "steps": history.number_of_steps() if hasattr(history, "number_of_steps") else len(actions),
                "visited_urls": urls[-20:],
                "actions": actions[-50:],
                "final_result": final_result or "",
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps(
            {
                "ok": False,
                "code": "BROWSER_USE_ERROR",
                "message": str(exc),
                "task": task,
                "start_url": start_url,
            },
            ensure_ascii=False,
        )
    finally:
        if browser is not None and hasattr(browser, "close"):
            close_result = browser.close()
            if hasattr(close_result, "__await__"):
                try:
                    await close_result
                except Exception:
                    pass
