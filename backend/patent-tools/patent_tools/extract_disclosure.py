from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.config.paths import VIRTUAL_PATH_PREFIX

_MAX_EXTRACT_CHARS = 200_000


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_input_path(runtime: ToolRuntime[ContextT, ThreadState], source_filepath: str) -> Path:
    """Resolve a file path, supporting both virtual and absolute paths."""
    if runtime.state is None:
        raise ValueError("Thread runtime state is not available")

    thread_data = runtime.state.get("thread_data") or {}
    workspace_path = thread_data.get("workspace_path")
    uploads_path = thread_data.get("uploads_path")
    outputs_path = thread_data.get("outputs_path")

    stripped = source_filepath.lstrip("/")
    virtual_prefix = VIRTUAL_PATH_PREFIX.lstrip("/")
    if stripped == virtual_prefix or stripped.startswith(virtual_prefix + "/"):
        suffix = stripped[len(virtual_prefix) :].lstrip("/")
        segment_to_host = {}
        for segment, host in [
            ("workspace", workspace_path),
            ("uploads", uploads_path),
            ("outputs", outputs_path),
        ]:
            if host:
                segment_to_host[segment] = host
        if suffix:
            top_segment = suffix.split("/")[0]
            if top_segment in segment_to_host:
                source_path = Path(segment_to_host[top_segment]) / "/".join(suffix.split("/")[1:])
            else:
                any_host = next(iter(segment_to_host.values()))
                user_data_root = str(Path(any_host).parent)
                source_path = Path(user_data_root) / suffix
        else:
            any_host = next(iter(segment_to_host.values()))
            source_path = Path(Path(any_host).parent)
    else:
        source_path = Path(source_filepath).expanduser().resolve()

    source_path = source_path.resolve()
    allowed_roots = [Path(p).resolve() for p in (workspace_path, uploads_path, outputs_path) if p]
    if not allowed_roots:
        raise ValueError("Thread directories are not available in runtime state")
    if not any(_is_relative_to(source_path, root) for root in allowed_roots):
        raise ValueError(f"Only files in {VIRTUAL_PATH_PREFIX} can be read: {source_filepath}")
    if not source_path.exists() or not source_path.is_file():
        raise ValueError(f"Source file not found: {source_filepath}")
    return source_path


def _is_skill_or_system_injection(text: str) -> bool:
    """Return True if the text looks like a skill definition, system prompt, or nested JSON export."""
    stripped = text.strip()
    if stripped.startswith("---\nname:") or stripped.startswith("---\nname :"):
        return True
    # Also skip JSON strings that are conversation dumps (not disclosure text)
    if stripped.startswith("{") and ("\"messages\"" in stripped or "'messages'" in stripped):
        return True
    return False


def _extract_disclosure_from_conversation_export(data: dict) -> str:
    """Extract the longest plain-text disclosure from a deer-flow exported conversation JSON."""
    messages = data.get("messages", [])
    texts: list[tuple[int, str]] = []
    for idx, msg in enumerate(messages):
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > 1000:
            if not _is_skill_or_system_injection(content):
                texts.append((idx, content))
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    txt = block.get("text", "")
                    if len(txt) > 1000 and not _is_skill_or_system_injection(txt):
                        texts.append((idx, txt))
    if not texts:
        raise ValueError("No disclosure text found in the conversation export.")
    # Return the longest non-skill text block (usually the disclosure)
    _, text = max(texts, key=lambda t: len(t[1]))
    return text


def _extract_disclosure_from_nested_export(data: dict) -> str | None:
    """Handle JSON files that contain a full previous conversation as a message's content."""
    messages = data.get("messages", [])
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip().startswith("{"):
            try:
                inner = json.loads(content, strict=False)
                if isinstance(inner, dict) and "messages" in inner:
                    return _extract_disclosure_from_conversation_export(inner)
            except (json.JSONDecodeError, ValueError):
                continue
    return None


def _extract_disclosure(data: dict) -> tuple[str, int]:
    """Extract disclosure text from a JSON file.

    Returns (disclosure_text, message_count).
    """
    # Strategy 1: Check if any message contains a nested conversation export.
    # This handles JSON files where a previous conversation was pasted/attached.
    nested = _extract_disclosure_from_nested_export(data)
    if nested:
        return nested, len(data.get("messages", []))

    # Strategy 2: Top-level messages array (standard export)
    if "messages" in data:
        text = _extract_disclosure_from_conversation_export(data)
        return text, len(data.get("messages", []))

    raise ValueError(
        "Cannot find disclosure text. Expected a deer-flow exported conversation JSON "
        "with a 'messages' array, or a message containing such a JSON."
    )


@tool("extract_json_disclosure", parse_docstring=True)
def extract_json_disclosure_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    source_filepath: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """Extract a technical disclosure from a deer-flow exported conversation JSON.

    Reads a JSON file (typically uploaded by the user from a previous conversation
    export), finds the longest plain-text message — usually the original technical
    disclosure — and writes it to ``/mnt/user-data/workspace/disclosure.md`` so it
    can be processed by patent drafting skills.

    Supports:
    - Standard deer-flow conversation exports (top-level ``{"messages": [...]}``)
    - JSON files where a message's content is itself a full conversation export

    Args:
        source_filepath: Absolute path to the JSON file (in uploads, workspace, or outputs).
    """
    try:
        if runtime.state is None:
            raise ValueError("Thread runtime state is not available")
        thread_data = runtime.state.get("thread_data") or {}
        workspace_path = thread_data.get("workspace_path")
        if not workspace_path:
            raise ValueError("Thread workspace path is not available in runtime state")

        source_path = _resolve_input_path(runtime, source_filepath)
        if source_path.suffix.lower() not in (".json",):
            raise ValueError(f"Source must be a JSON file: {source_filepath}")

        content = source_path.read_text(encoding="utf-8")
        data = json.loads(content, strict=False)

        disclosure, msg_count = _extract_disclosure(data)
        disclosure = disclosure[:_MAX_EXTRACT_CHARS]

        # Write to workspace/disclosure.md
        workspace_dir = Path(workspace_path).resolve()
        workspace_dir.mkdir(parents=True, exist_ok=True)
        target_path = workspace_dir / "disclosure.md"
        target_path.write_text(disclosure, encoding="utf-8")

        artifact_path = f"{VIRTUAL_PATH_PREFIX}/workspace/disclosure.md"
        preview = disclosure[:500].replace("\n", " ")
        summary = (
            f"Extracted disclosure from JSON ({msg_count} messages): {artifact_path} "
            f"({len(disclosure)} chars). Preview: {preview}"
        )
        return Command(
            update={
                "artifacts": [artifact_path],
                "messages": [
                    ToolMessage(summary, tool_call_id=tool_call_id),
                ],
            }
        )
    except (ValueError, json.JSONDecodeError) as exc:
        return Command(
            update={
                "messages": [ToolMessage(f"Error: {exc}", tool_call_id=tool_call_id)],
            }
        )
