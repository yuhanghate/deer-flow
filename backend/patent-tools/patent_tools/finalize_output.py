from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Annotated

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.config import get_config
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.config.paths import VIRTUAL_PATH_PREFIX

from .markdown_processor import preprocess_markdown_to_html
from .output_versioning import resolve_unique_versioned_filename, strip_trailing_v_suffix

_PATENT_FILENAME_INVALID_CHARS = re.compile(r"[\\/:*?\"<>|]+")
_ALLOWED_MD_EXTS = {".md", ".markdown"}


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
        raise ValueError(f"Only files in {VIRTUAL_PATH_PREFIX} can be finalized: {source_filepath}")
    if not source_path.exists() or not source_path.is_file():
        raise ValueError(f"Source file not found: {source_filepath}")
    return source_path


def _normalize_patent_title(title: str) -> str:
    normalized = _PATENT_FILENAME_INVALID_CHARS.sub("_", title).strip()
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "未命名专利"


@tool("finalize_patent_output", parse_docstring=True)
def finalize_patent_output_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    patent_title: str,
    source_filepath: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Finalize a patent draft into a versioned single output file and present it to the user.

    Use this when a patent draft is complete and you need one deliverable file named
    `vYYYYMMDDHHMM_专利名称.<ext>` in `/mnt/user-data/outputs`.

    Args:
        patent_title: Patent title used for the output filename suffix.
        source_filepath: Absolute source file path (typically in `/mnt/user-data/workspace` or `/mnt/user-data/outputs`).
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

        normalized_title = _normalize_patent_title(patent_title)
        normalized_title = strip_trailing_v_suffix(normalized_title) or normalized_title
        suffix = source_path.suffix or ".docx"

        # Pre-process Markdown files: convert to HTML with <sub>/<sup> tags
        if source_path.suffix.lower() in _ALLOWED_MD_EXTS:
            content = source_path.read_text(encoding="utf-8")
            preprocessed = preprocess_markdown_to_html(content)
            source_path.write_text(preprocessed, encoding="utf-8")

        target_name = resolve_unique_versioned_filename(
            outputs_dir, normalized_title, suffix
        )
        target_path = outputs_dir / target_name
        shutil.copy2(source_path, target_path)

        artifact_path = f"{VIRTUAL_PATH_PREFIX}/outputs/{target_name}"
        return Command(
            update={
                "artifacts": [artifact_path],
                "messages": [
                    ToolMessage(
                        f"Finalized patent file: {artifact_path}",
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
