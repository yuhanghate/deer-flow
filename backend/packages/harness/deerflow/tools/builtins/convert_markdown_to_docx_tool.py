from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Annotated

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.config import get_config
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.config.paths import VIRTUAL_PATH_PREFIX, get_paths

_INVALID_CHARS = re.compile(r"[\\/:*?\"<>|]+")
_ALLOWED_MARKDOWN_EXTS = {".md", ".markdown"}
_MAX_ERROR_CHARS = 1200


def _get_thread_id(runtime: ToolRuntime[ContextT, ThreadState]) -> str | None:
    thread_id = runtime.context.get("thread_id") if runtime.context else None
    if thread_id:
        return thread_id

    runtime_config = getattr(runtime, "config", None) or {}
    thread_id = runtime_config.get("configurable", {}).get("thread_id")
    if thread_id:
        return thread_id

    try:
        return get_config().get("configurable", {}).get("thread_id")
    except RuntimeError:
        return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_source_path(runtime: ToolRuntime[ContextT, ThreadState], source_filepath: str) -> Path:
    if runtime.state is None:
        raise ValueError("Thread runtime state is not available")

    thread_data = runtime.state.get("thread_data") or {}
    workspace_path = thread_data.get("workspace_path")
    uploads_path = thread_data.get("uploads_path")
    outputs_path = thread_data.get("outputs_path")
    if not outputs_path:
        raise ValueError("Thread outputs path is not available in runtime state")

    thread_id = _get_thread_id(runtime)
    if not thread_id:
        raise ValueError("Thread ID is not available in runtime context or runtime config")

    stripped = source_filepath.lstrip("/")
    virtual_prefix = VIRTUAL_PATH_PREFIX.lstrip("/")
    if stripped == virtual_prefix or stripped.startswith(virtual_prefix + "/"):
        source_path = get_paths().resolve_virtual_path(thread_id, source_filepath)
    else:
        source_path = Path(source_filepath).expanduser().resolve()

    source_path = source_path.resolve()
    allowed_roots = [Path(p).resolve() for p in (workspace_path, uploads_path, outputs_path) if p]
    if not allowed_roots:
        raise ValueError("Thread directories are not available in runtime state")

    if not any(_is_relative_to(source_path, root) for root in allowed_roots):
        raise ValueError(f"Only files in {VIRTUAL_PATH_PREFIX} can be converted: {source_filepath}")
    if not source_path.exists() or not source_path.is_file():
        raise ValueError(f"Source file not found: {source_filepath}")
    if source_path.suffix.lower() not in _ALLOWED_MARKDOWN_EXTS:
        allowed = ", ".join(sorted(_ALLOWED_MARKDOWN_EXTS))
        raise ValueError(f"Source must be a Markdown file ({allowed}): {source_filepath}")
    return source_path


def _sanitize_filename(filename: str) -> str:
    cleaned = _INVALID_CHARS.sub("_", filename).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned


def _resolve_output_path(outputs_dir: Path, source_path: Path, output_filename: str) -> Path:
    if output_filename.strip():
        name = _sanitize_filename(output_filename)
        if not name:
            raise ValueError("output_filename is invalid after sanitization")
    else:
        name = source_path.stem

    if not name.lower().endswith(".docx"):
        name = f"{name}.docx"
    target = outputs_dir / name
    if not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    index = 1
    while True:
        candidate = outputs_dir / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _convert_with_pandoc(source_path: Path, target_path: Path) -> tuple[bool, str]:
    result = subprocess.run(
        ["pandoc", str(source_path), "-o", str(target_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return True, ""
    message = (result.stderr or result.stdout or "pandoc failed with unknown error").strip()
    return False, message[:_MAX_ERROR_CHARS]


@tool("convert_markdown_to_docx", parse_docstring=True)
def convert_markdown_to_docx_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    source_filepath: str,
    output_filename: str = "",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """Convert a Markdown draft into a DOCX file in `/mnt/user-data/outputs`.

    Use this tool instead of manually running `pandoc` in bash when you need a
    Word deliverable from a Markdown draft.

    Args:
        source_filepath: Absolute path of the Markdown source file.
        output_filename: Optional target filename (with or without `.docx`).
    """
    try:
        if runtime.state is None:
            raise ValueError("Thread runtime state is not available")

        thread_data = runtime.state.get("thread_data") or {}
        outputs_path = thread_data.get("outputs_path")
        if not outputs_path:
            raise ValueError("Thread outputs path is not available in runtime state")

        source_path = _resolve_source_path(runtime, source_filepath)
        outputs_dir = Path(outputs_path).resolve()
        outputs_dir.mkdir(parents=True, exist_ok=True)
        target_path = _resolve_output_path(outputs_dir, source_path, output_filename)

        ok, error_message = _convert_with_pandoc(source_path, target_path)
        if not ok:
            raise ValueError(
                "Failed to convert Markdown to DOCX via pandoc. "
                f"source={source_path.name}, target={target_path.name}, error={error_message}"
            )

        artifact_path = f"{VIRTUAL_PATH_PREFIX}/outputs/{target_path.name}"
        return Command(
            update={
                "artifacts": [artifact_path],
                "messages": [
                    ToolMessage(
                        f"Converted Markdown to DOCX: {artifact_path}",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )
    except ValueError as exc:
        return Command(
            update={
                "messages": [ToolMessage(f"Error: {exc}", tool_call_id=tool_call_id)],
            }
        )
