"""Redact internal skill reference artifacts from assistant outputs."""

from __future__ import annotations

import re
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

_INTERNAL_SAMPLE_PUBLICATION_IDS = {
    "CN103382267B",
    "CN106883431B",
    "CN106936529B",
    "CN105634643B",
    "CN106119820B",
    "CN105618506B",
    "CN108024294B",
    "CN112575228B",
    "CN108286799B",
    "CN108620077B",
}
# Match generic CN publication IDs and selectively redact only internal samples.
_CN_PUBLICATION_ID_REGEX = re.compile(r"\bCN[\s-]?\d{6,12}(?:[.\s-]?\d+)?[A-Z]?\b", re.IGNORECASE)
_INTERNAL_PATH_REGEX = re.compile(
    r"(?:/mnt/skills/public/patent-cn-core/resources/samples[^\s]*)|(?:skills/public/patent-cn-core/resources/samples[^\s]*)",
    re.IGNORECASE,
)


def _sanitize_text(text: str) -> str:
    def _replace_cn_id(match: re.Match[str]) -> str:
        raw = match.group(0)
        canonical = re.sub(r"[\s\-.]", "", raw).upper()
        return "内部参考文献" if canonical in _INTERNAL_SAMPLE_PUBLICATION_IDS else raw

    sanitized = _CN_PUBLICATION_ID_REGEX.sub(_replace_cn_id, text)
    sanitized = _INTERNAL_PATH_REGEX.sub("内部参考资料路径", sanitized)
    return sanitized


def _sanitize_content(content: Any) -> Any:
    if isinstance(content, str):
        return _sanitize_text(content)

    if isinstance(content, list):
        changed = False
        new_items: list[Any] = []
        for item in content:
            if isinstance(item, dict):
                new_item = dict(item)
                for key in ("text", "content"):
                    value = new_item.get(key)
                    if isinstance(value, str):
                        sanitized_value = _sanitize_text(value)
                        if sanitized_value != value:
                            new_item[key] = sanitized_value
                            changed = True
                new_items.append(new_item)
            else:
                new_items.append(item)
        return new_items if changed else content

    return content


class InternalReferenceRedactionMiddleware(AgentMiddleware[AgentState]):
    """Redact internal sample publication IDs from final assistant output."""

    def _sanitize_last_ai_message(self, state: AgentState) -> dict | None:
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        if getattr(last_msg, "type", None) != "ai":
            return None

        content = getattr(last_msg, "content", None)
        sanitized_content = _sanitize_content(content)
        if sanitized_content == content:
            return None

        updated_msg = last_msg.model_copy(update={"content": sanitized_content})
        return {"messages": [updated_msg]}

    @override
    def after_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._sanitize_last_ai_message(state)

    @override
    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._sanitize_last_ai_message(state)
